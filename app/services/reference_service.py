"""
Reference document service.

Loads all documents from the reference directory once at startup and
caches their text content for injection into LLM prompts.
"""
import importlib
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".docx", ".doc", ".xlsx", ".xls"}

# Module-level cache — loaded once at startup, never reloaded
_reference_context: Optional[str] = None
_reference_glossary_rules: List[Dict[str, str]] = []
_reference_style_rules: List[Dict[str, str]] = []
_loaded: bool = False


def load_reference_documents() -> None:
    """
    Parse all documents in the reference directory and cache their text.
    Call once during application startup.
    """
    global _reference_context, _reference_glossary_rules, _reference_style_rules, _loaded
    if _loaded:
        return

    settings = get_settings()
    ref_dir = Path(settings.reference_dir)

    if not ref_dir.exists() or not ref_dir.is_dir():
        logger.info("Reference directory '%s' not found — skipping reference loading.", ref_dir)
        _reference_context = None
        _reference_glossary_rules = []
        _reference_style_rules = []
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
        _loaded = True
        return

    glossary_rules: List[Dict[str, str]] = []
    style_rules: List[Dict[str, str]] = []
    for path in files:
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
        r"[“\"']?([^\"”'\.]{2,80})[”\"']?\s+is\s+no\s+longer\s+used\.\s*(?:it\s+has\s+been\s+replaced\s+by:|use)\s+([^\.]{2,120})",
        cleaned,
        flags=re.IGNORECASE,
    ):
        source = m.group(1).strip(" .;:\"'“”")
        target = m.group(2).strip(" .;:\"'“”")
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
        r"[«\"']?([^\"»'\.]{2,80})[»\"']?\s+n['’]est\s+plus\s+utilis[ée]\.?(?:\s*il\s+est\s+remplac[ée]\s+par\s*:?|\s*utiliser\s+)([^\.]{2,120})",
        cleaned,
        flags=re.IGNORECASE,
    ):
        source = m.group(1).strip(" .;:\"'«»")
        target = m.group(2).strip(" .;:\"'«»")
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
