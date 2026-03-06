from dataclasses import dataclass
from .store import InMemoryStore
from .services.agent_manager import AgentManager
from .services.execution_logger import ExecutionLogger
from .services.task_queue import TaskQueue
from .services.llm_executor import LlmExecutor
from .services.tool_registry import ToolRegistry
from .services.agent_runtime import AgentRuntime
from .skills.registry import SkillRegistry


@dataclass
class AppContext:
    store: InMemoryStore
    agent_manager: AgentManager
    execution_logger: ExecutionLogger
    tool_registry: ToolRegistry
    skill_registry: SkillRegistry
    task_queue: TaskQueue
    llm_executor: LlmExecutor
    agent_runtime: AgentRuntime

    async def close(self) -> None:
        await self.llm_executor.close()
