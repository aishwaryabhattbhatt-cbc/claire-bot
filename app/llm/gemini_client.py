# Low-level Gemini API client — handles all direct google.generativeai calls
# and usage/cost tracking (moved from app/services/gemini_service.py).

import json
from typing import AsyncGenerator, Dict, List, Optional, Any

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from app.core.config import get_settings
from app.models import ParsedDocument
from app.llm.prompt_builder import build_prompt
from app.services.usage_service import record_gemini_usage


MODEL_PRICING = {
    "gemini-2.5-flash": {"input_per_m": 0.10, "output_per_m": 0.40},
}


def _serialize_document(doc: ParsedDocument) -> str:
    """Convert a ParsedDocument into the template input text block."""
    lines = [
        f"Report Language: {doc.metadata.language}",
        f"Total Pages: {doc.metadata.total_pages}",
        "Report Pages:",
    ]
    for page in doc.pages:
        snippet = (page.text or "").strip().replace("\n", " ")
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "..."
        lines.append(f"Page {page.page_number}: {snippet}")
    return "\n".join(lines)


class GeminiClient:
    """Low-level Gemini API client with usage tracking."""

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
        self._last_usage: Optional[Dict[str, Any]] = None

    def _pricing_for_model(self) -> Dict[str, float]:
        return MODEL_PRICING.get(
            self.model_name,
            MODEL_PRICING["gemini-2.5-flash"],
        )

    def review(self, prompt: str) -> str:
        """Send a pre-built prompt to Gemini and return the raw response text."""
        response = self.model.generate_content(prompt)
        self._record_usage(response)
        return response.text.strip() if response.text else ""

    async def stream_review(self, prompt: str) -> AsyncGenerator[str, None]:
        """Stream a pre-built prompt to Gemini, yielding text chunks as they arrive."""
        response = self.model.generate_content(prompt, stream=True)
        for chunk in response:
            text = getattr(chunk, "text", None)
            if text:
                yield text

    def _record_usage(self, response: Any) -> None:
        """Extract usage metadata from the response and record it."""
        try:
            usage = getattr(response, "usage_metadata", None)
            if usage is None:
                return
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

            self._last_usage = usage_summary
        except Exception as _err:
            print("Failed to extract usage metadata for cost logging:", _err)

    # -------------------------------------------------------------------------
    # Higher-level convenience method (preserves backward-compat with
    # GeminiReviewService.review_document used by llm_service.py)
    # -------------------------------------------------------------------------

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
        Build a full review prompt, call Gemini, and return parsed findings list.
        """
        mode = (prompt_mode or "french_review").strip().lower()
        document_content = _serialize_document(report)
        if benchmark is not None:
            benchmark_lines = [
                "\nBenchmark (English) Pages:",
                f"Total Pages: {benchmark.metadata.total_pages}",
            ]
            for page in benchmark.pages:
                snippet = (page.text or "").strip().replace("\n", " ")
                if len(snippet) > 2000:
                    snippet = snippet[:2000] + "..."
                benchmark_lines.append(f"Page {page.page_number}: {snippet}")
            document_content = document_content + "\n" + "\n".join(benchmark_lines)

        prompt = build_prompt(
            mode=mode,
            document_content=document_content,
            reference_content=reference_context or "",
        )
        if instructions_text:
            prompt = f"Instructions:\n{instructions_text.strip()}\n\n{prompt}"
        if additional_context and additional_context.strip():
            prompt += f"\n\nAdditional context from the user:\n{additional_context.strip()}"
        raw = self.review(prompt)

        try:
            text = raw
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


# Backward-compatible alias so existing imports of GeminiReviewService still work
GeminiReviewService = GeminiClient


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience function (replaces llm_service.review_with_llm)
# ─────────────────────────────────────────────────────────────────────────────

def get_llm_service() -> GeminiClient:
    """Return the configured Gemini client instance."""
    _ = get_settings()
    return GeminiClient()


def review_with_llm(
    report: ParsedDocument,
    benchmark: Optional[ParsedDocument] = None,
    instructions_text: Optional[str] = None,
    reference_context: Optional[str] = None,
    prompt_mode: Optional[str] = None,
    additional_context: Optional[str] = None,
):
    """
    Run a full LLM review and return (findings_list, usage_dict).

    This is the single entry-point used by the API layer.
    """
    from typing import Tuple
    service = get_llm_service()
    findings = service.review_document(
        report,
        benchmark,
        instructions_text=instructions_text,
        reference_context=reference_context,
        prompt_mode=prompt_mode,
        additional_context=additional_context,
    )
    usage = getattr(service, "_last_usage", None)
    return findings, usage

