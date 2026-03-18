import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.core.config import get_settings

_usage_lock = threading.Lock()


def _usage_file_path() -> Path:
    settings = get_settings()
    path = Path(settings.processed_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / "gemini_usage_totals.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_totals() -> Dict[str, Any]:
    return {
        "call_count": 0,
        "prompt_tokens": 0,
        "response_tokens": 0,
        "cached_tokens": 0,
        "thoughts_tokens": 0,
        "total_tokens": 0,
        "input_cost": 0.0,
        "output_cost": 0.0,
        "total_cost": 0.0,
        "first_recorded_at": None,
        "last_recorded_at": None,
    }


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_usage(usage: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        "provider": usage.get("provider") or "gemini",
        "model": usage.get("model"),
        "pricing_source": usage.get("pricing_source") or "configured_model_rates",
        "prompt_tokens": _to_int(usage.get("prompt_tokens")),
        "response_tokens": _to_int(usage.get("response_tokens")),
        "cached_tokens": _to_int(usage.get("cached_tokens")),
        "thoughts_tokens": _to_int(usage.get("thoughts_tokens")),
        "total_tokens": _to_int(usage.get("total_tokens")),
        "input_cost": _to_float(usage.get("input_cost")),
        "output_cost": _to_float(usage.get("output_cost")),
        "total_cost": _to_float(usage.get("total_cost")),
        "recorded_at": usage.get("recorded_at") or _utc_now(),
    }
    if normalized["total_tokens"] <= 0:
        normalized["total_tokens"] = normalized["prompt_tokens"] + normalized["response_tokens"]
    return normalized


def _load_totals(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return _empty_totals()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        totals = _empty_totals()
        totals.update(data if isinstance(data, dict) else {})
        return totals
    except Exception:
        return _empty_totals()


def record_gemini_usage(latest_usage: Dict[str, Any]) -> Dict[str, Any]:
    latest = _normalize_usage(latest_usage)
    path = _usage_file_path()

    with _usage_lock:
        cumulative = _load_totals(path)
        if not cumulative["first_recorded_at"]:
            cumulative["first_recorded_at"] = latest["recorded_at"]

        cumulative["call_count"] = _to_int(cumulative.get("call_count")) + 1
        cumulative["prompt_tokens"] = _to_int(cumulative.get("prompt_tokens")) + latest["prompt_tokens"]
        cumulative["response_tokens"] = _to_int(cumulative.get("response_tokens")) + latest["response_tokens"]
        cumulative["cached_tokens"] = _to_int(cumulative.get("cached_tokens")) + latest["cached_tokens"]
        cumulative["thoughts_tokens"] = _to_int(cumulative.get("thoughts_tokens")) + latest["thoughts_tokens"]
        cumulative["total_tokens"] = _to_int(cumulative.get("total_tokens")) + latest["total_tokens"]
        cumulative["input_cost"] = _to_float(cumulative.get("input_cost")) + latest["input_cost"]
        cumulative["output_cost"] = _to_float(cumulative.get("output_cost")) + latest["output_cost"]
        cumulative["total_cost"] = _to_float(cumulative.get("total_cost")) + latest["total_cost"]
        cumulative["last_recorded_at"] = latest["recorded_at"]

        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(cumulative, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    return {
        "provider": latest["provider"],
        "model": latest.get("model"),
        "pricing_source": latest["pricing_source"],
        "latest": latest,
        "cumulative": cumulative,
    }
