import re
from typing import Any, Dict, List, Optional

from app.models import ParsedDocument


def run_deterministic_checks(
    report: ParsedDocument,
    benchmark: Optional[ParsedDocument] = None,
    style_rules: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    # Deterministic checks removed. All formatting, capitalization, age labels,
    # methodology consistency, benchmark alignment, and language purity checks
    # are now performed by the LLM review with better context awareness.
    #
    # Only reference-based checks remain (glossary & style guide rules).

    if style_rules:
        findings.extend(_check_reference_style_rules(report, style_rules))

    return findings


def _issue(page_number: int, language: str, issue_detected: str, proposed_change: str, category: str = "") -> Dict[str, Any]:
    return {
        "page_number": int(page_number),
        "language": language,
        "category": category,
        "issue_detected": issue_detected,
        "proposed_change": proposed_change,
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

    for page in report.pages:
        text = page.text or ""
        for m in re.finditer(r"\b\d{1,2}\s*(?:-|à)\s*\d{1,2}(?!\s*ans)\b", text, flags=re.IGNORECASE):
            findings.append(
                _issue(
                    page.page_number,
                    lang,
                    f"Age range '{m.group(0)}' is missing 'ans'.",
                    f"Utiliser le format '{m.group(0)} ans'.",
                    category="Formatting & Consistency",
                )
            )

    return findings


def _check_methodology_consistency(report: ParsedDocument) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    if not report.pages:
        return findings

    lang = report.metadata.language
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


def _check_benchmark_alignment(report: ParsedDocument, benchmark: ParsedDocument) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    lang = report.metadata.language

    if report.metadata.total_pages != benchmark.metadata.total_pages:
        findings.append(
            _issue(
                1,
                lang,
                "Page count mismatch versus benchmark.",
                f"Aligner le nombre de pages sur le rapport de référence ({benchmark.metadata.total_pages} pages).",
                category="Data Accuracy",
            )
        )

    min_pages = min(len(report.pages), len(benchmark.pages))
    pct_pattern = re.compile(r"\b(\d{1,3})\s*%")
    for idx in range(min_pages):
        report_pcts = pct_pattern.findall(report.pages[idx].text or "")
        benchmark_pcts = pct_pattern.findall(benchmark.pages[idx].text or "")
        if report_pcts and benchmark_pcts and sorted(report_pcts) != sorted(benchmark_pcts):
            findings.append(
                _issue(
                    report.pages[idx].page_number,
                    lang,
                    "Percentage values do not match benchmark on this page.",
                    "Mettre à jour les valeurs françaises pour qu'elles correspondent exactement aux valeurs du rapport de référence.",
                    category="Data Accuracy",
                )
            )

    return findings


def _check_sentence_capitalization(report: ParsedDocument) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    lang = report.metadata.language

    for page in report.pages:
        text = (page.text or "").strip()
        if not text:
            continue

        # Split by sentence boundaries and check first alpha char after punctuation.
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            # Skip percentage-leading sentences as requested
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
                            "Commencer chaque nouvelle phrase par une majuscule.",
                            category="Formatting & Consistency",
                        )
                    )
                    break

    return findings


def _check_reference_glossary(
    report: ParsedDocument, glossary_rules: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """Apply deterministic source->target terminology checks from reference glossary files."""
    findings: List[Dict[str, Any]] = []
    lang = report.metadata.language
    report_lang = (lang or "").strip().lower()

    for page in report.pages:
        text = page.text or ""
        if not text.strip():
            continue

        page_hits = 0
        for rule in glossary_rules:
            source = (rule.get("source") or "").strip()
            target = (rule.get("target") or "").strip()
            rule_lang = (rule.get("language") or "Any").strip().lower()
            origin = (rule.get("origin") or "reference glossary").strip()

            if not source or not target:
                continue

            if rule_lang == "french" and report_lang != "french":
                continue
            if rule_lang == "english" and report_lang != "english":
                continue

            source_pattern = re.compile(rf"\b{re.escape(source)}\b", flags=re.IGNORECASE)
            target_pattern = re.compile(rf"\b{re.escape(target)}\b", flags=re.IGNORECASE)

            if source_pattern.search(text) and not target_pattern.search(text):
                findings.append(
                    _issue(
                        page.page_number,
                        lang,
                        f"Reference terminology mismatch: found '{source}' without preferred term '{target}' ({origin}).",
                        f"Replace '{source}' with preferred terminology '{target}'.",
                        category="Terminology",
                    )
                )
                page_hits += 1

            if page_hits >= 8:
                break

    return findings


def _check_reference_style_rules(
    report: ParsedDocument, style_rules: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """Apply deterministic style-guide rules (forbidden/replacement) extracted from style docs."""
    findings: List[Dict[str, Any]] = []
    lang = report.metadata.language
    report_lang = (lang or "").strip().lower()

    for page in report.pages:
        text = page.text or ""
        if not text.strip():
            continue

        page_hits = 0
        for rule in style_rules:
            rule_type = (rule.get("type") or "").strip().lower()
            source = (rule.get("source") or "").strip()
            target = (rule.get("target") or "").strip()
            rule_lang = (rule.get("language") or "Any").strip().lower()
            origin = (rule.get("origin") or "style guide").strip()

            if not source:
                continue
            if rule_lang == "french" and report_lang != "french":
                continue
            if rule_lang == "english" and report_lang != "english":
                continue

            source_pattern = re.compile(rf"\b{re.escape(source)}\b", flags=re.IGNORECASE)
            if not source_pattern.search(text):
                continue

            if rule_type == "forbidden":
                findings.append(
                    _issue(
                        page.page_number,
                        lang,
                        f"Style guide violation: forbidden term '{source}' found ({origin}).",
                        "Replace with approved Canadian/CBC style equivalent.",
                        category="Terminology",
                    )
                )
                page_hits += 1
            elif rule_type == "replacement" and target:
                target_pattern = re.compile(rf"\b{re.escape(target)}\b", flags=re.IGNORECASE)
                if not target_pattern.search(text):
                    findings.append(
                        _issue(
                            page.page_number,
                            lang,
                            f"Style guide replacement required: '{source}' should be '{target}' ({origin}).",
                            f"Replace '{source}' with '{target}'.",
                            category="Terminology",
                        )
                    )
                    page_hits += 1

            if page_hits >= 8:
                break

    return findings
