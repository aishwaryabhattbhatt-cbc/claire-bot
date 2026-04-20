# Deterministic French-language quality checks for OTM/Radio-Canada reports.

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


def _check_french_language_purity(report: ParsedDocument) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    prohibited = {
        "members": "membres",
        "canadians": "canadiens",
        "television": "télévision",
        "market": "marché",
        "summary": "sommaire",
        "viewers": "téléspectateurs",
        "respondents": "répondants",
        "platform": "plateforme",
        "trends": "tendances",
        "insights": "constats",
        "online": "en ligne",
        "listeners": "auditeurs",
        "subscribers": "abonnés",
        "households": "ménages",
    }

    for page in report.pages:
        text = (page.text or "")
        lower = text.lower()
        for english_word, french_alt in prohibited.items():
            if re.search(rf"\b{re.escape(english_word)}\b", lower):
                findings.append(
                    _issue(
                        page.page_number,
                        "French",
                        f"English word '{english_word}' found in French content.",
                        f"Remplacer par l'équivalent français : '{french_alt}'.",
                        category="Language Purity",
                    )
                )

    return findings


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


def _check_methodology_consistency(report: ParsedDocument) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    if not report.pages:
        return findings

    lang = report.metadata.language
    report_lang = (lang or "").strip().lower()
    if report_lang != "french":
        return findings

    first_page_text = (report.pages[0].text or "").lower()
    expected_sample = _infer_sample_from_first_page(first_page_text)
    if not expected_sample:
        return findings

    pattern = re.compile(r"répondants\s+(francophones|anglophones|canadiens)", flags=re.IGNORECASE)
    for page in report.pages:
        text = (page.text or "")
        lower = text.lower()
        if "les résultats présentés ici" in lower and "répondants" in lower:
            match = pattern.search(lower)
            if match:
                actual = match.group(1).lower()
                if actual != expected_sample:
                    findings.append(
                        _issue(
                            page.page_number,
                            lang,
                            f"Methodology sample mismatch: found 'répondants {actual}'.",
                            f"Utiliser 'répondants {expected_sample}'.",
                            category="Methodology",
                        )
                    )

    return findings


def _infer_sample_from_first_page(text: str) -> Optional[str]:
    if "francophone" in text:
        return "francophones"
    if "anglophone" in text:
        return "anglophones"
    if "canadien" in text or "canadian" in text:
        return "canadiens"
    return None


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


def run_french_checks(
    report: ParsedDocument,
    glossary_rules: Optional[List[Dict[str, str]]] = None,
    style_rules: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """Run all French-language deterministic checks and return findings."""
    findings: List[Dict[str, Any]] = []
    findings.extend(_check_age_labels(report))
    findings.extend(_check_methodology_consistency(report))
    findings.extend(_check_sentence_capitalization(report))
    findings.extend(_check_french_language_purity(report))
    return findings
