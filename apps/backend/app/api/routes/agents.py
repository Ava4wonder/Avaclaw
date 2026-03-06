from fastapi import APIRouter, Depends, HTTPException, Request
from ...schemas import AgentCreate, AgentOut, AgentUpdate, EnableRequest
from ...context import AppContext


router = APIRouter(prefix="/api/agents", tags=["agents"])


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@router.get("/", response_model=list[AgentOut])
def list_agents(ctx: AppContext = Depends(get_ctx)):
    return ctx.agent_manager.list_agents()


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, ctx: AppContext = Depends(get_ctx)):
    agent = ctx.agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Not found")
    return agent


@router.post("/", response_model=AgentOut, status_code=201)
def create_agent(payload: AgentCreate, ctx: AppContext = Depends(get_ctx)):
    return ctx.agent_manager.create_agent(payload.model_dump())


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: str, payload: AgentUpdate, ctx: AppContext = Depends(get_ctx)):
    try:
        return ctx.agent_manager.update_agent(agent_id, payload.model_dump(exclude_none=True))
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/{agent_id}/enable", response_model=AgentOut)
def enable_agent(agent_id: str, payload: EnableRequest, ctx: AppContext = Depends(get_ctx)):
    try:
        return ctx.agent_manager.set_enabled(agent_id, payload.enabled)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: str, ctx: AppContext = Depends(get_ctx)):
    ctx.agent_manager.delete_agent(agent_id)
    return None
