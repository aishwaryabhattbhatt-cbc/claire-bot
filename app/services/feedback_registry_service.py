# Structured feedback registry service for false alarms, missed issues, and corrections.

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.config import get_settings

VALID_PROMPT_MODES = {"comparison", "french_review", "english_review"}
VALID_FEEDBACK_TYPES = {"false_alarm", "missed_issue", "correction"}
VALID_STATUSES = {"pending_review", "active", "disabled"}
VALID_PRIORITIES = {"low", "medium", "high"}


class FeedbackRegistryService:
    """Persist and query structured feedback records used to guide future prompts."""

    def __init__(self) -> None:
        settings = get_settings()
        file_name = getattr(settings, "feedback_registry_filename", "review_feedback_registry.json")
        self._file_path = Path(settings.processed_dir) / file_name
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def list_items(
        self,
        mode: Optional[str] = None,
        feedback_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        mode_filter = self._normalize_mode(mode) if mode else None
        type_filter = self._normalize_feedback_type(feedback_type) if feedback_type else None
        status_filter = self._normalize_status(status) if status else None

        store = self._read_store()
        items = store.get("items", [])
        output: list[dict[str, Any]] = []
        for item in items:
            if mode_filter and item.get("mode") != mode_filter:
                continue
            if type_filter and item.get("feedback_type") != type_filter:
                continue
            if status_filter and item.get("status") != status_filter:
                continue
            output.append(dict(item))

        output.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        return output

    def create_item(
        self,
        *,
        mode: str,
        feedback_type: str,
        issue_pattern: str,
        reason: str,
        finding_category: Optional[str] = None,
        expected_finding: Optional[str] = None,
        original_finding: Optional[dict[str, Any]] = None,
        priority: str = "medium",
        created_by: Optional[str] = None,
    ) -> dict[str, Any]:
        normalized_mode = self._normalize_mode(mode)
        normalized_type = self._normalize_feedback_type(feedback_type)
        normalized_priority = self._normalize_priority(priority)
        text_pattern = (issue_pattern or "").strip()
        text_reason = (reason or "").strip()

        if not text_pattern:
            raise ValueError("issue_pattern is required")
        if not text_reason:
            raise ValueError("reason is required")
        if normalized_type in {"missed_issue", "correction"} and not (expected_finding or "").strip():
            raise ValueError("expected_finding is required for missed_issue and correction")

        now = self._utc_now()
        item: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "mode": normalized_mode,
            "feedback_type": normalized_type,
            "finding_category": (finding_category or "").strip() or None,
            "issue_pattern": text_pattern,
            "reason": text_reason,
            "expected_finding": (expected_finding or "").strip() or None,
            "original_finding": original_finding if isinstance(original_finding, dict) else None,
            "status": "active",
            "priority": normalized_priority,
            "created_by": (created_by or "").strip() or None,
            "disabled_reason": None,
            "created_at": now,
            "updated_at": now,
            "version": 1,
        }

        with self._lock:
            store = self._read_store_no_lock()
            store.setdefault("items", []).append(item)
            self._write_store_no_lock(store)

        return dict(item)

    def update_item(
        self,
        item_id: str,
        *,
        mode: Optional[str] = None,
        feedback_type: Optional[str] = None,
        finding_category: Optional[str] = None,
        issue_pattern: Optional[str] = None,
        reason: Optional[str] = None,
        expected_finding: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict[str, Any]:
        with self._lock:
            store = self._read_store_no_lock()
            items = store.get("items", [])
            idx = self._find_item_index(items, item_id)
            if idx < 0:
                raise KeyError("Feedback item not found")

            current = items[idx]
            next_mode = self._normalize_mode(mode) if mode is not None else current.get("mode")
            next_type = self._normalize_feedback_type(feedback_type) if feedback_type is not None else current.get("feedback_type")
            next_status = self._normalize_status(status) if status is not None else current.get("status")
            next_priority = self._normalize_priority(priority) if priority is not None else current.get("priority")

            if issue_pattern is not None:
                issue_pattern = issue_pattern.strip()
                if not issue_pattern:
                    raise ValueError("issue_pattern cannot be empty")
                current["issue_pattern"] = issue_pattern

            if reason is not None:
                reason = reason.strip()
                if not reason:
                    raise ValueError("reason cannot be empty")
                current["reason"] = reason

            if finding_category is not None:
                current["finding_category"] = finding_category.strip() or None

            if expected_finding is not None:
                current["expected_finding"] = expected_finding.strip() or None

            current["mode"] = next_mode
            current["feedback_type"] = next_type
            current["status"] = next_status
            current["priority"] = next_priority

            if next_type in {"missed_issue", "correction"} and not (current.get("expected_finding") or "").strip():
                raise ValueError("expected_finding is required for missed_issue and correction")

            current["updated_at"] = self._utc_now()
            current["version"] = int(current.get("version") or 1) + 1
            self._write_store_no_lock(store)
            return dict(current)

    def disable_item(self, item_id: str, reason: Optional[str] = None) -> dict[str, Any]:
        with self._lock:
            store = self._read_store_no_lock()
            items = store.get("items", [])
            idx = self._find_item_index(items, item_id)
            if idx < 0:
                raise KeyError("Feedback item not found")

            current = items[idx]
            current["status"] = "disabled"
            current["disabled_reason"] = (reason or "User disabled entry").strip()
            current["updated_at"] = self._utc_now()
            current["version"] = int(current.get("version") or 1) + 1
            self._write_store_no_lock(store)
            return dict(current)

    def get_active_mode_directives(self, mode: str, max_items: int = 30) -> dict[str, list[str]]:
        normalized_mode = self._normalize_mode(mode)
        items = self.list_items(mode=normalized_mode, status="active")

        # priority ordering: high > medium > low, then newest first
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        items_sorted = sorted(
            items,
            key=lambda row: (
                priority_rank.get((row.get("priority") or "medium").lower(), 1),
                row.get("updated_at") or "",
            ),
        )
        items_sorted.reverse()
        items_sorted = items_sorted[: max(1, int(max_items or 30))]

        directives = {
            "false_alarms": [],
            "missed_issues": [],
            "corrections": [],
        }

        for item in items_sorted:
            kind = item.get("feedback_type")
            category = (item.get("finding_category") or "general").strip()
            pattern = (item.get("issue_pattern") or "").strip()
            reason = (item.get("reason") or "").strip()
            expected = (item.get("expected_finding") or "").strip()

            if kind == "false_alarm":
                directives["false_alarms"].append(
                    f"Avoid flagging '{pattern}' in category '{category}' when context does not provide explicit evidence. Reason: {reason}."
                )
            elif kind == "missed_issue":
                base = f"Always check for possible missing issue pattern '{pattern}' in category '{category}'."
                if expected:
                    base += f" Preferred finding style: {expected}."
                base += f" Reason: {reason}."
                directives["missed_issues"].append(base)
            elif kind == "correction":
                base = f"For pattern '{pattern}' in category '{category}', prefer corrected wording/logic."
                if expected:
                    base += f" Corrected form: {expected}."
                base += f" Reason: {reason}."
                directives["corrections"].append(base)

        return directives

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

    def _normalize_feedback_type(self, feedback_type: str) -> str:
        normalized = (feedback_type or "").strip().lower()
        if normalized not in VALID_FEEDBACK_TYPES:
            raise ValueError("feedback_type must be one of: false_alarm, missed_issue, correction")
        return normalized

    def _normalize_status(self, status: str) -> str:
        normalized = (status or "").strip().lower()
        if normalized not in VALID_STATUSES:
            raise ValueError("status must be one of: pending_review, active, disabled")
        return normalized

    def _normalize_priority(self, priority: str) -> str:
        normalized = (priority or "").strip().lower() or "medium"
        if normalized not in VALID_PRIORITIES:
            raise ValueError("priority must be one of: low, medium, high")
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
        return {"schema_version": 1, "items": []}

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
