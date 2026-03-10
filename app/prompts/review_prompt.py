from typing import List, Optional

from app.models import ParsedDocument


def build_review_prompt(
    report: ParsedDocument,
    benchmark: Optional[ParsedDocument] = None,
    instructions_text: Optional[str] = None,
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

    rules_text = (instructions_text or "").strip()
    if not rules_text:
        rules_text = (
            "Role: You are Clairebot, an expert editor for MTM/OTM reports.\n"
            "Task: Review French and English reports and compare FR against EN benchmark when provided.\n"
            "Rules: enforce French purity, terminology consistency, age labels with 'ans', footnote integrity, "
            "methodology sample consistency, summary/data alignment, and benchmark alignment.\n"
        )

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

    return header + "\n".join(report_block + benchmark_block)
