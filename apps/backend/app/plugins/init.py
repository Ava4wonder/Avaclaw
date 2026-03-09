from __future__ import annotations

from datetime import datetime, timezone

from .registry import PluginRegistry, Tool


def init_plugins(registry: PluginRegistry) -> None:
    registry.register_tool(
        Tool(
            id="echo",
            name="Echo",
            description="Echo back the provided payload value.",
            parameters={
                "type": "object",
                "properties": {"value": {}},
                "required": ["value"],
                "additionalProperties": True
            },
            handler=lambda payload: payload.get("value")
        ),
        origin="builtin",
        source="init"
    )

    registry.register_tool(
        Tool(
            id="time",
            name="Current Time",
            description="Get the current UTC time.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False
            },
            handler=lambda _: {"now": datetime.now(timezone.utc).isoformat()}
        ),
        origin="builtin",
        source="init"
    )
