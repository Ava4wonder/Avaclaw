from dataclasses import dataclass
from .store import PostgresStore
from .services.agent_manager import AgentManager
from .services.execution_logger import ExecutionLogger
from .services.task_queue import TaskQueue
from .services.llm_executor import LlmExecutor
from .services.agent_runtime import AgentRuntime
from .plugins.registry import PluginRegistry


@dataclass
class AppContext:
    store: PostgresStore
    agent_manager: AgentManager
    execution_logger: ExecutionLogger
    plugin_registry: PluginRegistry
    task_queue: TaskQueue
    llm_executor: LlmExecutor
    agent_runtime: AgentRuntime

    async def close(self) -> None:
        self.store.close()
        self.task_queue.close()
        await self.llm_executor.close()
