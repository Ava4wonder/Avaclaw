from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
import asyncio
import time
from collections import deque

from jsonschema import validate as jsonschema_validate
from jsonschema.exceptions import ValidationError


@dataclass
class RedactionPolicy:
    keys: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    mask: str = "***"


@dataclass
class ToolPolicy:
    timeout_ms: int | None = None
    max_retries: int = 0
    rate_limit_per_min: int | None = None
    redaction: RedactionPolicy = field(default_factory=RedactionPolicy)


@dataclass
class Tool:
    id: str
    name: str
    description: str
    parameters: dict
    handler: Callable[[Any], Any | Awaitable[Any]]
    policy: ToolPolicy = field(default_factory=ToolPolicy)


@dataclass
class Plugin:
    id: str
    tool: Tool
    origin: str
    source: str | None = None


class RateLimiter:
    def __init__(self, max_per_min: int) -> None:
        self.max_per_min = max_per_min
        self._events: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        window_start = now - 60.0
        while self._events and self._events[0] < window_start:
            self._events.popleft()
        if len(self._events) >= self.max_per_min:
            return False
        self._events.append(now)
        return True


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._rate_limiters: dict[str, RateLimiter] = {}

    def register(self, plugin: Plugin) -> None:
        self._plugins[plugin.id] = plugin
        if plugin.tool.policy.rate_limit_per_min:
            self._rate_limiters[plugin.id] = RateLimiter(plugin.tool.policy.rate_limit_per_min)

    def register_tool(self, tool: Tool, origin: str, source: str | None = None) -> None:
        self.register(Plugin(id=tool.id, tool=tool, origin=origin, source=source))

    def unregister(self, plugin_id: str) -> None:
        self._plugins.pop(plugin_id, None)
        self._rate_limiters.pop(plugin_id, None)

    def remove_by_origin(self, origin: str) -> None:
        to_remove = [pid for pid, plugin in self._plugins.items() if plugin.origin == origin]
        for plugin_id in to_remove:
            self.unregister(plugin_id)

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
                    "description": plugin.tool.description,
                    "parameters": plugin.tool.parameters
                }
            }
            for plugin in plugins
        ]

    def list_tools(self) -> list[Tool]:
        return [plugin.tool for plugin in self.list()]

    def get_policy(self, plugin_id: str) -> ToolPolicy | None:
        plugin = self.get(plugin_id)
        return plugin.tool.policy if plugin else None

    async def call(self, plugin_id: str, args: Any) -> Any:
        plugin = self.get(plugin_id)
        if not plugin:
            raise ValueError(f"Plugin not found: {plugin_id}")

        payload = args if args is not None else {}
        if not isinstance(payload, dict):
            raise ValueError("Tool input must be an object")

        try:
            jsonschema_validate(instance=payload, schema=plugin.tool.parameters)
        except ValidationError as exc:
            raise ValueError(f"Tool input validation failed: {exc.message}")

        policy = plugin.tool.policy
        if policy.rate_limit_per_min:
            limiter = self._rate_limiters.get(plugin_id)
            if not limiter:
                limiter = RateLimiter(policy.rate_limit_per_min)
                self._rate_limiters[plugin_id] = limiter
            if not limiter.allow():
                raise RuntimeError(f"Rate limit exceeded for tool: {plugin_id}")

        async def _run_once() -> Any:
            result = plugin.tool.handler(payload)
            if hasattr(result, "__await__"):
                if policy.timeout_ms:
                    return await asyncio.wait_for(result, policy.timeout_ms / 1000)
                return await result
            if policy.timeout_ms:
                return await asyncio.wait_for(
                    asyncio.to_thread(plugin.tool.handler, payload),
                    policy.timeout_ms / 1000
                )
            return result

        attempt = 0
        while True:
            try:
                return await _run_once()
            except Exception:
                if attempt >= policy.max_retries:
                    raise
                backoff = min(0.2 * (2 ** attempt), 2.0)
                attempt += 1
                await asyncio.sleep(backoff)
