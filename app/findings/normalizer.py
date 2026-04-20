# Findings normalizer — deduplicates and sorts a list of raw finding dicts.

from typing import Any, List


def normalize_findings(findings: List[Any]) -> List[Any]:
    """
    Deduplicate findings by (page_number, finding_category, issue) and
    return results sorted ascending by page_number.

    TODO: accept List[Finding] once the rest of the codebase uses the
          Finding model instead of raw dicts.
    """
    seen: set = set()
    unique: List[Any] = []

    for f in findings:
        # Support both dict-style and object-style findings
        if isinstance(f, dict):
            key = (
                f.get("page_number"),
                f.get("finding_category") or f.get("category"),
                f.get("issue") or f.get("issue_detected"),
            )
        else:
            key = (
                getattr(f, "page_number", None),
                getattr(f, "finding_category", None),
                getattr(f, "issue", None),
            )

        if key in seen:
            continue
        seen.add(key)
        unique.append(f)

    def _sort_key(f: Any) -> int:
        if isinstance(f, dict):
            return int(f.get("page_number") or 0)
        return int(getattr(f, "page_number", 0) or 0)

    return sorted(unique, key=_sort_key)
