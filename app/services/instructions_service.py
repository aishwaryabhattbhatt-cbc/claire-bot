import json
from pathlib import Path
from typing import Dict

from app.core.config import get_settings


DEFAULT_FRENCH_INSTRUCTIONS = """Role: You are Clairebot, an expert editor for French OTM reports.
Task: Review French reports with strict language purity and MTM/OTM standards.
Output: Return JSON only with object key 'findings'. Each finding must include:
- page_number (int)
- language (French|English)
- issue_detected (string)
- proposed_change (string)

French review rules:
- No English words in French text/graphics.
- Ensure proper French accents and approved terminology.
- Age references should use 'ans' (e.g., '18-34 ans').
- Check sentence casing and acronym first-definition consistency.
- Footnote markers must have matching footnotes on the same page.
- In French narrative text, use numbers in words except percentages, hours, and ages.
- Verify methodology sample wording consistency (canadiens/francophones/anglophones).
- Verify summary values match body values.
"""


DEFAULT_ENGLISH_INSTRUCTIONS = """Role: You are Clairebot, an expert editor for English MTM reports.
Task: Review English reports for data, structure, and consistency.
Output: Return JSON only with object key 'findings'. Each finding must include:
- page_number (int)
- language (French|English)
- issue_detected (string)
- proposed_change (string)

English review rules:
- Validate data consistency across pages.
- Verify summary values match detailed pages.
- Check methodology wording and target sample consistency.
- Check terminology and structural clarity.
- Ensure footnote markers and footnote text align.
- When benchmark is provided in comparison mode, English report is source of truth.
"""


class InstructionsService:
    """Read/write review instructions used by the LLM prompt."""

    def __init__(self) -> None:
        settings = get_settings()
        self._file_path = Path(settings.processed_dir) / "review_instructions.json"
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def get_instructions(self) -> Dict[str, str]:
        if not self._file_path.exists():
            payload = self._default_payload()
            self._write_payload(payload)
            return payload

        raw = self._file_path.read_text(encoding="utf-8").strip()
        if not raw:
            payload = self._default_payload()
            self._write_payload(payload)
            return payload

        # Backward compatibility: previously stored as plain text
        if not raw.startswith("{"):
            payload = {
                "english_instructions": raw,
                "french_instructions": raw,
            }
            self._write_payload(payload)
            return payload

        try:
            parsed = json.loads(raw)
            english = (parsed.get("english_instructions") or "").strip()
            french = (parsed.get("french_instructions") or "").strip()
            payload = {
                "english_instructions": english or DEFAULT_ENGLISH_INSTRUCTIONS,
                "french_instructions": french or DEFAULT_FRENCH_INSTRUCTIONS,
            }
            self._write_payload(payload)
            return payload
        except Exception:
            payload = self._default_payload()
            self._write_payload(payload)
            return payload

    def save_instructions(
        self,
        english_instructions: str,
        french_instructions: str,
    ) -> Dict[str, str]:
        english = (english_instructions or "").strip() or DEFAULT_ENGLISH_INSTRUCTIONS
        french = (french_instructions or "").strip() or DEFAULT_FRENCH_INSTRUCTIONS
        payload = {
            "english_instructions": english,
            "french_instructions": french,
        }
        self._write_payload(payload)
        return payload

    def _default_payload(self) -> Dict[str, str]:
        return {
            "english_instructions": DEFAULT_ENGLISH_INSTRUCTIONS,
            "french_instructions": DEFAULT_FRENCH_INSTRUCTIONS,
        }

    def _write_payload(self, payload: Dict[str, str]) -> None:
        self._file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
