from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Skill:
    id: str
    name: str
    description: str
    prompt: str | None
    tools: list[str]
    origin: str
    source: str | None = None


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.id] = skill

    def unregister(self, skill_id: str) -> None:
        self._skills.pop(skill_id, None)

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def list(self) -> list[Skill]:
        return list(self._skills.values())

    def remove_by_origin(self, origin: str) -> None:
        to_remove = [skill_id for skill_id, skill in self._skills.items() if skill.origin == origin]
        for skill_id in to_remove:
            self._skills.pop(skill_id, None)
