"""Input validation at the untrusted telemetry boundary."""

from typing import Any


def validate_telemetry(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("schema_version", "generated_at", "incident", "nodes"):
        if key not in payload:
            errors.append(f"Missing top-level field: {key}")
    if not isinstance(payload.get("nodes"), list) or not payload.get("nodes"):
        errors.append("nodes must be a non-empty list")
        return errors
    for index, node in enumerate(payload["nodes"]):
        for key in ("node_id", "node_type", "telemetry"):
            if key not in node:
                errors.append(f"nodes[{index}] missing {key}")
    return errors
