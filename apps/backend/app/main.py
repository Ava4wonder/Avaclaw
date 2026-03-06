from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .config import settings
from .store import InMemoryStore
from .context import AppContext
from .services.agent_manager import AgentManager
from .services.execution_logger import ExecutionLogger
from .services.task_queue import TaskQueue
from .services.llm_executor import LlmExecutor
from .services.tool_registry import ToolRegistry
from .services.agent_runtime import AgentRuntime
from .skills.registry import SkillRegistry
from .skills.init import init_skills
from .api.routes import agents, tasks, logs, queue, skills


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = InMemoryStore()
    agent_manager = AgentManager(store)
    execution_logger = ExecutionLogger(store)
    tool_registry = ToolRegistry()
    skill_registry = SkillRegistry()
    init_skills(skill_registry)
    task_queue = TaskQueue()
    llm_executor = LlmExecutor()
    agent_runtime = AgentRuntime(
        store=store,
        agent_manager=agent_manager,
        execution_logger=execution_logger,
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        task_queue=task_queue,
        llm_executor=llm_executor
    )
    app.state.ctx = AppContext(
        store=store,
        agent_manager=agent_manager,
        execution_logger=execution_logger,
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        task_queue=task_queue,
        llm_executor=llm_executor,
        agent_runtime=agent_runtime
    )
    yield
    await app.state.ctx.close()


app = FastAPI(title="AvaClaw Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"] ,
    allow_headers=["*"]
)


@app.get("/health")
def health():
    return {"ok": True}


app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(logs.router)
app.include_router(queue.router)
app.include_router(skills.router)
