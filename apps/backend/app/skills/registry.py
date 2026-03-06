from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Skill:
    id: str
    name: str
    description: str
    parameters: Any
    execute: Callable[[Any], Any]


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.id] = skill

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def list(self) -> list[Skill]:
        return list(self._skills.values())

    def has(self, skill_id: str) -> bool:
        return skill_id in self._skills

    async def execute(self, skill_id: str, args: Any) -> Any:
        skill = self.get(skill_id)
        if not skill:
            raise ValueError(f"Skill not found: {skill_id}")
        result = skill.execute(args)
        if hasattr(result, "__await__"):
            return await result
        return result
