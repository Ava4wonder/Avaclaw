import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from ..schemas import TaskOut
from .agent_manager import AgentManager
from .execution_logger import ExecutionLogger
from .task_queue import TaskQueue
from .llm_executor import LlmExecutor, LlmMessage, LlmResponse
from ..plugins.registry import PluginRegistry
from ..store import PostgresStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


class AgentRuntime:
    def __init__(
        self,
        store: PostgresStore,
        agent_manager: AgentManager,
        execution_logger: ExecutionLogger,
        plugin_registry: PluginRegistry,
        task_queue: TaskQueue,
        llm_executor: LlmExecutor
    ) -> None:
        self.store = store
        self.agent_manager = agent_manager
        self.execution_logger = execution_logger
        self.plugin_registry = plugin_registry
        self.task_queue = task_queue
        self.llm_executor = llm_executor
        self._processing_lock = asyncio.Lock()

    async def enqueue_task(self, agent_id: str, input_text: str) -> TaskOut:
        record = self.store.create_task(agent_id, input_text)
        task_id = record["id"]
        self.task_queue.enqueue(task_id)
        asyncio.create_task(self._process_queue())
        return TaskOut(**record)

    def list_tasks(self) -> list[TaskOut]:
        return [TaskOut(**row) for row in self.store.list_tasks()]

    def get_task(self, task_id: str) -> TaskOut | None:
        row = self.store.get_task(task_id)
        return TaskOut(**row) if row else None

    def queue_depth(self) -> int:
        return self.task_queue.depth()

    def running_tasks(self) -> list[str]:
        return self.task_queue.running_tasks()

    async def _process_queue(self) -> None:
        if self._processing_lock.locked():
            return
        async with self._processing_lock:
            while self.task_queue.depth() > 0:
                task_id = self.task_queue.dequeue()
                if not task_id:
                    break
                await self._run_task(task_id)

    async def _run_task(self, task_id: str) -> None:
        task = self.get_task(task_id)
        if not task:
            return
        agent = self.agent_manager.get_agent(task.agent_id)
        if not agent:
            self._update_task(task_id, {"status": "failed", "error": "Agent not found", "completed_at": _now_iso()})
            return
        if not agent.enabled:
            self._update_task(task_id, {"status": "failed", "error": "Agent is disabled", "completed_at": _now_iso()})
            return

        self._update_task(task_id, {"status": "running", "started_at": _now_iso()})
        self.task_queue.mark_running(task_id)

        trace_id = task.id
        root_span_id = str(uuid4())
        root_start = _now()
        root_start_perf = time.perf_counter()
        root_status = "ok"
        root_error = None

        try:
            result = await self._execute(agent, task, trace_id, root_span_id)
            self._update_task(task_id, {"status": "completed", "result": result, "completed_at": _now_iso()})
        except Exception as exc:
            root_status = "error"
            root_error = str(exc)
            self._update_task(task_id, {"status": "failed", "error": str(exc), "completed_at": _now_iso()})
        finally:
            root_end = _now()
            root_duration = int((time.perf_counter() - root_start_perf) * 1000)
            self.execution_logger.log_span(
                {
                    "id": root_span_id,
                    "task_id": task.id,
                    "trace_id": trace_id,
                    "parent_span_id": None,
                    "name": "task",
                    "span_type": "task",
                    "start_time": root_start,
                    "end_time": root_end,
                    "duration_ms": root_duration,
                    "status": root_status,
                    "error": root_error,
                    "model": agent.model,
                    "tokens_total": None,
                    "tool_args": None,
                    "tool_result": None
                }
            )
            self.task_queue.mark_complete(task_id)

    async def _execute(self, agent, task, trace_id: str, parent_span_id: str) -> str:
        step_index = 0
        tool_list = f"Available tools: {', '.join(agent.tools)}." if agent.tools else ""
        tool_specs = self.plugin_registry.tool_specs(agent.tools)
        system_prompt = (
            f"{agent.system_prompt}\n\nIf you need a tool, use the tool-calling interface. "
            f"If tool calls are unavailable, respond ONLY with a JSON object: "
            f"{{\"tool\":\"<name>\",\"input\":{{...}}}}. {tool_list}"
        )

        messages = [
            LlmMessage(role="system", content=system_prompt),
            LlmMessage(role="user", content=task.input)
        ]

        for _ in range(4):
            llm_start = _now()
            llm_start_perf = time.perf_counter()
            llm_error = None
            try:
                llm = await self.llm_executor.chat(agent.model, messages, tools=tool_specs)
            except Exception as exc:
                llm_error = str(exc)
                llm = None
            llm_end = _now()
            llm_duration = int((time.perf_counter() - llm_start_perf) * 1000)

            if llm is None:
                self.execution_logger.log_span(
                    {
                        "task_id": task.id,
                        "trace_id": trace_id,
                        "parent_span_id": parent_span_id,
                        "name": "llm",
                        "span_type": "llm",
                        "start_time": llm_start,
                        "end_time": llm_end,
                        "duration_ms": llm_duration,
                        "status": "error",
                        "error": llm_error,
                        "model": agent.model,
                        "tokens_total": None,
                        "tool_args": None,
                        "tool_result": None
                    }
                )
                raise RuntimeError(llm_error or "LLM call failed")

            self.execution_logger.log_step(
                {
                    "task_id": task.id,
                    "step_index": step_index,
                    "type": "llm",
                    "input": json.dumps([m.__dict__ for m in messages]),
                    "output": json.dumps({"content": llm.content, "raw": llm.raw}),
                    "tokens_used": llm.tokens_used
                }
            )
            self.execution_logger.log_span(
                {
                    "task_id": task.id,
                    "trace_id": trace_id,
                    "parent_span_id": parent_span_id,
                    "name": "llm",
                    "span_type": "llm",
                    "start_time": llm_start,
                    "end_time": llm_end,
                    "duration_ms": llm_duration,
                    "status": "ok",
                    "error": None,
                    "model": agent.model,
                    "tokens_total": llm.tokens_used,
                    "tool_args": None,
                    "tool_result": None
                }
            )
            step_index += 1

            tool_call = _extract_tool_call(llm)
            if not tool_call:
                return llm.content

            if tool_call["tool"] not in agent.tools:
                return f"Tool not allowed: {tool_call['tool']}"

            tool_start = _now()
            tool_start_perf = time.perf_counter()
            tool_error = None
            tool_result = None
            try:
                tool_result = await self._execute_tool(tool_call["tool"], tool_call.get("input"))
            except Exception as exc:
                tool_error = str(exc)
            tool_end = _now()
            tool_duration = int((time.perf_counter() - tool_start_perf) * 1000)

            self.execution_logger.log_span(
                {
                    "task_id": task.id,
                    "trace_id": trace_id,
                    "parent_span_id": parent_span_id,
                    "name": tool_call["tool"],
                    "span_type": "tool",
                    "start_time": tool_start,
                    "end_time": tool_end,
                    "duration_ms": tool_duration,
                    "status": "error" if tool_error else "ok",
                    "error": tool_error,
                    "model": None,
                    "tokens_total": 0,
                    "tool_args": tool_call.get("input"),
                    "tool_result": tool_result
                }
            )
            if tool_error:
                raise RuntimeError(tool_error)

            self.execution_logger.log_step(
                {
                    "task_id": task.id,
                    "step_index": step_index,
                    "type": "tool",
                    "input": json.dumps(tool_call),
                    "output": json.dumps(tool_result),
                    "tokens_used": 0
                }
            )
            step_index += 1

            messages.append(LlmMessage(role="assistant", content=llm.content))
            messages.append(LlmMessage(role="user", content=f"Tool result: {json.dumps(tool_result)}"))

        return "Max steps reached without final answer."

    async def _execute_tool(self, name: str, payload: Any) -> Any:
        if not self.plugin_registry.has(name):
            raise ValueError(f"Tool not registered: {name}")
        return await self.plugin_registry.call(name, payload)

    def _update_task(self, task_id: str, update: dict[str, Any]) -> None:
        self.store.update_task(task_id, update)


def _extract_tool_call(llm: LlmResponse) -> dict | None:
    if llm.tool_calls:
        call = llm.tool_calls[0] or {}
        if call.get("type") == "function":
            func = call.get("function") or {}
            name = func.get("name")
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args else {}
                except Exception:
                    args = {}
            if isinstance(name, str):
                return {"tool": name, "input": args}
    return _parse_tool_call(llm.content)


def _parse_tool_call(content: str) -> dict | None:
    content = (content or "").strip()
    if not content.startswith("{"):
        return None
    try:
        parsed = json.loads(content)
    except Exception:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("tool"), str) and "input" in parsed:
        return parsed
    return None
