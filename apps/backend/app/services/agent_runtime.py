import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from ..schemas import TaskOut
from .agent_manager import AgentManager
from .execution_logger import ExecutionLogger
from .task_queue import TaskQueue
from .llm_executor import LlmExecutor, LlmMessage
from .tool_registry import ToolRegistry
from ..skills.registry import SkillRegistry
from ..store import InMemoryStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentRuntime:
    def __init__(
        self,
        store: InMemoryStore,
        agent_manager: AgentManager,
        execution_logger: ExecutionLogger,
        tool_registry: ToolRegistry,
        skill_registry: SkillRegistry,
        task_queue: TaskQueue,
        llm_executor: LlmExecutor
    ) -> None:
        self.store = store
        self.agent_manager = agent_manager
        self.execution_logger = execution_logger
        self.tool_registry = tool_registry
        self.skill_registry = skill_registry
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

        try:
            result = await self._execute(agent, task)
            self._update_task(task_id, {"status": "completed", "result": result, "completed_at": _now_iso()})
        except Exception as exc:
            self._update_task(task_id, {"status": "failed", "error": str(exc), "completed_at": _now_iso()})
        finally:
            self.task_queue.mark_complete(task_id)

    async def _execute(self, agent, task) -> str:
        step_index = 0
        tool_list = f"Available tools: {', '.join(agent.tools)}." if agent.tools else ""
        system_prompt = (
            f"{agent.system_prompt}\n\nIf you need a tool, respond ONLY with a JSON object: "
            f"{{\"tool\":\"<name>\",\"input\":{{...}}}}. {tool_list}"
        )

        messages = [
            LlmMessage(role="system", content=system_prompt),
            LlmMessage(role="user", content=task.input)
        ]

        for _ in range(4):
            llm = await self.llm_executor.chat(agent.model, messages)
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
            step_index += 1

            tool_call = _parse_tool_call(llm.content)
            if not tool_call:
                return llm.content

            if tool_call["tool"] not in agent.tools:
                return f"Tool not allowed: {tool_call['tool']}"

            tool_result = await self._execute_tool(tool_call["tool"], tool_call.get("input"))

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
        if self.tool_registry.has(name):
            return await self.tool_registry.call(name, payload)
        if self.skill_registry.has(name):
            return await self.skill_registry.execute(name, payload)
        raise ValueError(f"Tool not registered: {name}")

    def _update_task(self, task_id: str, update: dict[str, Any]) -> None:
        self.store.update_task(task_id, update)


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
