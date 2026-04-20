# ClaireBot PRD - Current State

## 1. Product Summary
ClaireBot is an internal QA tool for reviewing MTM/OTM research reports. Users upload a French report for single-document review or upload a French report plus an English benchmark for comparison review. The system parses the documents, runs deterministic QA checks, runs a Gemini-based review pass, normalizes and deduplicates findings, and exports the result to Google Sheets.

This PRD reflects the product state implemented in the repository as of April 8, 2026.

## 2. Current Product Status

### Shipped
- FastAPI backend with a single-page web UI.
- File upload flow for PDF, PPTX, DOCX, and DOC review inputs.
- Two review modes:
  - `french_review`
  - `comparison`
- Deterministic rule engine for exact checks such as age-label formatting, methodology alignment, sentence capitalization, French language purity, glossary/style-based checks, and benchmark percentage/page-count alignment.
- Gemini-only LLM review path.
- Startup loading of reference documents from the local `reference/` directory.
- Custom instruction management endpoints for review modes.
- Google Sheets export for findings.
- SSE-based streaming progress updates for long-running reviews.
- Gemini usage and estimated cost tracking persisted to local processed storage.

### Partially implemented or limited
- PDF page numbering currently falls back to sequential numbering rather than reliably extracting visible page numbers from document chrome.
- DOCX parsing treats the full document as a single page.
- PowerPoint and PDF visual checks depend mostly on extracted text and simple structural signals rather than deep visual analysis.
- Placeholder review-status endpoint exists, but there is no persisted async job state model.
- Google Sheets output currently writes 5 columns, not the older 4-column format described in legacy docs.

### Not in current scope
- Full typography verification.
- Reliable hyperlink validation inside documents.
- Robust chart OCR and image-text extraction.
- Metadata or slide-master review.
- Multi-user auth, permissions, or job history dashboard.

## 3. Problem
Editorial and research teams need a faster, more consistent way to QA MTM/OTM reports against language, glossary, branding, structure, and methodology rules. Manual review is slow, repetitive, and vulnerable to missed inconsistencies, especially when a French report must match an English benchmark.

## 4. Users
- MTM/OTM editors
- Research QA reviewers
- Internal operations teams preparing report deliverables

## 5. User Jobs
- Upload a French report and receive structured QA findings.
- Upload a French report plus an English benchmark and identify mismatches.
- Review findings in a sheet-ready format.
- Adjust mode-specific instructions without editing backend code.
- Verify that the tool is grounded in current glossary and style references.

## 6. Product Goals
- Reduce manual QA effort for report review.
- Improve consistency of terminology, methodology, and structural checks.
- Combine deterministic rules with LLM judgment instead of relying on either alone.
- Return operational findings that can be copied directly into editorial workflows.
- Make processing status visible enough that users can trust what the system is doing.

## 7. Non-Goals
- Full document rewriting.
- Pixel-perfect design QA.
- Comprehensive OCR of charts and embedded imagery.
- General-purpose translation.
- Workflow orchestration beyond review and export.

## 8. Primary Workflows

### Workflow A: French Review
1. User uploads a French report.
2. User selects `french_review`.
3. User may supply additional context.
4. System parses the report.
5. System runs deterministic checks.
6. System runs Gemini review using default or saved French instructions.
7. System filters, categorizes, and deduplicates findings.
8. System exports findings to Google Sheets when enabled.
9. UI shows findings, export status, and processing timeline.

### Workflow B: Comparison Review
1. User uploads a French report and an English benchmark.
2. User enables comparison mode and selects `comparison`.
3. User may supply additional context.
4. System parses both documents.
5. System runs deterministic checks, including benchmark alignment.
6. System runs Gemini review using default or saved comparison instructions.
7. System filters, categorizes, and deduplicates findings.
8. System exports findings to Google Sheets when enabled.
9. UI shows findings, export status, and processing timeline.

## 9. Functional Requirements

### 9.1 Input Handling
- The system must accept report uploads through `/review` and `/review/stream`.
- Supported extensions for report review are `.pdf`, `.pptx`, `.docx`, and `.doc`.
- Comparison mode must require a benchmark file.
- `french_review` must require `report_language=French`.
- The system must reject unsupported file types and invalid mode combinations with clear HTTP 400 errors.

### 9.2 Document Parsing
- PDF parsing must extract per-page text and basic image/table presence.
- PPTX parsing must extract per-slide text and detect images/tables at a basic level.
- DOCX parsing must extract paragraph text and table presence.
- Reference XLSX files must be parsed for glossary rule extraction.
- Parsed content must be normalized into a common internal document model.

