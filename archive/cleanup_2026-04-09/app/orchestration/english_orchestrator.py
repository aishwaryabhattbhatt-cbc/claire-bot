# English review orchestrator — runs the full pipeline for MTM/English reports.

from typing import Any, Dict, List, Optional

from app.models import ParsedDocument
from app.checks.english_rules import run_english_checks
from app.orchestration.base_orchestrator import ReviewOrchestrator, _serialize_document


class EnglishOrchestrator(ReviewOrchestrator):
    """
    Orchestrates an English (MTM) report review.

    Deterministic checks:  app.checks.english_rules.run_english_checks
    Prompt mode:           english_review  (→ app/prompts/english_review.md)
    LLM client:            app.llm.gemini_client.GeminiClient
    """

    prompt_mode = "english_review"

    def _get_language(self) -> str:
        return "English"

    def _run_deterministic_checks(
        self,
        report: ParsedDocument,
        benchmark: Optional[ParsedDocument] = None,
        glossary_rules: Optional[List[Dict[str, str]]] = None,
        style_rules: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        return run_english_checks(report, glossary_rules=glossary_rules, style_rules=style_rules)

    def _build_document_content(
        self,
        report: ParsedDocument,
        benchmark: Optional[ParsedDocument] = None,
    ) -> str:
        return _serialize_document(report)
