from .academic_search.skill import academic_search_skill
from .registry import SkillRegistry


def init_skills(registry: SkillRegistry) -> None:
    registry.register(academic_search_skill)
