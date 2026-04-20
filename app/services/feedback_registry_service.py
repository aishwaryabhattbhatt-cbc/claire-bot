# Structured feedback registry service for false alarms, missed issues, and corrections.

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from app.core.config import get_settings

VALID_PROMPT_MODES = {"comparison", "french_review", "english_review"}
VALID_FEEDBACK_TYPES = {"false_alarm", "missed_issue", "correction"}
VALID_STATUSES = {"pending_review", "active", "disabled"}
VALID_PRIORITIES = {"low", "medium", "high"}
_GENERIC_CATEGORY = "general"
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "beyond", "but", "by", "do", "does",
    "for", "from", "has", "have", "if", "in", "into", "is", "it", "likely", "not", "of",
    "on", "or", "should", "so", "that", "the", "their", "them", "this", "to", "was", "when",
    "with", "within", "without", "consider", "considered", "considering", "finding", "showed",
}


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

    def delete_item(self, item_id: str) -> dict[str, Any]:
        """Permanently remove an item from the store."""
        with self._lock:
            store = self._read_store_no_lock()
            items = store.get("items", [])
            idx = self._find_item_index(items, item_id)
            if idx < 0:
                raise KeyError("Feedback item not found")
            removed = dict(items[idx])
            store["items"] = [item for item in items if item.get("id") != item_id]
            self._write_store_no_lock(store)
            return removed

    def get_active_mode_directives(self, mode: str, max_items: int = 30) -> dict[str, list[str]]:
        items_sorted = self._get_ranked_active_items(mode, max_items=max_items)

        directives = {
            "false_alarms": [],
            "missed_issues": [],
            "corrections": [],
        }

        for item in items_sorted:
            kind = item.get("feedback_type")
            category = (item.get("finding_category") or _GENERIC_CATEGORY).strip()
            pattern = (item.get("issue_pattern") or "").strip()
            reason = (item.get("reason") or "").strip()
            expected = (item.get("expected_finding") or "").strip()

            if kind == "false_alarm":
                # Truncate long user-written patterns to a concise form for prompt injection
                short_pattern = pattern[:120] + "…" if len(pattern) > 120 else pattern
                directives["false_alarms"].append(short_pattern)
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

    def apply_false_alarm_filters(self, findings: list[dict[str, Any]], mode: str) -> tuple[list[dict[str, Any]], int]:
        false_alarm_items = [
            item
            for item in self._get_ranked_active_items(mode)
            if item.get("feedback_type") == "false_alarm"
        ]
        if not false_alarm_items:
            return findings, 0

        filtered: list[dict[str, Any]] = []
        suppressed_count = 0
        for finding in findings:
            if self._matches_any_false_alarm(false_alarm_items, finding):
                suppressed_count += 1
                continue
            filtered.append(finding)
        return filtered, suppressed_count

    def apply_missed_issue_injections(
        self, findings: list[dict[str, Any]], mode: str
    ) -> tuple[list[dict[str, Any]], int]:
        """Inject expected findings for missed_issue entries not already covered."""
        missed_items = [
            item
            for item in self._get_ranked_active_items(mode)
            if item.get("feedback_type") == "missed_issue"
        ]
        if not missed_items:
            return findings, 0

        injected_count = 0
        result = list(findings)
        for item in missed_items:
            expected = (item.get("expected_finding") or "").strip()
            pattern = (item.get("issue_pattern") or "").strip()
            if not expected and not pattern:
                continue
            norm_expected = self._normalize_match_text(expected or pattern)
            already_present = any(
                self._text_matches_pattern(
                    norm_expected,
                    self._normalize_match_text(
                        f.get("issue_detected") or f.get("issue") or ""
                    ),
                )
                for f in result
            )
            if not already_present:
                category = (item.get("finding_category") or "general").strip()
                injected: dict[str, Any] = {
                    "page_number": 0,
                    "language": "general",
                    "category": category,
                    "finding_category": category,
                    "issue_detected": expected or pattern,
                    "issue": expected or pattern,
                    "proposed_change": expected or pattern,
                    "source": "feedback_registry",
                }
                result.append(injected)
                injected_count += 1
        return result, injected_count

    def apply_correction_patches(
        self, findings: list[dict[str, Any]], mode: str
    ) -> tuple[list[dict[str, Any]], int]:
        """Patch findings whose text matches a correction pattern with the expected wording."""
        correction_items = [
            item
            for item in self._get_ranked_active_items(mode)
            if item.get("feedback_type") == "correction"
        ]
        if not correction_items:
            return findings, 0

        patched_count = 0
        result: list[dict[str, Any]] = []
        for finding in findings:
            patched = False
            for item in correction_items:
                pattern = self._normalize_match_text(item.get("issue_pattern") or "")
                expected = (item.get("expected_finding") or "").strip()
                if not pattern or not expected:
                    continue
                expected_category = (item.get("finding_category") or "").strip().lower()
                finding_category = (
                    finding.get("category") or finding.get("finding_category") or ""
                ).strip().lower()
                if (
                    expected_category
                    and expected_category != _GENERIC_CATEGORY
                    and finding_category
                    and expected_category != finding_category
                ):
                    continue
                candidate_text = self._normalize_match_text(
                    f"{finding.get('issue_detected') or finding.get('issue') or ''} "
                    f"{finding.get('proposed_change') or ''}"
                )
                if self._text_matches_pattern(pattern, candidate_text):
                    f = dict(finding)
                    if "issue_detected" in f:
                        f["issue_detected"] = expected
                    if "issue" in f:
                        f["issue"] = expected
                    f["proposed_change"] = expected
                    f["source"] = f.get("source", "llm") + "+feedback_registry"
                    result.append(f)
                    patched_count += 1
                    patched = True
                    break
            if not patched:
                result.append(finding)
        return result, patched_count

    def _get_ranked_active_items(self, mode: str, max_items: int = 30) -> list[dict[str, Any]]:
        normalized_mode = self._normalize_mode(mode)
        items = self.list_items(mode=normalized_mode, status="active")

        priority_rank = {"high": 0, "medium": 1, "low": 2}
        items_sorted = sorted(
            items,
            key=lambda row: (
                priority_rank.get((row.get("priority") or "medium").lower(), 1),
                row.get("updated_at") or "",
            ),
        )
        items_sorted.reverse()
        return items_sorted[: max(1, int(max_items or 30))]

    def _matches_any_false_alarm(self, false_alarm_items: list[dict[str, Any]], finding: dict[str, Any]) -> bool:
        for item in false_alarm_items:
            if self._matches_false_alarm(item, finding):
                return True
        return False

    def _matches_false_alarm(self, item: dict[str, Any], finding: dict[str, Any]) -> bool:
        pattern = self._normalize_match_text(item.get("issue_pattern") or "")
        if not pattern:
            return False

        expected_category = (item.get("finding_category") or "").strip().lower()
        finding_category = (finding.get("category") or finding.get("finding_category") or "").strip().lower()
        if expected_category and expected_category != _GENERIC_CATEGORY and finding_category and expected_category != finding_category:
            return False

        candidates = [
            self._normalize_match_text(finding.get("issue_detected") or finding.get("issue") or ""),
            self._normalize_match_text(finding.get("proposed_change") or ""),
            self._normalize_match_text(
                f"{finding.get('issue_detected') or finding.get('issue') or ''} {finding.get('proposed_change') or ''}"
            ),
        ]
        return any(self._text_matches_pattern(pattern, candidate) for candidate in candidates if candidate)

    def _text_matches_pattern(self, pattern: str, candidate: str) -> bool:
        if not pattern or not candidate:
            return False

        if len(pattern) >= 24 and (pattern in candidate or candidate in pattern):
            return True

        pattern_tokens = self._meaningful_tokens(pattern)
        candidate_tokens = self._meaningful_tokens(candidate)
        if not pattern_tokens or not candidate_tokens:
            return False

        overlap = len(pattern_tokens & candidate_tokens) / max(len(pattern_tokens), 1)
        ratio = SequenceMatcher(None, pattern, candidate).ratio()
        return overlap >= 0.6 or (overlap >= 0.45 and ratio >= 0.72)

    def _meaningful_tokens(self, text: str) -> set[str]:
        tokens = set()
        for token in text.split():
            if token in _STOPWORDS:
                continue
            if len(token) >= 4 or any(ch.isdigit() for ch in token) or "%" in token:
                tokens.add(token)
        return tokens

    def _normalize_match_text(self, text: str) -> str:
        normalized = (text or "").strip().lower()
        normalized = normalized.replace("’", "'")
        normalized = re.sub(r"[^a-z0-9%\s']+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

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