### 9.3 Deterministic QA
- The system must run deterministic checks before the LLM pass.
- Current deterministic checks include:
  - French language purity keyword detection
  - age-range `ans` enforcement
  - methodology sample alignment
  - sentence capitalization
  - benchmark page-count and percentage alignment
  - glossary term enforcement from reference files
  - glossary-definition page checks
  - style-rule checks derived from reference files
- Deterministic findings must be tagged with `source=deterministic`.

### 9.4 LLM Review
- The system must use Gemini as the only active LLM provider.
- The prompt must include:
  - mode-specific instructions
  - parsed report content
  - benchmark content when applicable
  - reference context loaded from local reference files
  - optional additional user context
- The LLM output must be JSON with a `findings` array.
- If the LLM fails, the system must still return deterministic findings.

### 9.5 Instruction Management
- The product must expose endpoints to:
  - read active instructions
  - update instructions
  - reset instructions by mode
- Instructions must be stored in local processed storage and applied at runtime without code edits.

### 9.6 Reference Management
- Reference documents must load from the local `reference/` directory on startup.
- The system must expose reference inventory to the UI.
- The system must support global reference uploads for:
  - benchmark report
  - age references
  - text preferences
- Replacing a global reference file must refresh cached reference context.

### 9.7 Findings Processing
- Findings must be normalized into approved categories.
- Low-value findings such as noisy acronym-first-use results must be filtered.
- Exact duplicates must be removed.
- Same-page same-category duplicates should collapse to the most useful finding, with deterministic results preferred over LLM results when both exist.

### 9.8 Export
- When Sheets export is enabled and credentials are configured, the system must append findings to Google Sheets.
- The current output schema is:
  - `Page Number`
  - `Language of the report`
  - `Category`
  - `Issue Detected`
  - `Proposed Change`
- If no findings exist, the system must still write a no-issues row.

### 9.9 UX and Status Visibility
- The web UI must support file upload, review-mode selection, benchmark upload, and optional additional context.
- The streaming endpoint must emit phase and substep progress updates via SSE.
- The final response must expose findings, timeline, LLM status, Sheets status, and usage metadata when available.

## 10. API Surface

### Core Review
- `POST /review`
- `POST /review/stream`

### Instruction Management
- `GET /instructions`
- `PUT /instructions`
- `POST /instructions/reset`

### Reference Management
- `GET /references`
- `POST /references/global-upload`
- `DELETE /references/global-upload`

### Misc
- `GET /`
- `GET /health`
- `GET /review/{job_id}` (placeholder)
- `GET /docs/rule_engine`

## 11. Success Criteria
- Users can complete French review and comparison review from the web UI without manual backend intervention.
- Findings are returned in a structured, categorized format suitable for QA operations.
- Reference files materially influence deterministic and LLM review behavior.
- Reviews still complete with useful output when the LLM path fails.
- Streaming status makes long-running reviews understandable to users.

## 12. Risks
- Extracted text quality may be insufficient for deep visual QA.
- Sequential page numbering may diverge from visible document numbering.
- Reference documents may be incomplete, stale, or inconsistently structured.
- Gemini output quality depends on prompt discipline and parsed document fidelity.
- Google Sheets export is sensitive to credentials and template configuration.

## 13. Technical Stack
- Backend: Python 3.11+, FastAPI, Uvicorn
- Validation/config: Pydantic v2, `pydantic-settings`, `python-dotenv`
- Parsing:
  - PDF: PyMuPDF, pdfplumber
  - DOCX: python-docx
  - PPTX: python-pptx
  - XLSX: openpyxl
- OCR/image support dependencies: Pillow, pytesseract
- LLM: Google Gemini via `google-generativeai`
- Export/integrations: Google Sheets API via `google-api-python-client` and `google-auth`
- Frontend: server-rendered static HTML/CSS/JavaScript
- Tests: pytest
- Deployment assets: Dockerfile and Cloud Run config

## 14. Near-Term Product Priorities
1. Fix page-number fidelity so findings reference visible document numbering when possible.
2. Improve DOCX segmentation beyond single-page treatment.
3. Tighten the contract between PRD, prompts, and Sheets schema so output expectations stay aligned.
4. Expand deterministic coverage for footnotes, summary accuracy, and navigation checks.
5. Add real persisted job tracking if asynchronous processing becomes necessary.
