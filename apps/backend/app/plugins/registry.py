from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from jsonschema import validate as jsonschema_validate
from jsonschema.exceptions import ValidationError


@dataclass
class Plugin:
    id: str
    name: str
    description: str
    parameters: dict
    handler: Callable[[Any], Any | Awaitable[Any]]
    origin: str


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        self._plugins[plugin.id] = plugin

    def unregister(self, plugin_id: str) -> None:
        self._plugins.pop(plugin_id, None)

    def get(self, plugin_id: str) -> Plugin | None:
        return self._plugins.get(plugin_id)

    def list(self) -> list[Plugin]:
        return list(self._plugins.values())

    def has(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins

    def tool_specs(self, allowed: list[str] | None = None) -> list[dict]:
        plugins = self.list()
        if allowed is not None:
            allowed_set = set(allowed)
            plugins = [p for p in plugins if p.id in allowed_set]
        return [
            {
                "type": "function",
                "function": {
                    "name": plugin.id,
                    "description": plugin.description,
                    "parameters": plugin.parameters
                }
            }
            for plugin in plugins
        ]

    async def call(self, plugin_id: str, args: Any) -> Any:
        plugin = self.get(plugin_id)
        if not plugin:
            raise ValueError(f"Plugin not found: {plugin_id}")

        payload = args if args is not None else {}
        if not isinstance(payload, dict):
            raise ValueError("Tool input must be an object")

        try:
            jsonschema_validate(instance=payload, schema=plugin.parameters)
        except ValidationError as exc:
            raise ValueError(f"Tool input validation failed: {exc.message}")

        result = plugin.handler(payload)
        if hasattr(result, "__await__"):
            return await result
        return result
