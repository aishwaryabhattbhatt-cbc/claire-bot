import json
from typing import List, Optional, Dict, Any

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from app.core.config import get_settings
from app.models import ParsedDocument
from app.prompts.review_prompt import build_review_prompt


class GeminiReviewService:
    """Gemini-based review engine"""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required for Gemini review")

        genai.configure(api_key=settings.google_api_key)
        self._generation_config = GenerationConfig(
            temperature=settings.llm_temperature,
            response_mime_type="application/json",
        )
        self.model = genai.GenerativeModel(
            settings.gemini_model,
            generation_config=self._generation_config,
        )

    def review_document(
        self,
        report: ParsedDocument,
        benchmark: Optional[ParsedDocument] = None,
        instructions_text: Optional[str] = None,
        reference_context: Optional[str] = None,
        prompt_mode: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Review document using Gemini and return list of issues.

        Returns:
            List of issue dictionaries
        """
        prompt = build_review_prompt(
            report,
            benchmark,
            instructions_text=instructions_text,
            reference_context=reference_context,
            prompt_mode=prompt_mode,
        )
        response = self.model.generate_content(prompt)

        try:
            text = response.text.strip()
            # response_mime_type="application/json" means Gemini returns clean JSON.
            # Strip markdown fences as a safety net in case of model version variance.
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.rsplit("```", 1)[0].strip()

            parsed = json.loads(text)
            if isinstance(parsed, dict) and "findings" in parsed:
                return parsed["findings"]
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

        return []
