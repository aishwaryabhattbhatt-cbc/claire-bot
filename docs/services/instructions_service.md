# Instructions Service

**Purpose:** Read, write, and manage the saved review instructions used when building LLM prompts.

**Key functions:**
- `get_instructions()`: returns current saved instructions (comparison and french variants).
- `save_instructions(...)`: persist new instructions to `data/processed/review_instructions.json`.
- `update_instructions(...)` and `reset_instructions(...)` for partial updates and resets.

**Inputs:** strings for `comparison_instructions` and `french_instructions`.

**Outputs:** the payload dict saved or returned to callers.

**Side effects:** Reads/writes the JSON file under processed data; creates directories if missing.

**Tests / checks:** Ensure safe behavior when file is missing, malformed JSON, or partial updates are applied.
