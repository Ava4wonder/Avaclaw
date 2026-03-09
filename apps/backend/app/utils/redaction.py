from __future__ import annotations

from typing import Any

from ..plugins.registry import RedactionPolicy


def _redact_keys(value: Any, keys: set[str], mask: str) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key in keys:
                redacted[key] = mask
            else:
                redacted[key] = _redact_keys(item, keys, mask)
        return redacted
    if isinstance(value, list):
        return [_redact_keys(item, keys, mask) for item in value]
    return value


def _apply_path(value: Any, parts: list[str], mask: str) -> Any:
    if not parts:
        return mask
    head = parts[0]
    tail = parts[1:]
    if isinstance(value, dict):
        if head == "*":
            return {k: _apply_path(v, tail, mask) for k, v in value.items()}
        if head in value:
            value = dict(value)
            value[head] = _apply_path(value[head], tail, mask)
            return value
        return value
    if isinstance(value, list):
        if head == "*":
            return [_apply_path(item, tail, mask) for item in value]
        try:
            idx = int(head)
        except Exception:
            return value
        if 0 <= idx < len(value):
            value = list(value)
            value[idx] = _apply_path(value[idx], tail, mask)
            return value
        return value
    return value


def _redact_paths(value: Any, paths: list[str], mask: str) -> Any:
    result = value
    for path in paths:
        parts = [part for part in path.split(".") if part]
        if not parts:
            continue
        result = _apply_path(result, parts, mask)
    return result


def redact_payload(value: Any, policy: RedactionPolicy | None) -> Any:
    if policy is None:
        return value
    mask = policy.mask
    redacted = _redact_keys(value, set(policy.keys), mask) if policy.keys else value
    if policy.paths:
        redacted = _redact_paths(redacted, policy.paths, mask)
    return redacted
