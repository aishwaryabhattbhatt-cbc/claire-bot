# Sheets Service

**Purpose:** Normalize findings and write them to Google Sheets for human review and archival.

**Key functions:**
- `_normalize_findings`: convert app `finding` objects into spreadsheet row arrays, partition deterministic findings and insert header rows.
- Write rows to a target Google Sheet using Sheets API helper code.

**Inputs:** list of findings, target sheet id/config.

**Outputs:** number of rows written, sheet append response, normalized row arrays used for testing.

**Side effects:** Mutates or formats findings for presentation (adds explicit deterministic header rows), uses Google API credentials.

**Tests / checks:** Validate partitioning behavior (deterministic block first), confirm header rows appear, and check API error handling.
