# OpenAI Service

**Purpose:** Wrapper for OpenAI API calls (kept for compatibility or optional provider testing).

**Key functions:**
- Send prompts to OpenAI endpoints and parse results into the app's `finding` schema.
- Extract usage metadata when available and convert to the same usage format as other providers.

**Inputs:** prompt text, model name, and options.

**Outputs:** parsed findings and usage metadata.

**Side effects:** Network calls to OpenAI; may store or log usage similarly to Gemini service.

**Tests / checks:** Ensure compatibility with expected response shapes and that usage extraction mirrors Gemini behavior when fields exist.
