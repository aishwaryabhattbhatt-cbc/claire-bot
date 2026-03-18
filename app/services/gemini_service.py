import json
from typing import List, Optional, Dict, Any

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from app.core.config import get_settings
from app.models import ParsedDocument
from app.prompts.review_prompt import build_review_prompt
from app.services.usage_service import record_gemini_usage


MODEL_PRICING = {
    "gemini-2.5-flash": {"input_per_m": 0.10, "output_per_m": 0.40},
}


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
        self.model_name = settings.gemini_model

    def _pricing_for_model(self) -> Dict[str, float]:
        return MODEL_PRICING.get(
            self.model_name,
            MODEL_PRICING["gemini-2.5-flash"],
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
                pricing = self._pricing_for_model()
                input_price_per_m = pricing["input_per_m"]
                output_price_per_m = pricing["output_per_m"]

                prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
                candidate_tokens = getattr(usage, "candidates_token_count", 0) or 0
                cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0
                thoughts_tokens = getattr(usage, "thoughts_token_count", 0) or 0
                total_tokens = getattr(usage, "total_token_count", prompt_tokens + candidate_tokens) or (prompt_tokens + candidate_tokens)

                input_cost = (prompt_tokens / 1_000_000) * input_price_per_m
                output_cost = (candidate_tokens / 1_000_000) * output_price_per_m
                total_cost = input_cost + output_cost

                latest_usage = {
                    "provider": "gemini",
                    "model": self.model_name,
                    "pricing_source": "configured_model_rates",
                    "prompt_tokens": int(prompt_tokens),
                    "response_tokens": int(candidate_tokens),
                    "cached_tokens": int(cached_tokens),
                    "thoughts_tokens": int(thoughts_tokens),
                    "total_tokens": int(total_tokens),
                    "input_cost": float(input_cost),
                    "output_cost": float(output_cost),
                    "total_cost": float(total_cost),
                }

                usage_summary = record_gemini_usage(latest_usage)

                # Print to backend logs so Cloud Run logs capture actual API usage totals.
                print("--- Gemini usage for latest API call ---")
                print(f"Model: {self.model_name}")
                print(f"Prompt Tokens: {prompt_tokens} (Cost: ${input_cost:.6f})")
                print(f"Response Tokens: {candidate_tokens} (Cost: ${output_cost:.6f})")
                print(f"Cached Tokens: {cached_tokens}")
                print(f"Thoughts Tokens: {thoughts_tokens}")
                print(f"Total Tokens: {total_tokens}")
                print(f"Calculated Cost: ${total_cost:.6f}")
                print("--- Gemini cumulative usage ---")
                print(f"Call Count: {usage_summary['cumulative']['call_count']}")
                print(f"Cumulative Tokens: {usage_summary['cumulative']['total_tokens']}")
                print(f"Cumulative Cost: ${usage_summary['cumulative']['total_cost']:.6f}")

                try:
                    self._last_usage = usage_summary
                except Exception:
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
