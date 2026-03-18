# Parser Service

**Purpose:** Convert uploaded documents (PDFs, text, etc.) into plain text chunks and structured pages used by detectors.

**Key functions:**
- Extract text from files, split into pages/blocks, and provide page-level metadata (page number, filename, text length).
- Normalize whitespace and perform light cleanup to improve downstream rule matching.

**Inputs:** file path / upload stream and file metadata.

**Outputs:** list of page dicts: `{page_number, text, metadata}` ready for rule checks and LLM consumption.

**Side effects:** May write temporary files or use subprocesses for heavy extraction (PDF tools); must handle large files and memory usage.

**Tests / checks:** Confirm text extraction fidelity on sample PDFs, ensure page ordering preserved, and confirm no resource leaks on failure.
