from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .config import settings
from .store import PostgresStore
from .context import AppContext
from .services.agent_manager import AgentManager
from .services.execution_logger import ExecutionLogger
from .services.task_queue import TaskQueue
from .services.llm_executor import LlmExecutor
from .services.agent_runtime import AgentRuntime
from .plugins.registry import PluginRegistry
from .plugins.init import init_plugins
from .skills.registry import SkillRegistry
from .services.registry_manager import RegistryManager
from .api.routes import agents, tasks, logs, queue, skills, tools, plugins
from pathlib import Path


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = PostgresStore(settings.postgres_dsn)
    agent_manager = AgentManager(store)
    execution_logger = ExecutionLogger(store)
    plugin_registry = PluginRegistry()
    init_plugins(plugin_registry)
    skill_registry = SkillRegistry()
    registry_manager = RegistryManager(
        plugin_registry=plugin_registry,
        skill_registry=skill_registry,
        skills_root=Path(__file__).resolve().parent / "skills"
    )
    registry_manager.load()
    task_queue = TaskQueue(settings.redis_url)
    llm_executor = LlmExecutor()
    agent_runtime = AgentRuntime(
        store=store,
        agent_manager=agent_manager,
        execution_logger=execution_logger,
        plugin_registry=plugin_registry,
        skill_registry=skill_registry,
        task_queue=task_queue,
        llm_executor=llm_executor
    )
    app.state.ctx = AppContext(
        store=store,
        agent_manager=agent_manager,
        execution_logger=execution_logger,
        plugin_registry=plugin_registry,
        skill_registry=skill_registry,
        registry_manager=registry_manager,
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
app.include_router(tools.router)
app.include_router(plugins.router)
