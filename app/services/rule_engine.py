import re
import unicodedata
from typing import Any, Dict, List, Optional

from app.models import ParsedDocument


def run_deterministic_checks(
    report: ParsedDocument,
    benchmark: Optional[ParsedDocument] = None,
    glossary_rules: Optional[List[Dict[str, str]]] = None,
    style_rules: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    # Restoring deterministic checks for structured, exact rules that are hard
    # for an LLM to guarantee (formatting, numeric consistency, glossary
    # membership, language purity and methodology alignment). Spell-checking
    # (previously disabled) will remain off due to false-positive noise.

    findings.extend(_check_age_labels(report))
    findings.extend(_check_methodology_consistency(report))
    findings.extend(_check_sentence_capitalization(report))

    # Language purity checks for French (repetition, English tokens in French
    # content, etc.)
    if report.metadata.language.lower() == "french":
        findings.extend(_check_french_language_purity(report))

    # Benchmark alignment (percentages, page counts) when a benchmark is
    # provided.
    if benchmark is not None:
        findings.extend(_check_benchmark_alignment(report, benchmark))

    # Re-introduce glossary-based checks when rules are supplied.
    # Split into two deterministic rules:
    # 1) Check terms used in the report against the canonical term (column 1).
    # 2) Check glossary/definitions pages in the report against the canonical
    #    definition (column 2).
    if glossary_rules:
        findings.extend(_check_reference_terms(report, glossary_rules))
        findings.extend(_check_glossary_definition_pages(report, glossary_rules))

    if style_rules:
        findings.extend(_check_reference_style_rules(report, style_rules))

    return findings


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
    """Legacy combined glossary check (kept for compatibility)."""
    # Note: functionality split into two separate checks:
    # - _check_reference_terms
    # - _check_glossary_definition_pages
    return []


def _is_glossary_page(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    return bool(re.search(r"\b(glossaire|glossary|d\u00e9finitions|definitions|liste des d\u00e9finitions|list of definitions)\b", lower))


def _check_reference_terms(report: ParsedDocument, glossary_rules: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Check that terms used in the report match the canonical term (column 1).

    Flags a finding only when the report appears to contain a loose variant of
    the term without containing the normalized canonical term itself.

    Important: pure case differences should not be flagged. In practice the
    parser and OCR layers can change casing or unicode normalization while the
    underlying term is still correct.
    """
    findings: List[Dict[str, Any]] = []
    lang = report.metadata.language
    report_lang = (lang or "").strip().lower()

    def _normalize_text(s: str) -> str:
        # Normalize unicode (NFC) and convert NBSP to normal space, collapse multiple spaces.
        if not s:
            return ""
        n = unicodedata.normalize("NFC", s)
        n = n.replace("\u00A0", " ")
        n = re.sub(r"\s+", " ", n)
        return n.strip()

    def _contains_canonical_term(text_value: str, canonical_term: str) -> bool:
        # Treat case-only differences as equivalent to avoid false positives
        # like "Télévision en ligne" vs "télévision en ligne".
        text_folded = text_value.casefold()
        canonical_folded = canonical_term.casefold()
        esc = re.escape(canonical_folded).replace(r"\ ", r"\s+")
        return bool(re.search(rf"(?<!\w){esc}(?!\w)", text_folded))

    def _strip_accents(s: str) -> str:
        decomposed = unicodedata.normalize("NFD", s)
        return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")

    def _contains_loose_variant(text_value: str, canonical_term: str) -> bool:
        # Detect looser variants such as accent loss while still requiring the
        # same underlying token sequence.
        text_folded = _strip_accents(text_value).casefold()
        canonical_folded = _strip_accents(canonical_term).casefold()
        esc = re.escape(canonical_folded).replace(r"\ ", r"\s+")
        return bool(re.search(rf"(?<!\w){esc}(?!\w)", text_folded))

    for page in report.pages:
        raw_text = page.text or ""
        text = _normalize_text(raw_text)
        if not text:
            continue

        page_hits = 0
        for rule in glossary_rules:
            source = (rule.get("source") or "").strip()
            rule_lang = (rule.get("language") or "Any").strip().lower()
            origin = (rule.get("origin") or "reference glossary").strip()

            if not source:
                continue
            if rule_lang == "french" and report_lang != "french":
                continue
            if rule_lang == "english" and report_lang != "english":
                continue

            source_norm = _normalize_text(source)
            if not source_norm:
                continue

            # If the normalized canonical term is present, it is acceptable.
            if _contains_canonical_term(text, source_norm):
                continue

            if _contains_loose_variant(text, source_norm):
                findings.append(
                    _issue(
                        page.page_number,
                        lang,
                        f"Term usage mismatch: found variant of '{source}' but not the canonical form ({origin}).",
                        f"Use the exact canonical term: '{source}'.",
                        category="Terminology",
                    )
                )
                page_hits += 1

            if page_hits >= 8:
                break

    return findings


def _check_glossary_definition_pages(report: ParsedDocument, glossary_rules: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Check glossary/definition pages in the report against canonical definitions (column 2).

    For each page that looks like a glossary/definitions page, if it contains
    the canonical term (column 1) but does not contain the exact canonical
    definition (column 2) as a case-sensitive substring, emit a finding.
    """
    findings: List[Dict[str, Any]] = []
    lang = report.metadata.language
    report_lang = (lang or "").strip().lower()

    for page in report.pages:
        raw_text = page.text or ""
        text = unicodedata.normalize("NFC", raw_text).replace("\u00A0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if not _is_glossary_page(text):
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

            # Normalize rule text for matching
            source_norm = unicodedata.normalize("NFC", source).replace("\u00A0", " ")
            source_norm = re.sub(r"\s+", " ", source_norm).strip()
            target_norm = unicodedata.normalize("NFC", target).replace("\u00A0", " ") if target else ""
            target_norm = re.sub(r"\s+", " ", target_norm).strip() if target_norm else ""

            # If term appears on glossary page but canonical definition is missing
            sp_esc = re.escape(source_norm).replace(r"\\ ", r"\\s+")
            source_pattern = re.compile(rf"\b{sp_esc}\b")
            target_pattern = re.compile(re.escape(target_norm)) if target_norm else None

            if source_pattern.search(text) and not (target_pattern and target_pattern.search(text)):
                findings.append(
                    _issue(
                        page.page_number,
                        lang,
                        f"Glossary definition mismatch for '{source}': page does not contain the canonical definition ({origin}).",
                        f"Replace glossary definition with exact canonical text: '{target}'.",
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
