from fastapi import APIRouter, Depends, HTTPException, Request
from ...schemas import TaskCreate, TaskOut, ExecutionStepOut
from ...context import AppContext


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@router.get("/", response_model=list[TaskOut])
def list_tasks(ctx: AppContext = Depends(get_ctx)):
    return ctx.agent_runtime.list_tasks()


@router.post("/", response_model=TaskOut, status_code=201)
async def create_task(payload: TaskCreate, ctx: AppContext = Depends(get_ctx)):
    return await ctx.agent_runtime.enqueue_task(payload.agent_id, payload.input)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, ctx: AppContext = Depends(get_ctx)):
    task = ctx.agent_runtime.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Not found")
    return task


@router.get("/{task_id}/steps", response_model=list[ExecutionStepOut])
def get_steps(task_id: str, ctx: AppContext = Depends(get_ctx)):
    return ctx.execution_logger.list_steps(task_id)
