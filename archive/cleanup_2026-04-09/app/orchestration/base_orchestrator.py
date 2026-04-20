# Abstract base orchestrator — defines the canonical review pipeline sequence
# that every concrete orchestrator must follow.

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.models import ParsedDocument
from app.services.parser_service import DocumentParserService
from app.findings.normalizer import normalize_findings

logger = logging.getLogger(__name__)

_parser = DocumentParserService()


def _serialize_document(doc: ParsedDocument) -> str:
    """Convert a ParsedDocument to the plain-text block passed to the prompt template."""
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


def _parse_llm_json(raw: str) -> List[Dict[str, Any]]:
    """Best-effort parse of a Gemini JSON response into a findings list."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "findings" in parsed:
            return parsed["findings"]
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return []


class ReviewOrchestrator(ABC):
    """
    Abstract base class for all review orchestrators.

    Subclasses must implement:
      - prompt_mode (class attribute)
      - _run_deterministic_checks()
      - _get_language()          — language string passed to the parser
      - _build_document_content() — assemble the document text block for the prompt

    The run() method owns the fixed pipeline:
      1. Parse uploaded document(s)
      2. Run deterministic checks (always first, never skipped)
      3. Try LLM review — failures are logged and produce an empty list
      4. Merge both lists → normalize_findings()
      5. Optionally export to Sheets if sheet_id is provided
      6. Return final findings list
    """

    #: Must be overridden by every subclass with the correct mode string.
    prompt_mode: str = "french_review"

    # -------------------------------------------------------------------------
    # Abstract hooks — subclasses fill in the language-specific details
    # -------------------------------------------------------------------------

    @abstractmethod
    def _run_deterministic_checks(
        self,
        report: ParsedDocument,
        benchmark: Optional[ParsedDocument] = None,
        glossary_rules: Optional[List[Dict[str, str]]] = None,
        style_rules: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        """Return deterministic findings for the given document(s)."""
        ...

    @abstractmethod
    def _get_language(self) -> str:
        """Return the primary language string used when parsing ('French'/'English')."""
        ...

    @abstractmethod
    def _build_document_content(
        self,
        report: ParsedDocument,
        benchmark: Optional[ParsedDocument] = None,
    ) -> str:
        """Assemble the document text block to substitute into the prompt template."""
        ...

    # -------------------------------------------------------------------------
    # Pipeline
    # -------------------------------------------------------------------------

    def run(
        self,
        file_path: str,
        instructions_text: Optional[str] = None,
        reference_content: str = "",
        additional_context: Optional[str] = None,
        glossary_rules: Optional[List[Dict[str, str]]] = None,
        style_rules: Optional[List[Dict[str, str]]] = None,
        sheet_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute the full review pipeline and return the normalised findings list.

        Args:
            file_path:         Path to the primary document to review.
            instructions_text: Optional override for the LLM instructions block.
            reference_content: Pre-built reference text injected into the prompt.
            additional_context: Free-text user note appended to the prompt.
            glossary_rules:    Parsed glossary rules for deterministic checks.
            style_rules:       Parsed style-guide rules for deterministic checks.
            sheet_id:          If provided, export findings to this Google Sheet
                               and attach the URL to each finding.
        Returns:
            Normalised list of finding dicts sorted by page_number.
        """
        from app.llm.gemini_client import GeminiClient
        from app.llm.prompt_builder import build_prompt

        # ── Step 1: Parse ────────────────────────────────────────────────────
        language = self._get_language()
        report: ParsedDocument = _parser.parse_document(file_path, language)
        logger.info("[%s] Parsed %d pages (%s).", self.__class__.__name__, report.metadata.total_pages, language)

        # ── Step 2: Deterministic checks ─────────────────────────────────────
        det_findings = self._run_deterministic_checks(
            report,
            glossary_rules=glossary_rules,
            style_rules=style_rules,
        )
        logger.info("[%s] Deterministic checks: %d findings.", self.__class__.__name__, len(det_findings))

        # ── Step 3: LLM review ───────────────────────────────────────────────
        llm_findings: List[Dict[str, Any]] = []
        try:
            document_content = self._build_document_content(report)
            prompt = build_prompt(
                mode=self.prompt_mode,
                document_content=document_content,
                reference_content=reference_content,
            )
            if instructions_text:
                prompt = f"Instructions:\n{instructions_text.strip()}\n\n{prompt}"
            if additional_context:
                prompt += f"\n\nAdditional context from the user:\n{additional_context.strip()}"

            client = GeminiClient()
            raw = client.review(prompt)
            llm_findings = _parse_llm_json(raw)
            for f in llm_findings:
                f.setdefault("source", "llm")
            logger.info("[%s] LLM review: %d findings.", self.__class__.__name__, len(llm_findings))
        except Exception as exc:
            logger.error(
                "[%s] LLM review failed — continuing with deterministic findings only. Error: %s",
                self.__class__.__name__,
                exc,
            )

        # ── Step 4: Merge + normalise ─────────────────────────────────────────
        all_findings = det_findings + llm_findings
        final: List[Dict[str, Any]] = normalize_findings(all_findings)
        logger.info("[%s] Final findings after normalisation: %d.", self.__class__.__name__, len(final))

        # ── Step 5: Optional Sheets export ───────────────────────────────────
        if sheet_id:
            try:
                from app.export.sheets_client import SheetsClient
                url = SheetsClient().export_findings(final, sheet_id)
                for f in final:
                    f["sheets_url"] = url
                logger.info("[%s] Exported to Sheets: %s", self.__class__.__name__, url)
            except Exception as exc:
                logger.error("[%s] Sheets export failed: %s", self.__class__.__name__, exc)

        # ── Step 6: Return ────────────────────────────────────────────────────
        return final
