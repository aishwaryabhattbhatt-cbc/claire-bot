import json
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.config import get_settings

VALID_PROMPT_MODES = {"comparison", "french_review", "english_review"}
VALID_DERIVATION_STATUSES = {"queued", "processing", "completed", "failed"}
VALID_ACTIVATION_STATUSES = {"pending_activation", "active", "disabled"}


class FeedbackMemoryService:
    """Persist, derive, and manage mode-scoped feedback memory instructions."""

    def __init__(self) -> None:
        settings = get_settings()
        file_name = getattr(settings, "feedback_memory_filename", "review_feedback_memory.json")
        self._file_path = Path(settings.processed_dir) / file_name
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._queue: deque[str] = deque()
        self._worker_started = False

    def list_items(self, mode: Optional[str] = None) -> list[dict[str, Any]]:
        mode_filter = self._normalize_mode(mode) if mode else None
        store = self._read_store()
        items = store.get("items", [])

        output: list[dict[str, Any]] = []
        for item in items:
            if mode_filter and item.get("mode") != mode_filter:
                continue
            output.append(self._to_public_item(item))

        output.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        return output

    def create_item(
        self,
        *,
        mode: str,
        feedback_text: str,
        origin_review_job_id: Optional[str] = None,
        origin_finding_id: Optional[str] = None,
        finding_snapshot: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        mode = self._normalize_mode(mode)
        text = (feedback_text or "").strip()
        if not text:
            raise ValueError("feedback_text is required")

        now = self._utc_now()
        item_id = str(uuid.uuid4())
        item: dict[str, Any] = {
            "id": item_id,
            "mode": mode,
            "source_type": "feedback",
            "origin_review_job_id": (origin_review_job_id or "").strip() or None,
            "origin_finding_id": (origin_finding_id or "").strip() or None,
            "finding_snapshot": finding_snapshot if isinstance(finding_snapshot, dict) else None,
            "feedback_text": text,
            "derived_instruction": None,
            "derivation_status": "queued",
            "activation_status": "pending_activation",
            "is_soft_disabled": False,
            "failure_reason": None,
            "created_at": now,
            "updated_at": now,
            "derived_at": None,
            "activated_at": None,
            "disabled_at": None,
            "disabled_reason": None,
            "version": 1,
        }

        with self._lock:
            store = self._read_store_no_lock()
            items = store.setdefault("items", [])
            items.append(item)
            self._write_store_no_lock(store)
            self._queue.append(item_id)
            self._ensure_worker_no_lock()

        return self._to_public_item(item)

    def update_item(self, item_id: str, feedback_text: str) -> dict[str, Any]:
        text = (feedback_text or "").strip()
        if not text:
            raise ValueError("feedback_text is required")

        with self._lock:
            store = self._read_store_no_lock()
            items = store.get("items", [])
            idx = self._find_item_index(items, item_id)
            if idx < 0:
                raise KeyError("Feedback item not found")

            current = items[idx]
            if current.get("is_soft_disabled"):
                raise ValueError("Disabled feedback cannot be edited")

            now = self._utc_now()
            current["feedback_text"] = text
            current["derived_instruction"] = None
            current["derivation_status"] = "queued"
            current["activation_status"] = "pending_activation"
            current["failure_reason"] = None
            current["updated_at"] = now
            current["derived_at"] = None
            current["activated_at"] = None
            current["version"] = int(current.get("version") or 1) + 1

            self._write_store_no_lock(store)
            self._queue.append(item_id)
            self._ensure_worker_no_lock()
            return self._to_public_item(current)

    def disable_item(self, item_id: str, reason: Optional[str] = None) -> dict[str, Any]:
        with self._lock:
            store = self._read_store_no_lock()
            items = store.get("items", [])
            idx = self._find_item_index(items, item_id)
            if idx < 0:
                raise KeyError("Feedback item not found")

            current = items[idx]
            now = self._utc_now()
            current["activation_status"] = "disabled"
            current["is_soft_disabled"] = True
            current["disabled_at"] = now
            current["disabled_reason"] = (reason or "User deleted from memory tab").strip()
            current["updated_at"] = now
            current["version"] = int(current.get("version") or 1) + 1
            self._write_store_no_lock(store)
            return self._to_public_item(current)

    def get_active_mode_instructions(self, mode: str) -> list[str]:
        mode = self._normalize_mode(mode)
        store = self._read_store()
        items = store.get("items", [])
        active: list[str] = []
        for item in items:
            if item.get("mode") != mode:
                continue
            if item.get("activation_status") != "active":
                continue
            instruction = (item.get("derived_instruction") or "").strip()
            if instruction:
                active.append(instruction)
        return active

    def _ensure_worker_no_lock(self) -> None:
        if self._worker_started:
            return
        worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_started = True
        worker.start()

    def _worker_loop(self) -> None:
        while True:
            next_id: Optional[str] = None
            with self._lock:
                if self._queue:
                    next_id = self._queue.popleft()
            if not next_id:
                time.sleep(0.2)
                continue
            self._process_item(next_id)

    def _process_item(self, item_id: str) -> None:
        with self._lock:
            store = self._read_store_no_lock()
            items = store.get("items", [])
            idx = self._find_item_index(items, item_id)
            if idx < 0:
                return

            item = items[idx]
            if item.get("is_soft_disabled"):
                return

            item["derivation_status"] = "processing"
            item["updated_at"] = self._utc_now()
            self._write_store_no_lock(store)

        # Simulated queued processing delay so UI can surface pending state.
        time.sleep(0.6)

        try:
            derived = self._derive_instruction(item)
        except Exception as exc:
            with self._lock:
                store = self._read_store_no_lock()
                items = store.get("items", [])
                idx = self._find_item_index(items, item_id)
                if idx < 0:
                    return
                current = items[idx]
                current["derivation_status"] = "failed"
                current["failure_reason"] = str(exc)
                current["updated_at"] = self._utc_now()
                current["version"] = int(current.get("version") or 1) + 1
                self._write_store_no_lock(store)
            return

        with self._lock:
            store = self._read_store_no_lock()
            items = store.get("items", [])
            idx = self._find_item_index(items, item_id)
            if idx < 0:
                return

            current = items[idx]
            if current.get("is_soft_disabled"):
                return

            now = self._utc_now()
            current["derived_instruction"] = derived
            current["derivation_status"] = "completed"
            current["activation_status"] = "active"
            current["is_soft_disabled"] = False
            current["failure_reason"] = None
            current["derived_at"] = now
            current["activated_at"] = now
            current["updated_at"] = now
            current["version"] = int(current.get("version") or 1) + 1
            self._write_store_no_lock(store)

    def _derive_instruction(self, item: dict[str, Any]) -> str:
        mode = item.get("mode") or "french_review"
        feedback_text = (item.get("feedback_text") or "").strip()
        snapshot = item.get("finding_snapshot") or {}

        issue = (snapshot.get("issue_detected") or "").strip()
        proposed = (snapshot.get("proposed_change") or "").strip()
        category = (snapshot.get("category") or "").strip()

        lower = feedback_text.lower()

        if any(token in lower for token in ["missed", "missing", "forgot", "didn't catch", "did not catch"]):
            core = "add a mandatory pass to catch similar missed issues across all pages"
        elif any(token in lower for token in ["wrong", "incorrect", "not correct", "false positive", "not an issue"]):
            core = "raise this type of issue only when there is explicit evidence in the report text"
        else:
            core = "apply this feedback consistently in future reviews"

        mode_label = {
            "comparison": "comparison",
            "english_review": "English review",
            "french_review": "French review",
        }.get(mode, mode)

        detail_segments: list[str] = []
        if category:
            detail_segments.append(f"category '{category}'")
        if issue:
            detail_segments.append(f"pattern '{issue}'")
        if proposed:
            detail_segments.append(f"preferred correction '{proposed}'")

        detail_text = ", ".join(detail_segments)
        user_feedback_summary = feedback_text[:220]

        if detail_text:
            return (
                f"For {mode_label} mode, {core}. Focus on {detail_text}. "
                f"User guidance: {user_feedback_summary}."
            )

        return f"For {mode_label} mode, {core}. User guidance: {user_feedback_summary}."

    def _to_public_item(self, item: dict[str, Any]) -> dict[str, Any]:
        effective_status = self._effective_status(item)
        payload = dict(item)
        payload["effective_status"] = effective_status
        return payload

    def _effective_status(self, item: dict[str, Any]) -> str:
        derivation_status = item.get("derivation_status")
        activation_status = item.get("activation_status")

        if derivation_status in {"queued", "processing"}:
            return "pending_derivation"
        if derivation_status == "failed":
            return "failed"
        if activation_status == "disabled":
            return "disabled"
        if activation_status == "pending_activation":
            return "pending_activation"
        if activation_status == "active":
            return "active"
        return "pending_derivation"

    def _find_item_index(self, items: list[dict[str, Any]], item_id: str) -> int:
        for idx, row in enumerate(items):
            if row.get("id") == item_id:
                return idx
        return -1

    def _normalize_mode(self, mode: str) -> str:
        normalized = (mode or "").strip().lower()
        if normalized not in VALID_PROMPT_MODES:
            raise ValueError("mode must be one of: comparison, french_review, english_review")
        return normalized

    def _read_store(self) -> dict[str, Any]:
        with self._lock:
            return self._read_store_no_lock()

    def _read_store_no_lock(self) -> dict[str, Any]:
        if not self._file_path.exists():
            return self._empty_store()
        try:
            parsed = json.loads(self._file_path.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                return self._empty_store()
            items = parsed.get("items")
            if not isinstance(items, list):
                parsed["items"] = []
            return parsed
        except Exception:
            return self._empty_store()

    def _write_store_no_lock(self, payload: dict[str, Any]) -> None:
        tmp_path = self._file_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._file_path)

    def _empty_store(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "items": [],
        }

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
