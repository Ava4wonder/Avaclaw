from __future__ import annotations

from datetime import datetime, timezone

from .registry import PluginRegistry, Plugin
from ..skills.academic_search.skill import academic_search_plugin


def init_plugins(registry: PluginRegistry) -> None:
    registry.register(
        Plugin(
            id="echo",
            name="Echo",
            description="Echo back the provided payload value.",
            parameters={
                "type": "object",
                "properties": {"value": {}},
                "required": ["value"],
                "additionalProperties": True
            },
            handler=lambda payload: payload.get("value"),
            origin="builtin"
        )
    )

    registry.register(
        Plugin(
            id="time",
            name="Current Time",
            description="Get the current UTC time.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False
            },
            handler=lambda _: {"now": datetime.now(timezone.utc).isoformat()},
            origin="builtin"
        )
    )

    registry.register(academic_search_plugin)
