from ...plugins.registry import Plugin
from .handler import search_academic

academic_search_plugin = Plugin(
    id="academic_search",
    name="Academic Search",
    description="Search academic papers using Semantic Scholar API",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20}
        },
        "required": ["query"],
        "additionalProperties": False
    },
    handler=search_academic,
    origin="skill"
)
