from typing import List, Dict, Any, Optional

from app.core.config import get_settings
from app.models import ParsedDocument
from app.services.gemini_service import GeminiReviewService
from app.services.openai_service import OpenAIReviewService


def get_llm_service():
    settings = get_settings()
    provider = (settings.llm_provider or "gemini").lower()

    if provider == "openai":
        return OpenAIReviewService()

    return GeminiReviewService()


def review_with_llm(
    report: ParsedDocument,
    benchmark: Optional[ParsedDocument] = None,
    instructions_text: Optional[str] = None,
    reference_context: Optional[str] = None,
    prompt_mode: Optional[str] = None,
    additional_context: Optional[str] = None,
) -> List[Dict[str, Any]]:
    service = get_llm_service()
    return service.review_document(
        report,
        benchmark,
        instructions_text=instructions_text,
        reference_context=reference_context,
        prompt_mode=prompt_mode,
        additional_context=additional_context,
    )
