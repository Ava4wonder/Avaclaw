from typing import Any, Callable, Awaitable


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[[Any], Any | Awaitable[Any]]] = {}
        self.register("echo", lambda payload: payload)
        self.register("time", lambda _: {"now": __import__("datetime").datetime.utcnow().isoformat()})

    def register(self, name: str, handler: Callable[[Any], Any | Awaitable[Any]]) -> None:
        self._tools[name] = handler

    def has(self, name: str) -> bool:
        return name in self._tools

    def list(self) -> list[str]:
        return list(self._tools.keys())

    async def call(self, name: str, payload: Any) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool not found: {name}")
        handler = self._tools[name]
        result = handler(payload)
        if hasattr(result, "__await__"):
            return await result
        return result
