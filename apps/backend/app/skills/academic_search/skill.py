from ..registry import Skill
from .handler import search_academic

academic_search_skill = Skill(
    id="academic_search",
    name="Academic Search",
    description="Search academic papers using Semantic Scholar API",
    parameters={
        "query": "string",
        "limit": "number"
    },
    execute=search_academic
)
