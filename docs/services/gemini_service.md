# Gemini Service

**Purpose:** Wraps calls to Google Gemini, sends prompts, parses JSON responses, and extracts token usage and estimated cost.

**Key functions:**
- Send prompt payloads to Gemini and receive structured JSON output.
- Parse model output into a list of `finding` objects used by the app.
- Extract `usage` metadata (tokens) and compute an estimated cost for the run.

**Inputs:** prompt text, model name, temperature, optional parameters.

**Outputs:** list of findings (dicts), usage metadata (tokens/cost), parsing errors on failure.

**Side effects:** Stores latest usage on the service instance and logs usage/cost for telemetry.

**Tests / checks:** Validate JSON parsing for different response shapes, confirm token counts extraction, and assert cost calculation.
