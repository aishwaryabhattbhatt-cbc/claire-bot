# Comparison orchestrator — reviews a French (OTM) report against an English
# (MTM) benchmark using alignment and cross-document checks.

import logging
from typing import Any, Dict, List, Optional

from app.models import ParsedDocument
from app.checks.alignment_rules import run_alignment_checks
from app.orchestration.base_orchestrator import (
    ReviewOrchestrator,
    _parse_llm_json,
    _parser,
    _serialize_document,
)
from app.findings.normalizer import normalize_findings

logger = logging.getLogger(__name__)


class ComparisonOrchestrator(ReviewOrchestrator):
    """
    Orchestrates a side-by-side comparison of a French (OTM) report against
    an English (MTM) benchmark.

    Deterministic checks:  app.checks.alignment_rules.run_alignment_checks
    Prompt mode:           comparison  (→ app/prompts/comparison.md)
    LLM client:            app.llm.gemini_client.GeminiClient

    This orchestrator overrides run() because it needs two document paths
    instead of one.
    """

    prompt_mode = "comparison"

    # ── Abstract-method implementations (used when called via the base run()) ──

    def _get_language(self) -> str:
        # Primary document is always French in a comparison review
        return "French"

    def _run_deterministic_checks(
        self,
        report: ParsedDocument,
        benchmark: Optional[ParsedDocument] = None,
        glossary_rules: Optional[List[Dict[str, str]]] = None,
        style_rules: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        return run_alignment_checks(
            report,
            benchmark=benchmark,
            glossary_rules=glossary_rules,
            style_rules=style_rules,
        )

    def _build_document_content(
        self,
        report: ParsedDocument,
        benchmark: Optional[ParsedDocument] = None,
    ) -> str:
        block = _serialize_document(report)
        if benchmark is not None:
            bench_lines = [
                "\nBenchmark (English) Pages:",
                f"Total Pages: {benchmark.metadata.total_pages}",
            ]
            for page in benchmark.pages:
                snippet = (page.text or "").strip().replace("\n", " ")
                if len(snippet) > 2000:
                    snippet = snippet[:2000] + "..."
                bench_lines.append(f"Page {page.page_number}: {snippet}")
            block += "\n" + "\n".join(bench_lines)
        return block

    # ── Overridden run() — accepts two file paths ─────────────────────────────

    def run(  # type: ignore[override]
        self,
        french_file_path: str,
        english_file_path: str,
        instructions_text: Optional[str] = None,
        reference_content: str = "",
        additional_context: Optional[str] = None,
        glossary_rules: Optional[List[Dict[str, str]]] = None,
        style_rules: Optional[List[Dict[str, str]]] = None,
        sheet_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute the full comparison pipeline and return normalised findings.

        Args:
            french_file_path:  Path to the French (OTM) report.
            english_file_path: Path to the English (MTM) benchmark report.
            instructions_text: Optional override for the LLM instructions block.
            reference_content: Pre-built reference text injected into the prompt.
            additional_context: Free-text user note appended to the prompt.
            glossary_rules:    Parsed glossary rules for deterministic checks.
            style_rules:       Parsed style-guide rules for deterministic checks.
            sheet_id:          If provided, export findings to this Google Sheet.
        Returns:
            Normalised list of finding dicts sorted by page_number.
        """
        from app.llm.gemini_client import GeminiClient
        from app.llm.prompt_builder import build_prompt

        # ── Step 1: Parse both documents ─────────────────────────────────────
        french_report: ParsedDocument = _parser.parse_document(french_file_path, "French")
        english_report: ParsedDocument = _parser.parse_document(english_file_path, "English")
        logger.info(
            "[ComparisonOrchestrator] Parsed French (%d pages) and English (%d pages).",
            french_report.metadata.total_pages,
            english_report.metadata.total_pages,
        )

        # ── Step 2: Deterministic alignment checks ───────────────────────────
        det_findings = self._run_deterministic_checks(
            french_report,
            benchmark=english_report,
            glossary_rules=glossary_rules,
            style_rules=style_rules,
        )
        logger.info("[ComparisonOrchestrator] Deterministic checks: %d findings.", len(det_findings))

        # ── Step 3: LLM review ───────────────────────────────────────────────
        llm_findings: List[Dict[str, Any]] = []
        try:
            document_content = self._build_document_content(french_report, english_report)
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
            logger.info("[ComparisonOrchestrator] LLM review: %d findings.", len(llm_findings))
        except Exception as exc:
            logger.error(
                "[ComparisonOrchestrator] LLM review failed — continuing with deterministic findings only. Error: %s",
                exc,
            )

        # ── Step 4: Merge + normalise ─────────────────────────────────────────
        all_findings = det_findings + llm_findings
        final: List[Dict[str, Any]] = normalize_findings(all_findings)
        logger.info("[ComparisonOrchestrator] Final findings after normalisation: %d.", len(final))

        # ── Step 5: Optional Sheets export ───────────────────────────────────
        if sheet_id:
            try:
                from app.export.sheets_client import SheetsClient
                url = SheetsClient().export_findings(final, sheet_id)
                for f in final:
                    f["sheets_url"] = url
                logger.info("[ComparisonOrchestrator] Exported to Sheets: %s", url)
            except Exception as exc:
                logger.error("[ComparisonOrchestrator] Sheets export failed: %s", exc)

        # ── Step 6: Return ────────────────────────────────────────────────────
        return final
