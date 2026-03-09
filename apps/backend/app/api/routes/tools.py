from fastapi import APIRouter, Depends, Request

from ...context import AppContext
from ...schemas import ToolSummary


router = APIRouter(prefix="/api/tools", tags=["tools"])


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@router.get("/", response_model=list[ToolSummary])
def list_tools(ctx: AppContext = Depends(get_ctx)):
    return [
        ToolSummary(id=plugin.id, name=plugin.tool.name, description=plugin.tool.description, origin=plugin.origin)
        for plugin in ctx.plugin_registry.list()
    ]
