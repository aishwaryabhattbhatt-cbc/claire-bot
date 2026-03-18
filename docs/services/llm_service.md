# LLM Service

**Purpose:** Abstracts LLM interactions for non-provider-specific logic (prompt assembly, response validation, fallback handling).

**Key functions:**
- Build final prompt text from input parts (instructions, additional context, reference snippets).
- Validate LLM outputs and provide unified error/empty response handling.

**Inputs:** prompt pieces, model selection (though Gemini is enforced elsewhere), temperature and options.

**Outputs:** validated raw LLM response, optionally parsed findings handed to higher-level services.

**Side effects:** None by itself; delegates network calls to provider services (Gemini/OpenAI wrappers).

**Tests / checks:** Verify prompt builder output for given instruction sets; test fallback behavior on empty model responses.
