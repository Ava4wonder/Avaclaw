import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.skills.loader import parse_manifest, manifest_to_tool


def test_manifest_parsing_with_tool():
    raw = {
        "id": "demo_tool",
        "name": "Demo Tool",
        "description": "Demo tool description",
        "tool": {
            "handler": "app.tools.academic_search:academic_search",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False
            }
        }
    }
    manifest = parse_manifest(raw, "unit")
    tool = manifest_to_tool(manifest)
    assert tool is not None
    assert tool.id == "demo_tool"
    assert tool.name == "Demo Tool"


def test_manifest_validation_rejects_missing_fields():
    raw = {"name": "No Id", "description": "Missing id"}
    with pytest.raises(ValueError):
        parse_manifest(raw, "unit")
