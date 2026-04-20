# Finding — the canonical Pydantic model for a single review finding.

from pydantic import BaseModel


class Finding(BaseModel):
    """A single quality-review finding produced by a deterministic check or LLM."""

    page_number: int
    language: str
    finding_category: str
    issue: str
    proposed_change: str
    source: str = "deterministic"
