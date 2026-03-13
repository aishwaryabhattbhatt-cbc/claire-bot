"""
Reference document service.

Loads all documents from the reference directory once at startup and
caches their text content for injection into LLM prompts.
"""
import logging
from pathlib import Path
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".docx", ".doc", ".xlsx", ".xls"}

# Module-level cache — loaded once at startup, never reloaded
_reference_context: Optional[str] = None
_loaded: bool = False


def load_reference_documents() -> None:
    """
    Parse all documents in the reference directory and cache their text.
    Call once during application startup.
    """
    global _reference_context, _loaded
    if _loaded:
        return

    settings = get_settings()
    ref_dir = Path(settings.reference_dir)

    if not ref_dir.exists() or not ref_dir.is_dir():
        logger.info("Reference directory '%s' not found — skipping reference loading.", ref_dir)
        _reference_context = None
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
        _loaded = True
        return

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
        except Exception as exc:
            logger.warning("Could not parse reference document '%s': %s", path.name, exc)

    if blocks:
        _reference_context = "\n\n".join(blocks)
        logger.info("Reference context loaded: %d document(s).", len(blocks))
    else:
        _reference_context = None
        logger.info("Reference directory had files but none could be parsed.")

    _loaded = True


def get_reference_context() -> Optional[str]:
    """Return the cached reference context string, or None if not loaded."""
    if not _loaded:
        load_reference_documents()
    return _reference_context
