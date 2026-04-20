# Alignment and reference checks: reference document loading/caching, benchmark
# comparison, and glossary/style-guide enforcement (moved from reference_service.py
# and rule_engine.py).

import importlib
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.models import ParsedDocument

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".docx", ".doc", ".xlsx", ".xls"}

# ─────────────────────────────────────────────────────────────────────────────
# Module-level reference document cache (loaded once at startup)
# ─────────────────────────────────────────────────────────────────────────────

_reference_context: Optional[str] = None
_reference_glossary_rules: List[Dict[str, str]] = []
_reference_style_rules: List[Dict[str, str]] = []
_reference_documents: List[Dict[str, str]] = []
_loaded: bool = False


def load_reference_documents() -> None:
    """
    Parse all documents in the reference directory and cache their text.
    Call once during application startup.
    """
    global _reference_context, _reference_glossary_rules, _reference_style_rules, _reference_documents, _loaded
    if _loaded:
        return

    settings = get_settings()
    ref_dir = Path(settings.reference_dir)

    if not ref_dir.exists() or not ref_dir.is_dir():
        logger.info("Reference directory '%s' not found — skipping reference loading.", ref_dir)
        _reference_context = None
        _reference_glossary_rules = []
        _reference_style_rules = []
        _reference_documents = []
        _loaded = True
        return

    # Import here to avoid circular imports
    from app.services.parser_service import DocumentParserService

    parser = DocumentParserService()
    blocks: list[str] = []

    files = sorted(
        f for f in ref_dir.iterdir()
        if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTENSIONS
    )

    if not files:
        logger.info("No supported documents found in reference directory '%s'.", ref_dir)
        _reference_context = None
        _reference_glossary_rules = []
        _reference_style_rules = []
        _reference_documents = []
        _loaded = True
        return

    glossary_rules: List[Dict[str, str]] = []
    style_rules: List[Dict[str, str]] = []
    documents_meta: List[Dict[str, str]] = []
    for path in files:
        doc_type = _classify_reference_document(path)
        documents_meta.append(
            {
                "name": path.name,
                "type": doc_type,
            }
        )
        try:
            parsed = parser.parse_document(path, language="English")
            doc_text_parts = []
            for page in parsed.pages:
                text = page.text.strip()
                if text:
                    # Cap each page at 3000 chars to keep prompt size manageable
                    if len(text) > 3000:
                        text = text[:3000] + "..."
                    doc_text_parts.append(f"  [Page {page.page_number}]: {text}")

            if doc_text_parts:
                blocks.append(
                    f"--- Reference Document: {path.name} ---\n" + "\n".join(doc_text_parts)
                )
                logger.info("Loaded reference document: %s (%d pages)", path.name, len(doc_text_parts))

            if path.suffix.lower() in {".xlsx", ".xls"}:
                glossary_rules.extend(_extract_glossary_rules_from_xlsx(path))
            if _looks_like_style_guide(path.name):
                style_rules.extend(_extract_style_rules_from_text(path.name, "\n".join(doc_text_parts)))
        except Exception as exc:
            logger.warning("Could not parse reference document '%s': %s", path.name, exc)

    if blocks:
        _reference_context = "\n\n".join(blocks)
        logger.info("Reference context loaded: %d document(s).", len(blocks))
    else:
        _reference_context = None
        logger.info("Reference directory had files but none could be parsed.")

    _reference_glossary_rules = _dedupe_rules(glossary_rules)
    if _reference_glossary_rules:
        logger.info("Reference glossary rules loaded: %d", len(_reference_glossary_rules))

    _reference_style_rules = _dedupe_style_rules(style_rules)
    if _reference_style_rules:
        logger.info("Reference style rules loaded: %d", len(_reference_style_rules))

    _reference_documents = documents_meta

    _loaded = True


def get_reference_context() -> Optional[str]:
    """Return the cached reference context string, or None if not loaded."""
    if not _loaded:
        load_reference_documents()
    return _reference_context


def get_reference_glossary_rules() -> List[Dict[str, str]]:
    """Return parsed glossary replacement rules extracted from reference XLSX files."""
    if not _loaded:
        load_reference_documents()
    return list(_reference_glossary_rules)


def get_reference_style_rules() -> List[Dict[str, str]]:
    """Return parsed style guide rules extracted from reference style documents."""
    if not _loaded:
        load_reference_documents()
    return list(_reference_style_rules)


def get_reference_documents() -> List[Dict[str, str]]:
    """Return reference document metadata for UI display."""
    if not _loaded:
        load_reference_documents()
    return list(_reference_documents)


def reload_reference_documents() -> None:
    """Force refresh of cached reference documents and derived rules."""
    global _loaded
    _loaded = False
    load_reference_documents()


# ─────────────────────────────────────────────────────────────────────────────
# Reference document parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _classify_reference_document(path: Path) -> str:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in {".xlsx", ".xls"}:
        return "glossary"
    if "logo" in name:
        return "logo_guidelines"
    if _looks_like_style_guide(name):
        return "style_guide"
    return "reference"


