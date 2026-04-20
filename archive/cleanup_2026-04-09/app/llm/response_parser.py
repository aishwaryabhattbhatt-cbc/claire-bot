# LLM response parser stub — will normalise raw Gemini JSON into Finding objects.

from typing import Any, List


def parse_response(raw: str) -> List[Any]:
    """
    Parse a raw LLM response string into a list of findings.

    TODO: implement full parsing — extract JSON, validate fields, coerce types,
          and return a list of app.findings.models.Finding instances.
    """
    return []
