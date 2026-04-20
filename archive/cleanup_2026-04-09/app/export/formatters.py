# Finding row formatters for export — converts a finding dict/object to a flat row.

from typing import Any, List


def finding_to_row(finding: Any) -> List[Any]:
    """
    Convert a finding (dict or Finding model instance) to an ordered list of
    field values suitable for writing to a spreadsheet row:
    [page_number, language, category, issue_detected, proposed_change, source]
    """
    if isinstance(finding, dict):
        return [
            finding.get("page_number", ""),
            finding.get("language", ""),
            finding.get("category", "") or finding.get("finding_category", ""),
            finding.get("issue_detected", "") or finding.get("issue", ""),
            finding.get("proposed_change", ""),
            finding.get("source", ""),
        ]
    # Pydantic model or dataclass
    return [
        getattr(finding, "page_number", ""),
        getattr(finding, "language", ""),
        getattr(finding, "finding_category", "") or getattr(finding, "category", ""),
        getattr(finding, "issue", "") or getattr(finding, "issue_detected", ""),
        getattr(finding, "proposed_change", ""),
        getattr(finding, "source", ""),
    ]
