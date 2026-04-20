# French review orchestrator — runs the full pipeline for OTM/French reports.

from typing import Any, Dict, List, Optional

from app.models import ParsedDocument
from app.checks.french_rules import run_french_checks
from app.orchestration.base_orchestrator import ReviewOrchestrator, _serialize_document


class FrenchOrchestrator(ReviewOrchestrator):
    """
    Orchestrates a French (OTM) report review.

    Deterministic checks:  app.checks.french_rules.run_french_checks
    Prompt mode:           french_review  (→ app/prompts/french_review.md)
    LLM client:            app.llm.gemini_client.GeminiClient
    """

    prompt_mode = "french_review"

    def _get_language(self) -> str:
        return "French"

    def _run_deterministic_checks(
        self,
        report: ParsedDocument,
        benchmark: Optional[ParsedDocument] = None,
        glossary_rules: Optional[List[Dict[str, str]]] = None,
        style_rules: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        return run_french_checks(report, glossary_rules=glossary_rules, style_rules=style_rules)

    def _build_document_content(
        self,
        report: ParsedDocument,
        benchmark: Optional[ParsedDocument] = None,
    ) -> str:
        return _serialize_document(report)
