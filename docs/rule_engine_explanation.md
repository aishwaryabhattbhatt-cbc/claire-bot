# Explanation of `app/services/rule_engine.py`

This document explains the code in `app/services/rule_engine.py` in simple language.

## Purpose
The file contains deterministic (rule-based) checks that scan a parsed report for precise, repeatable issues that are hard for an LLM to guarantee. These checks find formatting, terminology, methodology, and data-consistency problems and return them in a structured list called "findings." Each finding is a small dictionary describing the issue.

## High-level flow
- `run_deterministic_checks(report, benchmark, glossary_rules, style_rules)` is the main entry point.
  - It runs several smaller checks in order and collects their results.
  - It returns a list of findings.

## Findings format
Each finding is a dictionary with these keys:
- `page_number` (int): the page where the issue was found.
- `language` (str): the report language (e.g., "French").
- `category` (str): a short category like "Terminology" or "Data Accuracy".
- `issue_detected` (str): a short description of the detected problem.
- `proposed_change` (str): a recommended change.
- `source` (str): where the finding came from; deterministic checks set this to `deterministic`.

The helper `_issue(...)` builds this dictionary for each detected problem.

## Individual checks (simple descriptions)
1. `_check_french_language_purity(report)`
   - Runs only for French reports.
   - Scans each page for English words that should be written in French (a small predefined list).
   - If it finds an English word (e.g., "television"), it suggests the French replacement (e.g., "télévision").
   - Each match becomes a `Language Purity` finding.

2. `_check_age_labels(report)`
   - Looks for age ranges like "18-24" or "18 à 24" that are missing the word "ans".
   - If it finds `18-24` without `ans`, it suggests using `18-24 ans`.
   - Category: `Formatting & Consistency`.

3. `_check_methodology_consistency(report)`
   - Reads the first page to infer whether the sample is "francophones", "anglophones", or "canadiens".
   - Scans pages that describe the results to ensure the reported respondent group matches the inferred sample.
   - If the page text says "répondants anglophones" but the inferred sample was "francophones", it flags a `Methodology` mismatch.

4. `_infer_sample_from_first_page(text)`
   - Small helper used by methodology checks to guess the sample group from the first page text.

5. `_check_benchmark_alignment(report, benchmark)`
   - Compares the report against a benchmark report (if provided).
   - Checks page count differences and page-level percentage mismatches.
   - If percentage values differ between the report and benchmark on a page, it emits a `Data Accuracy` finding.

6. `_check_sentence_capitalization(report)`
   - Splits page text into sentences and checks whether each sentence starts with a capital letter.
   - Skips sentences that start with a percentage (e.g., "45 % ...").
   - Emits `Formatting & Consistency` findings when sentences start with a lowercase letter.

7. Glossary/Terminology checks (split into two rules)
    - The glossary rules are still extracted from reference XLSX files; each rule includes:
       - `source` (column 1): the canonical term
       - `target` (column 2): the canonical definition or preferred wording
       - `language` and `origin` (which file/sheet it came from)
    - The logic is now split into two deterministic checks:
       1. `_check_reference_terms(report, glossary_rules)` — Term usage checks
            - Ensures terms used in the report match the canonical `source` (column 1).
            - Detects case-insensitive occurrences of a term variant but flags a finding when the exact canonical (case-sensitive) `source` form is missing on the page.
            - Emits `Terminology` findings with guidance to use the exact canonical term.
       2. `_check_glossary_definition_pages(report, glossary_rules)` — Definition/glossary-page checks
            - Detects pages that look like glossary or definitions pages (simple keyword heuristics).
            - For such pages, when a canonical `source` term appears but the exact canonical `target` definition (column 2) does not appear as a case-sensitive substring, it flags a definition mismatch.
            - Emits `Terminology` findings recommending the exact canonical definition be used.
    - Common behavior for both checks:
       - Case-sensitive matching is used for the canonical comparisons per configuration.
       - Rules respect the rule language (`rule['language']`) and skip non-matching report languages.
       - Per-page caps (e.g., max ~8 hits) prevent flooding.
    - The legacy combined `_check_reference_glossary` is retained as a no-op for compatibility; the two focused checks above implement the current behavior.

8. `_check_reference_style_rules(report, style_rules)`
   - Applies style guide rules (forbidden/replacement) pulled from style documents.
   - If a forbidden term is present, it flags a `Terminology` finding.
   - If a replacement rule exists and the replacement is not found, it suggests the replacement.

## Practical notes and behaviors
- The glossary extractor (`app/services/reference_service.py`) finds which sheet columns are source vs target. If a sheet has header names, it maps column names like "source", "target", "language" to the correct columns. If no header is present, it uses the first two non-empty columns as (source, target).
- Checks are intentionally strict and deterministic so you can rely on them for exact matches (term spelling and exact definition matching are case-sensitive and strict by the recent changes).
- To avoid overwhelming output, checks often stop after a page-level cap (`page_hits >= 8`).

## Where findings are used
- Findings are merged with LLM findings later in the pipeline. Deterministic findings are now tagged with `source: "deterministic"` so they can be preserved and exported separately (for example, written into a separate deterministic block in CSV/Sheets).

## How to adjust behavior
- Case-sensitivity: current checks are case-sensitive by request. To relax this, lower-case both rule and text before matching.
- Definition matching: currently requires exact substring match of column 2. To allow small variations, consider normalizing whitespace and punctuation or using fuzzy matching.

## File location
- You can find the code at `app/services/rule_engine.py` in the repository root.

---

If you want, I can also:
- Add a short example showing an input glossary row and a sample page text that triggers (or does not trigger) a finding, or
- Add unit tests for a few glossary and style rule cases.

