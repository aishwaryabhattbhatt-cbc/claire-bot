# Reference Service

**Purpose:** Load and parse the project's reference files (glossaries, style sheets, mappings) used by deterministic checks.

**Key functions:**
- Read XLSX/CSV reference files and detect the columns that represent `source` (term) and `target` (definition/style).
- Build `glossary_rules` and style mappings consumed by `rule_engine` and other services.

**Inputs:** path to reference directory / files.

**Outputs:** structured rules list/dicts with canonical `source`/`target` entries and metadata (sheet name, row).

**Side effects:** Normalizes term casing and fallback heuristics for column detection; may log warnings for ambiguous sheets.

**Tests / checks:** Ensure column heuristics work on sample XLSX; verify canonical term extraction and empty-cell handling.
