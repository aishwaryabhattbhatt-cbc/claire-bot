from typing import List, Optional

from app.models import ParsedDocument


ENFORCED_PHASE_INSTRUCTIONS = """Instructions:
Phase 1: Role & Core Function
-Role/Task/Output Format
Phase 2: Linguistic & Stylistic Rules (Radio-Canada/MTM Standards)
-Glossary/Language Purity/Age References/Casing/Footnotes/Text preferences
Phase 3: The Comparison Rules
-Benchmark/Data Matching/Target Sample/Translation Alignment/Review of the English report
Phase 4: Visual & Technical Verification
-Logos/Consistency/Summary/Graphics/Navigation (TOC)/Methodology/Date
"""


ENFORCED_COMPARISON_PROMPT = """Comparison prompt: You’re a master editor of MTM/OTM reports. To complete your task, you will compare the following reports. Follow every step listed in your instructions (Phase 1, Phase 2, Phase 3, Phase 4, Phase 5), perform a strict language purity double-check with an emphasis on the French report, make sure that numbers match, formatting is aligned and logos are accurate. Flag issues that you find both in the French and English reports. Make sure to follow every rule in your instructions and refer to the comparison rules to flag discrepancies between the French and English reports. Double check every step before providing your feedback.
"""


ENFORCED_FRENCH_REVIEW_PROMPT = """French Review Prompt: You’re a master editor of OTM reports. To complete your task, you will review the following report. Follow every step listed in Phase 1, Phase 2, Phase 3 and Phase 5 of your instructions (exclude Phase 4), perform a strict language purity double-check, make sure that numbers match the text, formatting is aligned and logos are accurate. Double check every step before providing your feedback.
"""


def build_review_prompt(
    report: ParsedDocument,
    benchmark: Optional[ParsedDocument] = None,
    instructions_text: Optional[str] = None,
    reference_context: Optional[str] = None,
) -> str:
    """
    Build the prompt for LLM review.

    Args:
        report: Parsed French or English report
        benchmark: Parsed English benchmark report (optional)

    Returns:
        Prompt string
    """
    comparison_mode = benchmark is not None

    scenario_prompt = ENFORCED_COMPARISON_PROMPT
    if not comparison_mode and report.metadata.language.lower() == "french":
        scenario_prompt = ENFORCED_FRENCH_REVIEW_PROMPT

    rules_text = ENFORCED_PHASE_INSTRUCTIONS + "\n" + scenario_prompt

    header = (
        "You are Clairebot, an expert editor for MTM/OTM reports. "
        "Review the report strictly using the instructions below. "
        "Return output as JSON ONLY. Use an object with key 'findings' containing a list of issues. "
        "Each issue must contain: "
        "page_number (int), language (French|English), issue_detected (string), proposed_change (string).\n\n"
        f"Instructions:\n{rules_text}\n\n"
        "Return NO explanations outside the JSON.\n\n"
    )

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
