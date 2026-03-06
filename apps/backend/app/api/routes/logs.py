from fastapi import APIRouter, Depends, Request
from ...context import AppContext


router = APIRouter(prefix="/api/logs", tags=["logs"])


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@router.get("/tasks/{task_id}")
def get_task_logs(task_id: str, ctx: AppContext = Depends(get_ctx)):
    return ctx.execution_logger.list_steps(task_id)
