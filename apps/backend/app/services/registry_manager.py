from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..plugins.registry import PluginRegistry, Tool
from ..skills.loader import load_manifests
from ..skills.registry import SkillRegistry, Skill


@dataclass
class RegistryLoadReport:
    tools_loaded: int
    skills_loaded: int
    errors: list[str]


class RegistryManager:
    def __init__(self, plugin_registry: PluginRegistry, skill_registry: SkillRegistry, skills_root: Path) -> None:
        self.plugin_registry = plugin_registry
        self.skill_registry = skill_registry
        self.skills_root = skills_root

    def reload(self) -> RegistryLoadReport:
        self.plugin_registry.remove_by_origin("manifest")
        self.skill_registry.remove_by_origin("manifest")
        return self.load()

    def load(self) -> RegistryLoadReport:
        result = load_manifests(self.skills_root)
        for tool in result.tools:
            self.plugin_registry.register_tool(tool, origin="manifest", source="manifest")
        for skill in result.skills:
            self.skill_registry.register(skill)
        return RegistryLoadReport(
            tools_loaded=len(result.tools),
            skills_loaded=len(result.skills),
            errors=result.errors
        )

    def register_tool(self, tool: Tool, origin: str = "api") -> None:
        self.plugin_registry.register_tool(tool, origin=origin, source="api")

    def register_skill(self, skill: Skill, origin: str = "api") -> None:
        skill.origin = origin
        skill.source = "api"
        self.skill_registry.register(skill)
