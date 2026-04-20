# Prompt construction and saved-instruction management
# (InstructionsService moved from app/services/instructions_service.py;
#  build_prompt reads app/prompts/*.md templates with {{placeholder}} syntax).

import json
from pathlib import Path
from typing import Dict, Optional

from app.core.config import get_settings


# ─────────────────────────────────────────────────────────────────────────────
# build_prompt — template-file-based prompt builder
# ─────────────────────────────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_MODE_TO_FILE = {
    "french_review": "french_review.md",
    "english_review": "english_review.md",
    "comparison": "comparison.md",
}


def get_mode_template(mode: str) -> str:
    """Return the raw markdown template text for a review mode."""
    normalized_mode = (mode or "french_review").strip().lower()
    template_file = _PROMPTS_DIR / _MODE_TO_FILE.get(normalized_mode, "french_review.md")
    if template_file.exists():
        return template_file.read_text(encoding="utf-8")
    return "Review the following document:\n\n{{document_content}}"


def build_prompt(
    mode: str,
    document_content: str,
    reference_content: str = "",
) -> str:
    """
    Read the .md template for *mode*, substitute {{document_content}} and
    {{reference_content}}, and return the assembled prompt string.
    """
    template = get_mode_template(mode)

    result = template.replace("{{document_content}}", document_content)
    result = result.replace("{{reference_content}}", reference_content)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# InstructionsService — persists user-edited review instructions to disk
# ─────────────────────────────────────────────────────────────────────────────

class InstructionsService:
    """Read/write review instructions used by the LLM prompt."""

    def __init__(self) -> None:
        settings = get_settings()
        self._file_path = Path(settings.processed_dir) / "review_instructions.json"
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def get_instructions(self) -> Dict[str, str]:
        if not self._file_path.exists():
            return self._empty_payload()

        raw = self._file_path.read_text(encoding="utf-8").strip()
        if not raw or not raw.startswith("{"):
            return self._empty_payload()

        try:
            parsed = json.loads(raw)
            return {
                "comparison_instructions": (parsed.get("comparison_instructions") or "").strip(),
                "french_instructions": (parsed.get("french_instructions") or "").strip(),
                "english_instructions": (parsed.get("english_instructions") or "").strip(),
            }
        except Exception:
            return self._empty_payload()

    def save_instructions(
        self,
        comparison_instructions: str,
        french_instructions: str,
        english_instructions: str,
    ) -> Dict[str, str]:
        payload = {
            "comparison_instructions": (comparison_instructions or "").strip(),
            "french_instructions": (french_instructions or "").strip(),
            "english_instructions": (english_instructions or "").strip(),
        }
        self._write_payload(payload)
        return payload

    def update_instructions(
        self,
        comparison_instructions: Optional[str] = None,
        french_instructions: Optional[str] = None,
        english_instructions: Optional[str] = None,
    ) -> Dict[str, str]:
        current = self.get_instructions()
        payload = {
            "comparison_instructions": (
                current["comparison_instructions"]
                if comparison_instructions is None
                else (comparison_instructions or "").strip()
            ),
            "french_instructions": (
                current["french_instructions"]
                if french_instructions is None
                else (french_instructions or "").strip()
            ),
            "english_instructions": (
                current["english_instructions"]
                if english_instructions is None
                else (english_instructions or "").strip()
            ),
        }
        self._write_payload(payload)
        return payload

    def reset_instructions(self, mode: str = "all") -> Dict[str, str]:
        mode = (mode or "all").strip().lower()
        current = self.get_instructions()

        if mode == "comparison":
            payload = {
                "comparison_instructions": "",
                "french_instructions": current["french_instructions"],
                "english_instructions": current["english_instructions"],
            }
        elif mode == "french":
            payload = {
                "comparison_instructions": current["comparison_instructions"],
                "french_instructions": "",
                "english_instructions": current["english_instructions"],
            }
        elif mode == "english":
            payload = {
                "comparison_instructions": current["comparison_instructions"],
                "french_instructions": current["french_instructions"],
                "english_instructions": "",
            }
        else:
            payload = self._empty_payload()

        self._write_payload(payload)
        return payload

    def _empty_payload(self) -> Dict[str, str]:
        return {
            "comparison_instructions": "",
            "french_instructions": "",
            "english_instructions": "",
        }

    def _write_payload(self, payload: Dict[str, str]) -> None:
        self._file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