def _extract_glossary_rules_from_xlsx(path: Path) -> List[Dict[str, str]]:
    """Extract source->target terminology rules from XLSX glossary-like sheets."""
    try:
        openpyxl = importlib.import_module("openpyxl")
    except Exception:
        return []

    rules: List[Dict[str, str]] = []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)

    default_lang = _infer_language_from_filename(path.name)

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        header_idx, header_map = _detect_header(rows)
        start_idx = header_idx + 1 if header_idx >= 0 else 0

        for row in rows[start_idx:]:
            if not row:
                continue

            if header_map:
                source = _cell_str(row, header_map.get("source"))
                target = _cell_str(row, header_map.get("target"))
                lang = _cell_str(row, header_map.get("language")) or default_lang
            else:
                non_empty = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if len(non_empty) < 2:
                    continue
                source, target = non_empty[0], non_empty[1]
                lang = default_lang

            if not source or not target:
                continue
            if source.lower() == target.lower():
                continue
            if len(source) < 2 or len(target) < 2:
                continue

            rules.append(
                {
                    "source": source,
                    "target": target,
                    "language": _normalize_language(lang),
                    "origin": f"{path.name}:{sheet_name}",
                }
            )

    wb.close()
    return rules


def _detect_header(rows: List[Any]) -> tuple[int, Dict[str, int]]:
    """Return (header_index, mapping) where mapping contains source/target/language indexes."""
    for i, row in enumerate(rows[:5]):
        values = [str(c).strip().lower() if c is not None else "" for c in row]
        if not any(values):
            continue

        src = _find_header_index(values, ["source", "incorrect", "wrong", "avoid", "à éviter", "term to replace"])
        tgt = _find_header_index(values, ["target", "correct", "preferred", "approved", "replacement", "use", "terme", "french"])
        lng = _find_header_index(values, ["language", "lang", "langue"])

        if src is not None and tgt is not None:
            mapping: Dict[str, int] = {"source": src, "target": tgt}
            if lng is not None:
                mapping["language"] = lng
            return i, mapping

    return -1, {}


def _find_header_index(values: List[str], tokens: List[str]) -> Optional[int]:
    for idx, value in enumerate(values):
        for token in tokens:
            if token in value:
                return idx
    return None


def _cell_str(row: Any, idx: Optional[int]) -> str:
    if idx is None:
        return ""
    if idx >= len(row):
        return ""
    value = row[idx]
    return str(value).strip() if value is not None else ""


def _infer_language_from_filename(filename: str) -> str:
    lower = filename.lower()
    if re.search(r"\b(fr|french|français)\b", lower):
        return "French"
    if re.search(r"\b(en|english|anglais)\b", lower):
        return "English"
    return "Any"


def _normalize_language(language: str) -> str:
    low = (language or "").strip().lower()
    if low in {"fr", "french", "français", "francais"}:
        return "French"
    if low in {"en", "english", "anglais"}:
        return "English"
    return "Any"


