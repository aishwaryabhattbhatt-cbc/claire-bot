# Deterministic English-language quality checks for MTM reports.

import re
from typing import Any, Dict, List, Optional

from app.models import ParsedDocument


def _issue(
    page_number: int,
    language: str,
    issue_detected: str,
    proposed_change: str,
    category: str = "",
    source: str = "deterministic",
) -> Dict[str, Any]:
    return {
        "page_number": int(page_number),
        "language": language,
        "category": category,
        "issue_detected": issue_detected,
        "proposed_change": proposed_change,
        "source": source,
    }


def _check_age_labels(report: ParsedDocument) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    lang = report.metadata.language
    report_lang = (lang or "").strip().lower()

    if report_lang not in {"french", "english"}:
        return findings

    for page in report.pages:
        text = page.text or ""
        if report_lang == "french":
            pattern = r"\b\d{1,2}\s*(?:-|à)\s*\d{1,2}(?!\s*ans\b)\b"
            for m in re.finditer(pattern, text, flags=re.IGNORECASE):
                findings.append(
                    _issue(
                        page.page_number,
                        lang,
                        f"Age range '{m.group(0)}' is missing 'ans'.",
                        f"Utiliser le format '{m.group(0)} ans'.",
                        category="Formatting & Consistency",
                    )
                )
        else:
            pattern = r"\b\d{1,2}\s*(?:-|to)\s*\d{1,2}(?!\s*years?\b)\b"
            for m in re.finditer(pattern, text, flags=re.IGNORECASE):
                findings.append(
                    _issue(
                        page.page_number,
                        lang,
                        f"Age range '{m.group(0)}' is missing 'years'.",
                        f"Use the format '{m.group(0)} years'.",
                        category="Formatting & Consistency",
                    )
                )

    return findings


def _check_sentence_capitalization(report: ParsedDocument) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    lang = report.metadata.language
    report_lang = (lang or "").strip().lower()

    for page in report.pages:
        text = (page.text or "").strip()
        if not text:
            continue

        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            if re.match(r"^\d+\s*%", s):
                continue
            first_alpha = re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", s)
            if first_alpha:
                ch = first_alpha.group(0)
                if ch.islower():
                    findings.append(
                        _issue(
                            page.page_number,
                            lang,
                            "Sentence starts with lowercase letter.",
                            (
                                "Start each new sentence with a capital letter."
                                if report_lang == "english"
                                else "Commencer chaque nouvelle phrase par une majuscule."
                            ),
                            category="Formatting & Consistency",
                        )
                    )
                    break

    return findings


def run_english_checks(
    report: ParsedDocument,
    glossary_rules: Optional[List[Dict[str, str]]] = None,
    style_rules: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """Run all English-language deterministic checks and return findings."""
    findings: List[Dict[str, Any]] = []
    findings.extend(_check_age_labels(report))
    findings.extend(_check_sentence_capitalization(report))
    return findings
