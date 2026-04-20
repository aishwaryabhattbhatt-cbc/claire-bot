"""Helper script to rewrite instructions-related files from scratch."""
import json
from pathlib import Path

BASE = Path("/Users/aishwaryabhattbhatt/Desktop/CBC/ClaireBot")

# ---------------------------------------------------------------------------
# 1. app/prompts/review_prompt.py
# ---------------------------------------------------------------------------
REVIEW_PROMPT = '''\
from typing import List, Optional

from app.models import ParsedDocument


def build_review_prompt(
    report: ParsedDocument,
    benchmark: Optional[ParsedDocument] = None,
    instructions_text: Optional[str] = None,
    reference_context: Optional[str] = None,
    prompt_mode: Optional[str] = None,
) -> str:
    """
    Build the LLM review prompt from the provided instructions and document content.

    Args:
        report: Parsed French report document
        benchmark: Parsed English benchmark document (optional, comparison mode only)
        instructions_text: Custom instructions entered/saved by the user
        reference_context: Extracted text from reference documents
        prompt_mode: "comparison" or "french_review"

    Returns:
        Prompt string to send to the LLM
    """
    comparison_mode = benchmark is not None
    rules_text = (instructions_text or "").strip()

    header_parts: List[str] = []

    if rules_text:
        header_parts.append(f"Instructions:\\n{rules_text}\\n")

    header_parts.append(
        "Return output as JSON ONLY. Use an object with key \'findings\' containing a list of issues. "
        "Each issue must contain: page_number (int), language (French|English), "
        "issue_detected (string), proposed_change (string). "
        "Return NO explanations outside the JSON.\\n"
    )

    report_block = [
        f"Report Language: {report.metadata.language}",
        f"Total Pages: {report.metadata.total_pages}",
        "Report Pages:",
    ]
    for page in report.pages:
        text_snippet = page.text.strip().replace("\\n", " ")
        if len(text_snippet) > 2000:
            text_snippet = text_snippet[:2000] + "..."
        report_block.append(f"Page {page.page_number}: {text_snippet}")

    benchmark_block: List[str] = []
    if comparison_mode and benchmark is not None:
        benchmark_block = [
            "\\nBenchmark (English) Pages:",
            f"Total Pages: {benchmark.metadata.total_pages}",
        ]
        for page in benchmark.pages:
            text_snippet = page.text.strip().replace("\\n", " ")
            if len(text_snippet) > 2000:
                text_snippet = text_snippet[:2000] + "..."
            benchmark_block.append(f"Page {page.page_number}: {text_snippet}")

    reference_block: List[str] = []
    if reference_context and reference_context.strip():
        reference_block = [
            "\\n\\nReference Standards:",
            reference_context.strip(),
        ]

    return (
        "\\n".join(header_parts)
        + "\\n"
        + "\\n".join(report_block + benchmark_block + reference_block)
    )
'''

# ---------------------------------------------------------------------------
# 2. app/services/instructions_service.py
# ---------------------------------------------------------------------------
INSTRUCTIONS_SERVICE = '''\
import json
from pathlib import Path
from typing import Dict

from app.core.config import get_settings


class InstructionsService:
    """Read/write review instructions used by the LLM prompt."""

    def __init__(self) -> None:
        settings = get_settings()
        self._file_path = Path(settings.processed_dir) / "review_instructions.json"
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def get_instructions(self) -> Dict[str, str]:
        """Return saved instructions, or empty strings if none saved yet."""
        if not self._file_path.exists():
            return self._empty_payload()

        raw = self._file_path.read_text(encoding="utf-8").strip()
        if not raw:
            return self._empty_payload()

        try:
            parsed = json.loads(raw)
            return {
                "comparison_instructions": (parsed.get("comparison_instructions") or "").strip(),
                "french_review_instructions": (parsed.get("french_review_instructions") or "").strip(),
            }
        except Exception:
            return self._empty_payload()

    def save_instructions(
        self,
        comparison_instructions: str,
        french_review_instructions: str,
    ) -> Dict[str, str]:
        """Persist instructions to disk."""
        payload = {
            "comparison_instructions": (comparison_instructions or "").strip(),
            "french_review_instructions": (french_review_instructions or "").strip(),
        }
        self._write_payload(payload)
        return payload

    def _empty_payload(self) -> Dict[str, str]:
        return {
            "comparison_instructions": "",
            "french_review_instructions": "",
        }

    def _write_payload(self, payload: Dict[str, str]) -> None:
        self._file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
'''

# ---------------------------------------------------------------------------
# 3. data/processed/review_instructions.json
# ---------------------------------------------------------------------------
INSTRUCTIONS_JSON = {
    "comparison_instructions": "",
    "french_review_instructions": "",
}

# ---------------------------------------------------------------------------
# Write everything
# ---------------------------------------------------------------------------
(BASE / "app/prompts/review_prompt.py").write_text(REVIEW_PROMPT, encoding="utf-8")
print("✓ app/prompts/review_prompt.py")

(BASE / "app/services/instructions_service.py").write_text(INSTRUCTIONS_SERVICE, encoding="utf-8")
print("✓ app/services/instructions_service.py")

(BASE / "data/processed/review_instructions.json").write_text(
    json.dumps(INSTRUCTIONS_JSON, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("✓ data/processed/review_instructions.json")

print("\nAll files written successfully.")
