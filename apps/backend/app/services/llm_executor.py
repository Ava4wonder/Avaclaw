from dataclasses import dataclass
from typing import Any
import httpx
from ..config import settings


@dataclass
class LlmMessage:
    role: str
    content: str


@dataclass
class LlmResponse:
    content: str
    raw: Any
    tokens_used: int
    tool_calls: list[dict] | None = None


class LlmExecutor:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=60)

    async def chat(
        self,
        model: str,
        messages: list[LlmMessage],
        tools: list[dict] | None = None,
        tool_choice: str | None = None
    ) -> LlmResponse:
        payload = {
            "model": model or settings.ollama_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        url = f"{settings.ollama_base_url}/api/chat"
        res = await self._client.post(url, json=payload)
        if res.status_code >= 400:
            raise RuntimeError(f"LLM error {res.status_code}: {res.text}")
        data = res.json()
        message = data.get("message") or {}
        content = message.get("content", "")
        tool_calls = message.get("tool_calls")
        tokens_used = int(data.get("prompt_eval_count", 0) or 0) + int(data.get("eval_count", 0) or 0)
        return LlmResponse(content=content, raw=data, tokens_used=tokens_used, tool_calls=tool_calls)

    async def close(self) -> None:
        await self._client.aclose()