def _dedupe_rules(rules: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    result: List[Dict[str, str]] = []
    for rule in rules:
        key = (
            (rule.get("source") or "").strip().lower(),
            (rule.get("target") or "").strip().lower(),
            (rule.get("language") or "Any").strip(),
        )
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(rule)
    return result


def _looks_like_style_guide(filename: str) -> bool:
    lower = filename.lower()
    return "style guide" in lower or "guide de style" in lower


def _extract_style_rules_from_text(filename: str, text: str) -> List[Dict[str, str]]:
    """
    Extract deterministic style rules from English/French style guide text.

    Rule shapes:
    - {type: 'forbidden', source, language, origin}
    - {type: 'replacement', source, target, language, origin}
    """
    rules: List[Dict[str, str]] = []
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return rules

    language = _infer_language_from_filename(filename)
    lower = cleaned.lower()

    # Pattern: "Avoid British spellings (a, b, c)"
    avoid_match = re.search(r"avoid\s+british\s+spellings\s*\(([^)]+)\)", lower, flags=re.IGNORECASE)
    if avoid_match:
        items = [it.strip(" .;:") for it in avoid_match.group(1).split(",")]
        for item in items:
            if item and item.lower() not in {"etc"} and len(item) >= 4:
                rules.append(
                    {
                        "type": "forbidden",
                        "source": item,
                        "language": "English",
                        "origin": filename,
                    }
                )

    # Pattern: "X is no longer used. It has been replaced by: Y"
    for m in re.finditer(
        r"[\u201c\u201d\"']?([^\u201c\u201d\"'\.]{2,80})[\u201c\u201d\"']?\s+is\s+no\s+longer\s+used\.\s*(?:it\s+has\s+been\s+replaced\s+by:|use)\s+([^\.]{2,120})",
        cleaned,
        flags=re.IGNORECASE,
    ):
        source = m.group(1).strip(" .;:\"\u2018\u2019\u201c\u201d")
        target = m.group(2).strip(" .;:\"\u2018\u2019\u201c\u201d")
        if (
            source
            and target
            and source.lower() != target.lower()
            and len(source) <= 40
            and len(target) <= 80
            and "no longer used" not in target.lower()
            and "table below" not in source.lower()
        ):
            rules.append(
                {
                    "type": "replacement",
                    "source": source,
                    "target": target,
                    "language": language,
                    "origin": filename,
                }
            )

    # French variant: "X n'est plus utilisé ... utiliser Y"
    for m in re.finditer(
        r"[\u00ab\"']?([^\"\u00bb'\.]{2,80})[\u00bb\"']?\s+n['']est\s+plus\s+utilis[ée]\.?(?:\s*il\s+est\s+remplac[ée]\s+par\s*:?|\s*utiliser\s+)([^\.]{2,120})",
        cleaned,
        flags=re.IGNORECASE,
    ):
        source = m.group(1).strip(" .;:\"\u00ab\u00bb")
        target = m.group(2).strip(" .;:\"\u00ab\u00bb")
        if (
            source
            and target
            and source.lower() != target.lower()
            and len(source) <= 40
            and len(target) <= 80
            and "n'est plus utilisé" not in target.lower()
        ):
            rules.append(
                {
                    "type": "replacement",
                    "source": source,
                    "target": target,
                    "language": "French",
                    "origin": filename,
                }
            )

    return rules


def _dedupe_style_rules(rules: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    result: List[Dict[str, str]] = []
    for rule in rules:
        key = (
            (rule.get("type") or "").strip().lower(),
            (rule.get("source") or "").strip().lower(),
            (rule.get("target") or "").strip().lower(),
            (rule.get("language") or "Any").strip(),
        )
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(rule)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Alignment check helpers (moved from rule_engine.py)
# ─────────────────────────────────────────────────────────────────────────────

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


def _is_glossary_page(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    return bool(re.search(
        r"\b(glossaire|glossary|d\u00e9finitions|definitions|liste des d\u00e9finitions|list of definitions)\b",
        lower,
    ))


def _check_benchmark_alignment(report: ParsedDocument, benchmark: ParsedDocument) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    lang = report.metadata.language
    report_lang = (lang or "").strip().lower()

    if report.metadata.total_pages != benchmark.metadata.total_pages:
        findings.append(
            _issue(
                1,
                lang,
                "Page count mismatch versus benchmark.",
                (
                    f"Align page count to the benchmark report ({benchmark.metadata.total_pages} pages)."
                    if report_lang == "english"
                    else f"Aligner le nombre de pages sur le rapport de référence ({benchmark.metadata.total_pages} pages)."
                ),
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
                    (
                        "Update values so they match the benchmark report exactly."
                        if report_lang == "english"
                        else "Mettre à jour les valeurs françaises pour qu'elles correspondent exactement aux valeurs du rapport de référence."
                    ),
                    category="Data Accuracy",
                )
            )

    return findings


def _check_reference_terms(report: ParsedDocument, glossary_rules: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Check that terms used in the report match the canonical term (column 1)."""
    findings: List[Dict[str, Any]] = []
    lang = report.metadata.language
    report_lang = (lang or "").strip().lower()

    def _normalize_text(s: str) -> str:
        if not s:
            return ""
        n = unicodedata.normalize("NFC", s)
        n = n.replace("\u00A0", " ")
        n = re.sub(r"\s+", " ", n)
        return n.strip()

    def _contains_canonical_term(text_value: str, canonical_term: str) -> bool:
        text_folded = text_value.casefold()
        canonical_folded = canonical_term.casefold()
        esc = re.escape(canonical_folded).replace(r"\ ", r"\s+")
        return bool(re.search(rf"(?<!\w){esc}(?!\w)", text_folded))

    def _strip_accents(s: str) -> str:
        decomposed = unicodedata.normalize("NFD", s)
        return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")

    def _contains_loose_variant(text_value: str, canonical_term: str) -> bool:
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
    """Check glossary/definition pages in the report against canonical definitions (column 2)."""
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

            source_norm = unicodedata.normalize("NFC", source).replace("\u00A0", " ")
            source_norm = re.sub(r"\s+", " ", source_norm).strip()
            target_norm = unicodedata.normalize("NFC", target).replace("\u00A0", " ") if target else ""
            target_norm = re.sub(r"\s+", " ", target_norm).strip() if target_norm else ""

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


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_alignment_checks(
    report: ParsedDocument,
    benchmark: Optional[ParsedDocument] = None,
    glossary_rules: Optional[List[Dict[str, str]]] = None,
    style_rules: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """Run benchmark comparison and reference-based alignment checks, return findings."""
    findings: List[Dict[str, Any]] = []

    if benchmark is not None:
        findings.extend(_check_benchmark_alignment(report, benchmark))

    if glossary_rules:
        findings.extend(_check_reference_terms(report, glossary_rules))
        findings.extend(_check_glossary_definition_pages(report, glossary_rules))

    if style_rules:
        findings.extend(_check_reference_style_rules(report, style_rules))

    return findings
