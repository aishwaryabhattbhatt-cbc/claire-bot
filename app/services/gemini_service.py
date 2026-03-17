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
        additional_context: Optional[str] = None,
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
            additional_context=additional_context,
        )
        response = self.model.generate_content(prompt)

        # --- Usage & Cost Logging (per-run) ---
        try:
            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                # Define pricing per 1 million tokens
                INPUT_PRICE_PER_M = 0.10
                OUTPUT_PRICE_PER_M = 0.40

                prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
                candidate_tokens = getattr(usage, "candidates_token_count", 0) or 0
                total_tokens = getattr(usage, "total_token_count", prompt_tokens + candidate_tokens) or (prompt_tokens + candidate_tokens)

                input_cost = (prompt_tokens / 1_000_000) * INPUT_PRICE_PER_M
                output_cost = (candidate_tokens / 1_000_000) * OUTPUT_PRICE_PER_M
                total_cost = input_cost + output_cost

                # Print to backend logs so Cloud Run logs capture cost per report in real-time
                print("--- Usage & Cost for this run ---")
                print(f"Prompt Tokens: {prompt_tokens} (Cost: ${input_cost:.6f})")
                print(f"Response Tokens: {candidate_tokens} (Cost: ${output_cost:.6f})")
                print(f"Total Tokens: {total_tokens}")
                print(f"Total Estimated Cost: ${total_cost:.6f}")
                # Persist usage info on the service instance for external access
                try:
                    self._last_usage = {
                        "prompt_tokens": int(prompt_tokens),
                        "response_tokens": int(candidate_tokens),
                        "total_tokens": int(total_tokens),
                        "input_cost": float(input_cost),
                        "output_cost": float(output_cost),
                        "total_cost": float(total_cost),
                    }
                except Exception:
                    # Safe fallback: ensure attribute exists
                    self._last_usage = None
        except Exception as _err:
            # Never fail the review because logging failed
            print("Failed to extract usage metadata for cost logging:", _err)

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
