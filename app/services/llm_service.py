from typing import List, Dict, Any, Optional, Tuple

from app.core.config import get_settings
from app.models import ParsedDocument
from app.services.gemini_service import GeminiReviewService


def get_llm_service():
    """Always return the Gemini-based review service.

    The OpenAI provider option has been removed to enforce Gemini-only usage.
    """
    # Keep settings access in case other parts rely on it (temperature, model)
    _ = get_settings()
    return GeminiReviewService()


def review_with_llm(
    report: ParsedDocument,
    benchmark: Optional[ParsedDocument] = None,
    instructions_text: Optional[str] = None,
    reference_context: Optional[str] = None,
    prompt_mode: Optional[str] = None,
    additional_context: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
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
