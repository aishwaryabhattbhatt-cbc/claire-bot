import json
from typing import List, Optional, Dict, Any

from openai import OpenAI

from app.core.config import get_settings
from app.models import ParsedDocument
from app.prompts.review_prompt import build_review_prompt


class OpenAIReviewService:
    """OpenAI-based review engine"""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI review")

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = self._resolve_model(settings.openai_model)

    def review_document(
        self,
        report: ParsedDocument,
        benchmark: Optional[ParsedDocument] = None,
        instructions_text: Optional[str] = None,
        reference_context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        prompt = build_review_prompt(report, benchmark, instructions_text=instructions_text, reference_context=reference_context)

        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "review_findings",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "findings": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "page_number": {"type": "integer"},
                                        "language": {"type": "string"},
                                        "issue_detected": {"type": "string"},
                                        "proposed_change": {"type": "string"},
                                    },
                                    "required": [
                                        "page_number",
                                        "language",
                                        "issue_detected",
                                        "proposed_change",
                                    ],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["findings"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                }
            },
        )

        text = _extract_response_text(response)

        try:
            parsed = _parse_json_issues(text)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

        return []

    def _resolve_model(self, configured_model: str) -> str:
        """Resolve model name. If 'auto', pick best available from a preferred list."""
        if configured_model and configured_model.lower() != "auto":
            return configured_model

        preferred_models = [
            "gpt-4.1",
            "gpt-4o",
            "gpt-4o-mini",
        ]

        try:
            model_page = self.client.models.list()
            available = {m.id for m in model_page.data}
            for model in preferred_models:
                if model in available:
                    return model
        except Exception:
            pass

        # Safe fallback
        return "gpt-4o-mini"


def _extract_response_text(response) -> str:
    try:
        # Standard responses API shape
        return response.output_text
    except Exception:
        pass

    try:
        # Fallback for raw structured output
        return response.output[0].content[0].text
    except Exception:
        return ""


def _parse_json_issues(text: str):
    cleaned = (text or "").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    data = json.loads(cleaned)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("findings", "issues", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []
