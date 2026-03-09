from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  system_prompt TEXT NOT NULL,
  tools JSONB NOT NULL,
  skills JSONB NOT NULL,
  model TEXT NOT NULL,
  enabled BOOLEAN NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id),
  input TEXT NOT NULL,
  status TEXT NOT NULL,
  result TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  run_id TEXT,
  session_id TEXT,
  parent_task_id TEXT,
  retry_count INTEGER,
  retry_state TEXT,
  replay_key TEXT,
  replay_metadata JSONB
);

CREATE TABLE IF NOT EXISTS execution_steps (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(id),
  step_index INTEGER NOT NULL,
  type TEXT NOT NULL,
  input TEXT NOT NULL,
  output TEXT NOT NULL,
  tokens_used INTEGER NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_spans (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(id),
  trace_id TEXT NOT NULL,
  parent_span_id TEXT,
  name TEXT NOT NULL,
  span_type TEXT NOT NULL,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ NOT NULL,
  duration_ms INTEGER NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  model TEXT,
  tokens_total INTEGER,
  tool_args JSONB,
  tool_result JSONB
);

ALTER TABLE agents ADD COLUMN IF NOT EXISTS skills JSONB;

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS run_id TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS session_id TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS parent_task_id TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS retry_count INTEGER;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS retry_state TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS replay_key TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS replay_metadata JSONB;
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        self._lock = Lock()
        self._conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
        with self._conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def list_agents(self) -> list[dict[str, Any]]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute("SELECT * FROM agents ORDER BY created_at DESC")
            return [dict(row) for row in cur.fetchall()]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute("SELECT * FROM agents WHERE id = %s", (agent_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(uuid4())
        created_at = _now()
        record = {
            "id": agent_id,
            "name": payload["name"],
            "system_prompt": payload["system_prompt"],
            "tools": list(payload.get("tools", [])),
            "skills": list(payload.get("skills", [])),
            "model": payload["model"],
            "enabled": bool(payload.get("enabled", True)),
            "created_at": created_at,
            "updated_at": created_at
        }
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agents (id, name, system_prompt, tools, skills, model, enabled, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    record["id"],
                    record["name"],
                    record["system_prompt"],
                    Jsonb(record["tools"]),
                    Jsonb(record["skills"]),
                    record["model"],
                    record["enabled"],
                    record["created_at"],
                    record["updated_at"]
                )
            )
            return dict(cur.fetchone())

    def update_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_agent(agent_id)
        if not current:
            raise ValueError("Agent not found")
        updated = {
            **current,
            "name": payload.get("name", current["name"]),
            "system_prompt": payload.get("system_prompt", current["system_prompt"]),
            "tools": payload.get("tools", current["tools"]),
            "skills": payload.get("skills", current.get("skills") or []),
            "model": payload.get("model", current["model"]),
            "enabled": payload.get("enabled", current["enabled"]),
            "updated_at": _now()
        }
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agents
                SET name = %s, system_prompt = %s, tools = %s, skills = %s, model = %s, enabled = %s, updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    updated["name"],
                    updated["system_prompt"],
                    Jsonb(updated["tools"]),
                    Jsonb(updated["skills"]),
                    updated["model"],
                    updated["enabled"],
                    updated["updated_at"],
                    agent_id
                )
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def delete_agent(self, agent_id: str) -> None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute("DELETE FROM agents WHERE id = %s", (agent_id,))

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute("SELECT * FROM tasks ORDER BY created_at DESC")
            rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["created_at"] = _iso(row["created_at"])
            row["started_at"] = _iso(row["started_at"])
            row["completed_at"] = _iso(row["completed_at"])
        return rows

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
        if not row:
            return None
        record = dict(row)
        record["created_at"] = _iso(record["created_at"])
        record["started_at"] = _iso(record["started_at"])
        record["completed_at"] = _iso(record["completed_at"])
        return record

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = str(uuid4())
        run_id = payload.get("run_id") or task_id
        session_id = payload.get("session_id") or run_id
        created_at = _now()
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tasks (
                    id, agent_id, input, status, result, error, created_at, started_at, completed_at,
                    run_id, session_id, parent_task_id, retry_count, retry_state, replay_key, replay_metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    task_id,
                    payload["agent_id"],
                    payload["input"],
                    "queued",
                    None,
                    None,
                    created_at,
                    None,
                    None,
                    run_id,
                    session_id,
                    payload.get("parent_task_id"),
                    payload.get("retry_count"),
                    payload.get("retry_state"),
                    payload.get("replay_key"),
                    Jsonb(payload.get("replay_metadata")) if payload.get("replay_metadata") is not None else None
                )
            )
            row = cur.fetchone()
        record = dict(row)
        record["created_at"] = _iso(record["created_at"])
        record["started_at"] = _iso(record["started_at"])
        record["completed_at"] = _iso(record["completed_at"])
        return record

    def update_task(self, task_id: str, update: dict[str, Any]) -> dict[str, Any]:
        current = self.get_task(task_id)
        if not current:
            raise ValueError("Task not found")
        merged = {**current, **update}
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tasks
                SET status = %s, result = %s, error = %s, started_at = %s, completed_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    merged["status"],
                    merged["result"],
                    merged["error"],
                    merged["started_at"],
                    merged["completed_at"],
                    task_id
                )
            )
            row = cur.fetchone()
        record = dict(row)
        record["created_at"] = _iso(record["created_at"])
        record["started_at"] = _iso(record["started_at"])
        record["completed_at"] = _iso(record["completed_at"])
        return record

    def add_step(self, payload: dict[str, Any]) -> dict[str, Any]:
        step_id = str(uuid4())
        timestamp = payload.get("timestamp") or _now()
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_steps (id, task_id, step_index, type, input, output, tokens_used, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    step_id,
                    payload["task_id"],
                    payload["step_index"],
                    payload["type"],
                    payload["input"],
                    payload["output"],
                    payload["tokens_used"],
                    timestamp
                )
            )
            row = cur.fetchone()
        record = dict(row)
        record["timestamp"] = _iso(record["timestamp"])
        return record

    def list_steps(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM execution_steps WHERE task_id = %s ORDER BY step_index",
                (task_id,)
            )
            rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["timestamp"] = _iso(row["timestamp"])
        return rows

    def add_span(self, payload: dict[str, Any]) -> dict[str, Any]:
        span_id = payload.get("id") or str(uuid4())
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_spans (
                    id, task_id, trace_id, parent_span_id, name, span_type,
                    start_time, end_time, duration_ms, status, error, model, tokens_total, tool_args, tool_result
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    span_id,
                    payload["task_id"],
                    payload["trace_id"],
                    payload.get("parent_span_id"),
                    payload["name"],
                    payload["span_type"],
                    payload["start_time"],
                    payload["end_time"],
                    payload["duration_ms"],
                    payload["status"],
                    payload.get("error"),
                    payload.get("model"),
                    payload.get("tokens_total"),
                    Jsonb(payload.get("tool_args")) if payload.get("tool_args") is not None else None,
                    Jsonb(payload.get("tool_result")) if payload.get("tool_result") is not None else None
                )
            )
            row = cur.fetchone()
        record = dict(row)
        record["start_time"] = _iso(record["start_time"])
        record["end_time"] = _iso(record["end_time"])
        return record

    def list_spans(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM execution_spans WHERE task_id = %s ORDER BY start_time",
                (task_id,)
            )
            rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["start_time"] = _iso(row["start_time"])
            row["end_time"] = _iso(row["end_time"])
        return rows
