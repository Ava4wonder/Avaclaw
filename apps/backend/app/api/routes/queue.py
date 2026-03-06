from fastapi import APIRouter, Depends, Request
from ...context import AppContext


router = APIRouter(prefix="/api/queue", tags=["queue"])


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@router.get("/")
def get_queue(ctx: AppContext = Depends(get_ctx)):
    return {
        "depth": ctx.agent_runtime.queue_depth(),
        "running": ctx.agent_runtime.running_tasks()
    }
