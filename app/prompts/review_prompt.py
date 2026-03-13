from typing import List, Optional

from app.models import ParsedDocument


BASE_INSTRUCTIONS = """Instructions:
Phase 1: Role & Core Function
- Role: You are Clairebot, a precision-first QA editor for MTM/OTM reports.
- Task: Detect only clear, evidence-based issues from provided content.
- Output: Return JSON only as {"findings":[{page_number, language, issue_detected, proposed_change}]}.

Phase 2: Linguistic & Stylistic Rules (Radio-Canada/MTM Standards)
- Enforce approved glossary, language purity, age references, casing, footnotes, and text preferences.

Phase 3: Comparison Rules
- Flag only material mismatches in data, claims, labels, sample/methodology wording, and translation alignment.

Phase 4: Visual & Technical Verification
- Check logos, formatting consistency, summary alignment, graphics labels, TOC/navigation, methodology/date consistency.

Precision rules:
- High-confidence findings only; if uncertain, do not report.
- Never invent content.
- Use exact page numbers from input.
- No prose outside JSON.
"""


COMPARISON_INSTRUCTIONS = """Comparison prompt:
- Full-document comparison is required.
- Compare all French pages against all benchmark English pages end-to-end.
- Treat benchmark English as source of truth for facts and meaning.
- Flag issues in French and English when clearly incorrect or inconsistent.
- Prioritize factual mismatches over stylistic preference.
- Propose minimal, direct corrections.
"""


FRENCH_REVIEW_INSTRUCTIONS = """French Review prompt:
- Full-document French-only review is required.
- Do not assume benchmark context.
- Enforce French language purity and approved terminology.
- Flag clear grammar/spelling/terminology/footnote consistency issues.
- Keep findings high-confidence, concise, and actionable.
"""


def get_fixed_mode_instructions(prompt_mode: Optional[str]) -> str:
    mode = (prompt_mode or "french_review").strip().lower()
    mode_block = COMPARISON_INSTRUCTIONS if mode == "comparison" else FRENCH_REVIEW_INSTRUCTIONS
    return BASE_INSTRUCTIONS + "\n" + mode_block


def build_review_prompt(
    report: ParsedDocument,
    benchmark: Optional[ParsedDocument] = None,
    instructions_text: Optional[str] = None,
    reference_context: Optional[str] = None,
    prompt_mode: Optional[str] = None,
) -> str:
    """
    Build the prompt for LLM review.

    Args:
        report: Parsed French or English report
        benchmark: Parsed English benchmark report (optional)

        instructions_text: Instructions text to include in the prompt
        reference_context: Reference documents context
        prompt_mode: 'comparison' or 'french_review'

    Returns:
        Prompt string
    """
    # Instructions are fixed by mode. `instructions_text` is kept only for backward-compatible signatures.
    _ = instructions_text
    comparison_mode = benchmark is not None
    rules_text = get_fixed_mode_instructions(prompt_mode)

    header = (
        "You are Clairebot, an expert editor for MTM/OTM reports. "
        "Review the report strictly using the instructions below. "
        "Return output as JSON ONLY. Use an object with key 'findings' containing a list of issues. "
        "Each issue must contain: "
        "page_number (int), language (French|English), issue_detected (string), proposed_change (string).\n\n"
    )

    header += f"Instructions:\n{rules_text}\n\n"

    header += "Return NO explanations outside the JSON.\n\n"

    report_block = [
        f"Report Language: {report.metadata.language}",
        f"Total Pages: {report.metadata.total_pages}",
        "Report Pages:",
    ]

    for page in report.pages:
        text_snippet = page.text.strip().replace("\n", " ")
        if len(text_snippet) > 2000:
            text_snippet = text_snippet[:2000] + "..."
        report_block.append(f"Page {page.page_number}: {text_snippet}")

    benchmark_block: List[str] = []
    if comparison_mode and benchmark is not None:
        benchmark_block = [
            "\nBenchmark (English) Pages:",
            f"Total Pages: {benchmark.metadata.total_pages}",
        ]
        for page in benchmark.pages:
            text_snippet = page.text.strip().replace("\n", " ")
            if len(text_snippet) > 2000:
                text_snippet = text_snippet[:2000] + "..."
            benchmark_block.append(f"Page {page.page_number}: {text_snippet}")

    reference_block: List[str] = []
    if reference_context and reference_context.strip():
        reference_block = [
            "\n\nReference Standards (use these as the authoritative source of truth when checking terminology, methodology, and benchmarks):",
            reference_context.strip(),
        ]

    return header + "\n".join(report_block + benchmark_block + reference_block)
