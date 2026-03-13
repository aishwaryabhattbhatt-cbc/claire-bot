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
            }
        except Exception:
            return self._empty_payload()

    def save_instructions(
        self,
        comparison_instructions: str,
        french_instructions: str,
    ) -> Dict[str, str]:
        payload = {
            "comparison_instructions": (comparison_instructions or "").strip(),
            "french_instructions": (french_instructions or "").strip(),
        }
        self._write_payload(payload)
        return payload

    def _empty_payload(self) -> Dict[str, str]:
        return {
            "comparison_instructions": "",
            "french_instructions": "",
        }

    def _write_payload(self, payload: Dict[str, str]) -> None:
        self._file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
