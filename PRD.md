# Clairebot PRD (MTM/OTM Report Reviewer)

## 1) Overview
Clairebot is an AI agent that reviews French (OTM) and English (MTM) reports in PDF/DOC/PPT format and returns structured, page-by-page edits in English (with French alternatives). It enforces MTM/Radio‑Canada standards, performs strict French language purity checks, and validates data alignment against English benchmarks.

## 2) Goals
- Deliver precise, page-level quality control for reports and infographics.
- Enforce linguistic, formatting, branding, and methodological standards.
- Compare French reports to English benchmarks with strict data accuracy.
- Provide outputs in a consistent, spreadsheet-ready format.

## 3) Non‑Goals
- No rewriting of full reports; only actionable corrections.
- No formatting in the output beyond tabular rows.
- No use of metadata-based page numbers.

## 4) Users
- MTM/OTM report editors, QA reviewers, research teams.

## 5) Inputs
- Single report: PDF, DOCX, PPTX.
- Comparative review: French report + English benchmark.

## 6) Output Requirements
- Google Sheets link with 4 columns:
  1) Page Number (document page number only)
  2) Language of the report (French or English)
  3) Issue Detected
  4) Proposed Change
- Each issue must be a separate row per page.
- English explanations; French alternative phrasing when relevant.
- No long paragraphs.

## 7) Functional Requirements

### Document Handling
- Accept PDF/DOCX/PPTX.
- Extract text, tables, and visual labels.
- Respect visible page numbering only.

### Editing & QA
- Language purity (no English words in French text/graphics).
- Glossary enforcement (ClaireBot MTM FR + Guide de style français).
- Data validation (numbers, labels, insights vs benchmark).
- Footnote integrity (asterisks and matching notes).
- Styling consistency (font, alignment, bolding, color).
- Branding verification (OTM vs MTM logos, first/last page).
- Methodology target sample correctness.
- Summary slide vs body data alignment.
- TOC accuracy + hyperlink validation.
- Date correctness (title slide date cannot be past).

### Comparison Rules
- English report is the source of truth.
- Page count and content alignment.
- Translation alignment of meaning and flow.

## 8) Memory & Context
- Persist conversation history for repeated corrections.
- Allow future additions to glossary/style rules.

## 9) Quality Metrics
- % of issues caught vs manual QA benchmark.
- False positive rate.
- Time to deliver output per report.

## 10) Risks
- Poor OCR on charts/graphics.
- Inconsistent page numbering.
- Missing glossary or style guide access.

---

# V1 (MVP) Scope

## Core Capabilities
1) **Single-report review** (French or English).
2) **Strict output format** (Google Sheets link with 4 columns).
3) **Page-by-page issue detection** for:
   - Language purity
   - Glossary compliance
   - Footnote consistency
   - Basic data accuracy (within the same report)
   - Branding/logo check (first/last page)
   - Methodology target sample text
   - Title slide date rule

## Comparative Review (Limited)
- If both reports provided, verify:
  - Page count match
  - Key numbers and labels match
  - Summary slide matches body data
  - Translation alignment for key insights

## Explicit Exclusions in V1
- Full typography inspection (font size, colors) beyond basic consistency flags.
- Deep hyperlink validation (flag if visible mismatch only).
- Advanced chart OCR for precise numeric extraction.
- Automated glossary expansion.

## MVP Success Criteria
- Output is strictly in the required 4-column sheet format.
- Detects and reports common errors with page precision.
- Produces consistent, usable QC feedback for real reports.
