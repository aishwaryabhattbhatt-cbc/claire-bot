from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class PageContent:
    """Represents content from a single page"""
    page_number: int  # Visible page number (not metadata)
    text: str
    has_images: bool = False
    has_tables: bool = False
    images_text: List[str] = None  # OCR text from images/charts
    
    def __post_init__(self):
        if self.images_text is None:
            self.images_text = []


@dataclass
class DocumentMetadata:
    """Document-level metadata"""
    filename: str
    file_type: str  # pdf, pptx, docx
    total_pages: int
    language: str  # French or English


@dataclass
class ParsedDocument:
    """Complete parsed document structure"""
    metadata: DocumentMetadata
    pages: List[PageContent]
    raw_metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.raw_metadata is None:
            self.raw_metadata = {}
