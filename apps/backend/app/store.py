from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class InMemoryStore:
    _agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    _tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    _steps: list[dict[str, Any]] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def list_agents(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._agents.values())
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._agents.get(agent_id)

    def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(uuid4())
        created_at = _now_iso()
        record = {
            "id": agent_id,
            "name": payload["name"],
            "system_prompt": payload["system_prompt"],
            "tools": list(payload.get("tools", [])),
            "model": payload["model"],
            "enabled": bool(payload.get("enabled", True)),
            "created_at": created_at,
            "updated_at": created_at
        }
        with self._lock:
            self._agents[agent_id] = record
        return record

    def update_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self._agents.get(agent_id)
            if not current:
                raise ValueError("Agent not found")
            updated = {
                **current,
                "name": payload.get("name", current["name"]),
                "system_prompt": payload.get("system_prompt", current["system_prompt"]),
                "tools": payload.get("tools", current["tools"]),
                "model": payload.get("model", current["model"]),
                "enabled": payload.get("enabled", current["enabled"]),
                "updated_at": _now_iso()
            }
            self._agents[agent_id] = updated
        return updated

    def delete_agent(self, agent_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_id, None)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._tasks.values())
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._tasks.get(task_id)

    def create_task(self, agent_id: str, input_text: str) -> dict[str, Any]:
        task_id = str(uuid4())
        created_at = _now_iso()
        record = {
            "id": task_id,
            "agent_id": agent_id,
            "input": input_text,
            "status": "queued",
            "result": None,
            "error": None,
            "created_at": created_at,
            "started_at": None,
            "completed_at": None
        }
        with self._lock:
            self._tasks[task_id] = record
        return record

    def update_task(self, task_id: str, update: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self._tasks.get(task_id)
            if not current:
                raise ValueError("Task not found")
            updated = {**current, **update}
            self._tasks[task_id] = updated
        return updated

    def add_step(self, payload: dict[str, Any]) -> dict[str, Any]:
        step_id = str(uuid4())
        record = {
            "id": step_id,
            "task_id": payload["task_id"],
            "step_index": payload["step_index"],
            "type": payload["type"],
            "input": payload["input"],
            "output": payload["output"],
            "tokens_used": payload["tokens_used"],
            "timestamp": payload.get("timestamp") or _now_iso()
        }
        with self._lock:
            self._steps.append(record)
        return record

    def list_steps(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = [row for row in self._steps if row["task_id"] == task_id]
        return sorted(rows, key=lambda row: row["step_index"])
