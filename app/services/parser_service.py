from pathlib import Path
from typing import Optional

from app.models import ParsedDocument
from app.parsers import PDFParser, PPTXParser, DOCXParser


class DocumentParserService:
    """Service for parsing various document types"""
    
    def __init__(self):
        self.pdf_parser = PDFParser()
        self.pptx_parser = PPTXParser()
        self.docx_parser = DOCXParser()
    
    def parse_document(self, file_path: str, language: str = "French") -> ParsedDocument:
        """
        Parse a document based on its file type.
        
        Args:
            file_path: Path to document
            language: Document language
            
        Returns:
            ParsedDocument with extracted content
            
        Raises:
            ValueError: If file type is not supported
        """
        file_path = Path(file_path)
        file_ext = file_path.suffix.lower()
        
        if file_ext == ".pdf":
            return self.pdf_parser.parse(str(file_path), language)
        elif file_ext in [".pptx", ".ppt"]:
            return self.pptx_parser.parse(str(file_path), language)
        elif file_ext in [".docx", ".doc"]:
            return self.docx_parser.parse(str(file_path), language)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")
    
    def get_page_text(self, file_path: str, page_number: int) -> str:
        """
        Get text from a specific page.
        
        Args:
            file_path: Path to document
            page_number: Page number (1-indexed)
            
        Returns:
            Text content from that page
        """
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext == ".pdf":
            return self.pdf_parser.extract_text_from_page(file_path, page_number)
        else:
            raise NotImplementedError(f"Page extraction not implemented for {file_ext}")
