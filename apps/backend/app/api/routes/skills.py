from fastapi import APIRouter, Depends, Request
from ...context import AppContext
from ...schemas import SkillSummary


router = APIRouter(prefix="/api/skills", tags=["skills"])


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@router.get("/", response_model=list[SkillSummary])
def list_skills(ctx: AppContext = Depends(get_ctx)):
    return [
        SkillSummary(id=s.id, name=s.name, description=s.description, origin=s.origin)
        for s in ctx.skill_registry.list()
    ]
