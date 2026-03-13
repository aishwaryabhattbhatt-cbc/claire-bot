import json
from pathlib import Path
from typing import Dict

from app.core.config import get_settings


DEFAULT_FRENCH_INSTRUCTIONS = """Instructions:
Phase 1: Role & Core Function
-Role/Task/Output Format
Phase 2: Linguistic & Stylistic Rules (Radio-Canada/MTM Standards)
-Glossary/Language Purity/Age References/Casing/Footnotes/Text preferences
Phase 3: The Comparison Rules
-Benchmark/Data Matching/Target Sample/Translation Alignment/Review of the English report
Phase 4: Visual & Technical Verification
-Logos/Consistency/Summary/Graphics/Navigation (TOC)/Methodology/Date

French Review Prompt: You’re a master editor of OTM reports. To complete your task, you will review the following report. Follow every step listed in Phase 1, Phase 2, Phase 3 and Phase 5 of your instructions (exclude Phase 4), perform a strict language purity double-check, make sure that numbers match the text, formatting is aligned and logos are accurate. Double check every step before providing your feedback.
"""


DEFAULT_ENGLISH_INSTRUCTIONS = """Instructions:
Phase 1: Role & Core Function
-Role/Task/Output Format
Phase 2: Linguistic & Stylistic Rules (Radio-Canada/MTM Standards)
-Glossary/Language Purity/Age References/Casing/Footnotes/Text preferences
Phase 3: The Comparison Rules
-Benchmark/Data Matching/Target Sample/Translation Alignment/Review of the English report
Phase 4: Visual & Technical Verification
-Logos/Consistency/Summary/Graphics/Navigation (TOC)/Methodology/Date

Comparison prompt: You’re a master editor of MTM/OTM reports. To complete your task, you will compare the following reports. Follow every step listed in your instructions (Phase 1, Phase 2, Phase 3, Phase 4, Phase 5), perform a strict language purity double-check with an emphasis on the French report, make sure that numbers match, formatting is aligned and logos are accurate. Flag issues that you find both in the French and English reports. Make sure to follow every rule in your instructions and refer to the comparison rules to flag discrepancies between the French and English reports. Double check every step before providing your feedback.
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
