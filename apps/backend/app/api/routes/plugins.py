from fastapi import APIRouter, Depends, HTTPException, Request

from ...context import AppContext
from ...schemas import PluginRegisterRequest, RegistryReloadOut, ToolSummary
from ...skills.loader import parse_manifest, manifest_to_tool, manifest_to_skill


router = APIRouter(prefix="/api/plugins", tags=["plugins"])


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@router.get("/", response_model=list[ToolSummary])
def list_plugins(ctx: AppContext = Depends(get_ctx)):
    return [
        ToolSummary(id=plugin.id, name=plugin.tool.name, description=plugin.tool.description, origin=plugin.origin)
        for plugin in ctx.plugin_registry.list()
    ]


@router.post("/reload", response_model=RegistryReloadOut)
def reload_plugins(ctx: AppContext = Depends(get_ctx)):
    report = ctx.registry_manager.reload()
    return RegistryReloadOut(
        tools_loaded=report.tools_loaded,
        skills_loaded=report.skills_loaded,
        errors=report.errors
    )


@router.post("/register", response_model=RegistryReloadOut)
def register_plugin(payload: PluginRegisterRequest, ctx: AppContext = Depends(get_ctx)):
    try:
        manifest = parse_manifest(payload.manifest, "api")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    tool = manifest_to_tool(manifest)
    skill = manifest_to_skill(manifest, tool.id if tool else None)
    tools_loaded = 0
    skills_loaded = 0
    if tool:
        ctx.plugin_registry.register_tool(tool, origin="api", source="api")
        tools_loaded += 1
    if skill:
        skill.origin = "api"
        skill.source = "api"
        ctx.skill_registry.register(skill)
        skills_loaded += 1
    return RegistryReloadOut(tools_loaded=tools_loaded, skills_loaded=skills_loaded, errors=[])


@router.delete("/{plugin_id}", response_model=None, status_code=204)
def unregister_plugin(plugin_id: str, ctx: AppContext = Depends(get_ctx)):
    ctx.plugin_registry.unregister(plugin_id)
    return None
