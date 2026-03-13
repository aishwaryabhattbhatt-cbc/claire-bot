import json
from typing import List, Optional, Dict, Any

import google.generativeai as genai

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
        self.model = genai.GenerativeModel(settings.gemini_model)

    def review_document(
        self,
        report: ParsedDocument,
        benchmark: Optional[ParsedDocument] = None,
        instructions_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Review document using Gemini and return list of issues.

        Returns:
            List of issue dictionaries
        """
        prompt = build_review_prompt(report, benchmark, instructions_text=instructions_text)
        response = self.model.generate_content(prompt)

        try:
            text = response.text.strip()
            # Strip markdown code fences that Gemini often adds
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.rsplit("```", 1)[0].strip()

            parsed = json.loads(text)
            # Handle {"findings": [...]} wrapper (standard shape)
            if isinstance(parsed, dict) and "findings" in parsed:
                return parsed["findings"]
            # Handle bare list (legacy shape)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

        # Fallback if parsing fails
        return []
