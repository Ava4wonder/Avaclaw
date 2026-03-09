from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import importlib
import json

import yaml
from jsonschema import validate as jsonschema_validate
from jsonschema.exceptions import ValidationError

from ..plugins.registry import Tool, ToolPolicy, RedactionPolicy
from .registry import Skill


@dataclass
class ToolManifest:
    id: str
    name: str
    description: str
    handler: str
    parameters: dict
    policy: ToolPolicy


@dataclass
class SkillManifest:
    id: str
    name: str
    description: str
    prompt: str | None
    tools: list[str] | None
    tool: ToolManifest | None
    origin: str
    source: str


@dataclass
class ManifestLoadResult:
    tools: list[Tool]
    skills: list[Skill]
    errors: list[str]


MANIFEST_FILENAMES = ("skill.yaml", "skill.yml", "skill.json", "SKILL.md")
SCHEMA_PATH = Path(__file__).with_name("manifest_schema.json")


def discover_manifests(root: Path) -> list[Path]:
    paths: list[Path] = []
    for name in MANIFEST_FILENAMES:
        paths.extend(root.rglob(name))
    return sorted(set(paths))


def _load_schema() -> dict[str, Any]:
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.lstrip().startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    raw_meta = parts[1]
    body = parts[2].lstrip("\n")
    meta = yaml.safe_load(raw_meta) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, body


def load_manifest(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.name == "SKILL.md":
        meta, body = _load_frontmatter(path)
        if body.strip() and "prompt" not in meta:
            meta["prompt"] = body.strip()
        return meta
    return {}


def _policy_from_payload(payload: dict[str, Any] | None) -> ToolPolicy:
    payload = payload or {}
    redact_payload = payload.get("redact") or {}
    redaction = RedactionPolicy(
        keys=list(redact_payload.get("keys", []) or []),
        paths=list(redact_payload.get("paths", []) or []),
        mask=str(redact_payload.get("mask", "***"))
    )
    return ToolPolicy(
        timeout_ms=payload.get("timeout_ms"),
        max_retries=int(payload.get("max_retries", 0) or 0),
        rate_limit_per_min=payload.get("rate_limit_per_min"),
        redaction=redaction
    )


def parse_manifest(raw: dict[str, Any], source: str) -> SkillManifest:
    schema = _load_schema()
    try:
        jsonschema_validate(instance=raw, schema=schema)
    except ValidationError as exc:
        raise ValueError(f"Manifest validation failed for {source}: {exc.message}") from exc

    tool_payload = raw.get("tool")
    tool = None
    if tool_payload:
        tool = ToolManifest(
            id=str(tool_payload.get("id") or raw["id"]),
            name=str(tool_payload.get("name") or raw["name"]),
            description=str(tool_payload.get("description") or raw["description"]),
            handler=str(tool_payload["handler"]),
            parameters=dict(tool_payload["parameters"]),
            policy=_policy_from_payload(tool_payload.get("policy"))
        )

    return SkillManifest(
        id=str(raw["id"]),
        name=str(raw["name"]),
        description=str(raw["description"]),
        prompt=raw.get("prompt"),
        tools=list(raw.get("tools")) if raw.get("tools") is not None else None,
        tool=tool,
        origin=str(raw.get("origin") or "manifest"),
        source=source
    )


def _import_handler(path: str):
    module_path, _, attribute = path.partition(":")
    if not module_path or not attribute:
        raise ValueError(f"Handler path must be in module:attr form: {path}")
    module = importlib.import_module(module_path)
    handler = getattr(module, attribute, None)
    if handler is None:
        raise ValueError(f"Handler not found: {path}")
    return handler


def manifest_to_tool(manifest: SkillManifest) -> Tool | None:
    if not manifest.tool:
        return None
    handler = _import_handler(manifest.tool.handler)
    return Tool(
        id=manifest.tool.id,
        name=manifest.tool.name,
        description=manifest.tool.description,
        parameters=manifest.tool.parameters,
        handler=handler,
        policy=manifest.tool.policy
    )


def manifest_to_skill(manifest: SkillManifest, tool_id: str | None) -> Skill | None:
    tools = manifest.tools
    if tools is None and tool_id:
        tools = [tool_id]
    if not manifest.prompt and not tools:
        return None
    return Skill(
        id=manifest.id,
        name=manifest.name,
        description=manifest.description,
        prompt=manifest.prompt,
        tools=list(tools or []),
        origin=manifest.origin,
        source=manifest.source
    )


def load_manifests(root: Path) -> ManifestLoadResult:
    tools: list[Tool] = []
    skills: list[Skill] = []
    errors: list[str] = []
    for path in discover_manifests(root):
        try:
            raw = load_manifest(path)
            manifest = parse_manifest(raw, str(path))
            tool = manifest_to_tool(manifest)
            if tool:
                tools.append(tool)
            skill = manifest_to_skill(manifest, tool.id if tool else None)
            if skill:
                skills.append(skill)
        except Exception as exc:
            errors.append(str(exc))
    return ManifestLoadResult(tools=tools, skills=skills, errors=errors)
