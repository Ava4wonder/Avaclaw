from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import html as html_lib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any
import uuid

import requests

from ..config import settings
from .academic_search import fetch_full_content, html_parsing_chunking_upsert


QUESTION_TYPE_PRIORITY = {
    "structure": 5,
    "subsystem_mapping": 5,
    "module_design": 5,
    "interface_contract": 5,
    "build_constraints": 4,
    "data_flow": 4,
    "algorithm": 4,
    "training": 3,
    "inference": 3,
    "parameter": 3,
    "edge_case": 2,
    "evaluation_protocol": 2,
    "implementation_gap": 1,
}

LANGUAGE_ALIASES = {
    "py": "python",
    "python3": "python",
    "ts": "typescript",
    "tsx": "typescript",
    "js": "javascript",
    "jsx": "javascript",
    "node": "javascript",
    "golang": "go",
    "rs": "rust",
    "c++": "cpp",
    "cc": "cpp",
    "cxx": "cpp",
    "hpp": "cpp",
    "h": "cpp",
    "proto3": "protobuf",
}

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "cpp",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".proto": "protobuf",
    ".thrift": "thrift",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".sql": "sql",
    ".ini": "ini",
    ".cfg": "ini",
    ".md": "markdown",
}

TARGET_CODE_LANGUAGES = {"python", "typescript", "java", "go", "rust", "cpp", "javascript"}
IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "target",
    "out",
    ".next",
    ".turbo",
    ".py312avacla",
}
BUILD_FILE_NAMES = {
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "package.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "go.mod",
    "Cargo.toml",
    "CMakeLists.txt",
    "BUILD",
    "BUILD.bazel",
    "WORKSPACE",
    "WORKSPACE.bazel",
    "Makefile",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    text = html_lib.unescape(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)
    return output


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", (text or "").lower())


def _sentence_split(text: str) -> list[str]:
    if not text:
        return []
    raw_parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in raw_parts if part.strip()]


def _semantic_split_text(text: str, max_chars: int = 1200) -> list[str]:
    text = _normalize_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    sentences = _sentence_split(text)
    if not sentences:
        return [text[:max_chars]]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        sentence_len = len(sentence)
        if current and current_len + sentence_len + 1 > max_chars:
            chunks.append(" ".join(current).strip())
            current = [sentence]
            current_len = sentence_len
            continue
        current.append(sentence)
        current_len += sentence_len + 1
    if current:
        chunks.append(" ".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _extract_object_number(caption: str, kind: str) -> str:
    if not caption:
        return ""
    if kind == "image":
        match = re.search(r"\b(?:fig(?:ure)?\.?)\s*([0-9A-Za-z._-]+)", caption, flags=re.IGNORECASE)
    else:
        match = re.search(r"\btable\s*([0-9A-Za-z._-]+)", caption, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _to_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return slug or "module"


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _coerce_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(low, min(high, parsed))


def _normalize_language(language: str) -> str:
    raw = (language or "").strip().lower()
    return LANGUAGE_ALIASES.get(raw, raw)


def _priority_label(question_type: str) -> str:
    score = QUESTION_TYPE_PRIORITY.get(question_type, 1)
    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _matches_any_prefix(path: str, prefixes: list[str]) -> bool:
    if not prefixes:
        return True
    normalized = path.replace("\\", "/").lstrip("./")
    for prefix in prefixes:
        p = prefix.replace("\\", "/").lstrip("./")
        if not p:
            continue
        if normalized == p or normalized.startswith(f"{p}/"):
            return True
    return False


def _log_entry(
    question_id: str,
    module_id: str,
    cited_chunk_ids: list[str],
    outcome_status: str,
    confidence: float,
    next_action: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": _utc_now_iso(),
        "question_id": question_id,
        "module_id": module_id,
        "cited_chunk_ids": cited_chunk_ids,
        "outcome_status": outcome_status,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "next_action": next_action,
        "details": details or {},
    }


@dataclass
class PaperChunk:
    chunk_id: str
    type: str
    content: str
    headings_info: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodeChunk:
    chunk_id: str
    repo_path: str
    language: str
    symbol_kind: str
    symbol_name: str
    content: str
    signature: str = ""
    docstring: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RepositoryModule:
    module_id: str
    path_prefix: str
    languages: list[str] = field(default_factory=list)
    file_count: int = 0
    symbol_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BuildTarget:
    target_id: str
    target_type: str
    path: str
    languages: list[str]
    commands: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InterfaceContract:
    contract_id: str
    contract_type: str
    repo_path: str
    language: str
    entities: list[str]
    operations: list[str]
    producers: list[str] = field(default_factory=list)
    consumers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RepositoryCollection:
    collection_id: str
    repo_root: str
    chunks: list[CodeChunk]
    modules: list[RepositoryModule]
    build_targets: list[BuildTarget]
    tests: list[str]
    configs: list[str]
    schemas: list[str]
    services: list[str]
    interface_contracts: list[InterfaceContract]
    dependency_edges: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "collection_id": self.collection_id,
            "repo_root": self.repo_root,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "modules": [module.to_dict() for module in self.modules],
            "build_targets": [target.to_dict() for target in self.build_targets],
            "tests": self.tests,
            "configs": self.configs,
            "schemas": self.schemas,
            "services": self.services,
            "interface_contracts": [contract.to_dict() for contract in self.interface_contracts],
            "dependency_edges": self.dependency_edges,
            "metadata": self.metadata,
        }


@dataclass
class GraphEdge:
    source: str
    target: str
    edge_type: str
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RepositoryGraph:
    graph_id: str
    graph_type: str
    nodes: list[dict[str, Any]]
    edges: list[GraphEdge]

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "graph_type": self.graph_type,
            "nodes": self.nodes,
            "edges": [edge.to_dict() for edge in self.edges],
            "summary": {"node_count": len(self.nodes), "edge_count": len(self.edges)},
        }


@dataclass
class RepositoryGraphBundle:
    import_graph: RepositoryGraph
    symbol_reference_graph: RepositoryGraph
    module_dependency_graph: RepositoryGraph
    build_target_graph: RepositoryGraph
    service_dataflow_graph: RepositoryGraph
    adjacency: dict[str, set[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "import_graph": self.import_graph.to_dict(),
            "symbol_reference_graph": self.symbol_reference_graph.to_dict(),
            "module_dependency_graph": self.module_dependency_graph.to_dict(),
            "build_target_graph": self.build_target_graph.to_dict(),
            "service_dataflow_graph": self.service_dataflow_graph.to_dict(),
        }


@dataclass
class PlanQuestion:
    question_id: str
    question_depth: int
    question: str
    question_type: str
    paper_scopes: list[str] = field(default_factory=list)
    repo_paths: list[str] = field(default_factory=list)
    target_languages: list[str] = field(default_factory=list)
    target_symbols: list[str] = field(default_factory=list)
    build_targets: list[str] = field(default_factory=list)
    subsystem_id: str = "repository"
    allowed_edit_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    goal_alignment: list[str] = field(default_factory=list)
    expected_output_type: str = "design_spec"
    priority: str = "medium"
    status: str = "pending"
    parent_question_id: str | None = None
    module_id: str = "framework"
    toc_page_indexes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload["toc_page_indexes"]:
            payload["toc_page_indexes"] = list(self.paper_scopes)
        return payload


@dataclass
class WorkingSet:
    repository_map: list[str]
    subsystem_map: dict[str, Any]
    candidate_file_set: list[str]
    candidate_symbol_set: list[str]
    bounded_edit_set: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DesignAnswer:
    question_id: str
    implementation_brief: dict[str, Any]
    citations: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    paper_evidence: list[dict[str, Any]] = field(default_factory=list)
    code_evidence: list[dict[str, Any]] = field(default_factory=list)
    merged_evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodeArtifact:
    artifact_id: str
    question_id: str
    files_changed: list[str]
    summary: str
    traceability: dict[str, Any]
    execution_logs: list[str]
    implementation_notes: list[str]
    generated_code: str
    language: str = "python"
    adapter_id: str = "fallback"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationRecord:
    question_id: str
    evaluation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _PaperHtmlParser(HTMLParser):
    """HTML parser that preserves headings, text blocks, figures, and tables."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._heading_level: int | None = None
        self._heading_buffer: list[str] = []
        self._text_tag: str | None = None
        self._text_buffer: list[str] = []
        self._text_path = ""
        self._in_figure = False
        self._figure_path = ""
        self._figure_buffer: list[str] = []
        self._figure_caption_buffer: list[str] = []
        self._figure_img_src = ""
        self._figure_img_alt = ""
        self._in_figcaption = False
        self._in_table = False
        self._table_path = ""
        self._table_buffer: list[str] = []
        self._table_caption_buffer: list[str] = []
        self._in_table_caption = False
        self._tag_stack: list[str] = []
        self.heading_stack: list[str] = []
        self.toc_paths: list[str] = []
        self.raw_chunks: list[dict[str, Any]] = []

    def _current_path(self) -> str:
        return "/".join(self._tag_stack)

    def _current_headings(self) -> str:
        if self.heading_stack:
            return " > ".join(self.heading_stack)
        return "Document"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): (value or "") for key, value in attrs}

        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            self._tag_stack.append(tag)
            return

        self._tag_stack.append(tag)
        if self._skip_depth > 0:
            return

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_level = int(tag[1])
            self._heading_buffer = []
            return

        if tag in {"p", "li", "blockquote", "pre"} and not self._in_figure and not self._in_table:
            self._text_tag = tag
            self._text_buffer = []
            self._text_path = self._current_path()
            return

        if tag == "figure":
            self._in_figure = True
            self._figure_path = self._current_path()
            self._figure_buffer = []
            self._figure_caption_buffer = []
            self._figure_img_src = ""
            self._figure_img_alt = ""
            return

        if tag == "img":
            src = attrs_dict.get("src", "").strip()
            alt = attrs_dict.get("alt", "").strip()
            if self._in_figure:
                if src:
                    self._figure_img_src = src
                if alt:
                    self._figure_img_alt = alt
            elif src or alt:
                self.raw_chunks.append(
                    {
                        "type": "image",
                        "content": _normalize_text(f"{alt} {src}"),
                        "headings_info": self._current_headings(),
                        "metadata": {
                            "caption": _normalize_text(alt),
                            "image_src": src,
                            "figure_number": _extract_object_number(alt, "image"),
                            "source_html_node_path": self._current_path(),
                        },
                    }
                )
            return

        if tag == "figcaption" and self._in_figure:
            self._in_figcaption = True
            return

        if tag == "table":
            self._in_table = True
            self._table_path = self._current_path()
            self._table_buffer = []
            self._table_caption_buffer = []
            return

        if tag == "caption" and self._in_table:
            self._in_table_caption = True
            return

        if tag == "tr" and self._in_table:
            self._table_buffer.append("\n")
            return

        if tag in {"td", "th"} and self._in_table:
            self._table_buffer.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_depth > 0:
            if tag in {"script", "style", "noscript"}:
                self._skip_depth = max(0, self._skip_depth - 1)
            if self._tag_stack:
                self._tag_stack.pop()
            return

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._heading_level:
            heading_text = _normalize_text("".join(self._heading_buffer))
            if heading_text:
                if self._heading_level <= len(self.heading_stack):
                    self.heading_stack = self.heading_stack[: self._heading_level - 1]
                self.heading_stack.append(heading_text)
                self.toc_paths.append(" > ".join(self.heading_stack))
            self._heading_level = None
            self._heading_buffer = []

        if self._text_tag and tag == self._text_tag:
            text = _normalize_text("".join(self._text_buffer))
            if text:
                self.raw_chunks.append(
                    {
                        "type": "text",
                        "content": text,
                        "headings_info": self._current_headings(),
                        "metadata": {"source_html_node_path": self._text_path},
                    }
                )
            self._text_tag = None
            self._text_buffer = []
            self._text_path = ""

        if tag == "figcaption" and self._in_figure:
            self._in_figcaption = False

        if tag == "figure" and self._in_figure:
            caption = _normalize_text("".join(self._figure_caption_buffer))
            content = _normalize_text(" ".join(self._figure_buffer))
            if not content:
                content = caption
            if content or caption or self._figure_img_src:
                self.raw_chunks.append(
                    {
                        "type": "image",
                        "content": content,
                        "headings_info": self._current_headings(),
                        "metadata": {
                            "caption": caption,
                            "image_src": self._figure_img_src,
                            "image_alt": self._figure_img_alt,
                            "figure_number": _extract_object_number(caption or self._figure_img_alt, "image"),
                            "source_html_node_path": self._figure_path,
                        },
                    }
                )
            self._in_figure = False
            self._figure_path = ""
            self._figure_buffer = []
            self._figure_caption_buffer = []
            self._figure_img_src = ""
            self._figure_img_alt = ""
            self._in_figcaption = False

        if tag == "caption" and self._in_table:
            self._in_table_caption = False

        if tag == "table" and self._in_table:
            caption = _normalize_text("".join(self._table_caption_buffer))
            content = _normalize_text("".join(self._table_buffer))
            combined = _normalize_text(f"{caption} {content}")
            if combined:
                self.raw_chunks.append(
                    {
                        "type": "table",
                        "content": combined,
                        "headings_info": self._current_headings(),
                        "metadata": {
                            "caption": caption,
                            "table_number": _extract_object_number(caption, "table"),
                            "source_html_node_path": self._table_path,
                        },
                    }
                )
            self._in_table = False
            self._table_path = ""
            self._table_buffer = []
            self._table_caption_buffer = []
            self._in_table_caption = False

        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._heading_level:
            self._heading_buffer.append(data)
            return
        if self._in_figure:
            if self._in_figcaption:
                self._figure_caption_buffer.append(data)
            else:
                self._figure_buffer.append(data)
            return
        if self._in_table:
            if self._in_table_caption:
                self._table_caption_buffer.append(data)
            else:
                self._table_buffer.append(data)
            return
        if self._text_tag:
            self._text_buffer.append(data)


def _format_toc(paths: list[str]) -> str:
    if not paths:
        return "Document"
    lines: list[str] = []
    for path in _dedupe_preserve_order(paths):
        depth = max(0, path.count(">"))
        indent = "  " * depth
        lines.append(f"{indent}- {path.split('>')[-1].strip()}")
    return "\n".join(lines).strip()


def _build_token_index(chunks: list[PaperChunk]) -> dict[str, Counter[str]]:
    index: dict[str, Counter[str]] = {}
    for chunk in chunks:
        source = f"{chunk.headings_info} {chunk.content}"
        index[chunk.chunk_id] = Counter(_tokenize(source))
    return index


def _collection_overview(chunks: list[PaperChunk]) -> dict[str, Any]:
    by_type: Counter[str] = Counter(chunk.type for chunk in chunks)
    return {"total_chunks": len(chunks), "by_type": dict(by_type)}


def _academic_chunking_runtime_available() -> bool:
    try:
        qdrant_url = f"http://{settings.qdrant_host}:{settings.qdrant_port}/collections"
        qdrant_res = requests.get(qdrant_url, timeout=0.6)
        if qdrant_res.status_code >= 500:
            return False
    except Exception:
        return False

    try:
        ollama_url = f"{settings.ollama_base_url}/api/tags"
        ollama_res = requests.get(ollama_url, timeout=0.6)
        if ollama_res.status_code >= 500:
            return False
    except Exception:
        return False
    return True


def _qdrant_scroll_all(collection_name: str, page_size: int = 256) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    url = f"http://{settings.qdrant_host}:{settings.qdrant_port}/collections/{collection_name}/points/scroll"
    next_offset: Any = None
    while True:
        payload: dict[str, Any] = {"limit": page_size, "with_payload": True, "with_vector": False}
        if next_offset is not None:
            payload["offset"] = next_offset

        res = requests.post(url, json=payload, timeout=30.0)
        if res.status_code >= 400:
            raise RuntimeError(f"Qdrant scroll error {res.status_code}: {res.text}")

        data = res.json() or {}
        result = data.get("result") or {}
        page_points: list[dict[str, Any]]
        if isinstance(result, dict):
            page_points = result.get("points", []) or []
            next_offset = result.get("next_page_offset")
        elif isinstance(result, list):
            page_points = result
            next_offset = None
        else:
            page_points = []

        if not page_points:
            break
        points.extend(page_points)
        if next_offset is None:
            break
    return points


def _toc_paths_from_text_toc(text_toc: str) -> list[str]:
    raw_lines = [line.strip() for line in (text_toc or "").splitlines() if line.strip()]
    toc_paths: list[str] = []
    for line in raw_lines:
        cleaned = re.sub(r"^[-*]+\s*", "", line)
        cleaned = cleaned.replace("> ", ">").replace(" >", ">")
        if ">" in cleaned:
            normalized = " > ".join(part.strip() for part in cleaned.split(">") if part.strip())
            if normalized:
                toc_paths.append(normalized)
        else:
            toc_paths.append(cleaned)
    return _dedupe_preserve_order(toc_paths)


def _build_collection_from_academic_chunking(
    html_content: str,
    paper_title: str,
    arxiv_id: str,
    collection_id: str | None,
    chunk_max_chars: int,
) -> dict[str, Any] | None:
    try:
        chunking_result = html_parsing_chunking_upsert(
            html_content=html_content,
            paper_title=paper_title,
            arxiv_id=arxiv_id,
            chunk_size=chunk_max_chars,
            chunk_overlap=max(100, int(chunk_max_chars * 0.15)),
        )
    except Exception:
        return None

    collection_name = str(chunking_result.get("collection_name", "")).strip()
    text_toc = str(chunking_result.get("text_toc", "")).strip()
    toc_paths = _toc_paths_from_text_toc(text_toc)
    points: list[dict[str, Any]] = []
    if collection_name:
        try:
            points = _qdrant_scroll_all(collection_name)
        except Exception:
            points = []
    if not points:
        return None

    chunks: list[PaperChunk] = []
    for idx, point in enumerate(points, start=1):
        payload = point.get("payload") or {}
        content = _normalize_text(str(payload.get("chunk_text", "")))
        if not content:
            continue
        headings = str(payload.get("headings_info", "Document")).strip() or "Document"
        headings = " > ".join(part.strip() for part in headings.split(">") if part.strip()) or "Document"
        chunks.append(
            PaperChunk(
                chunk_id=f"chunk-{idx:04d}",
                type="text",
                content=content,
                headings_info=headings,
                metadata={
                    "section_order_index": idx - 1,
                    "source": "academic_search.html_parsing_chunking_upsert",
                    "qdrant_point_id": point.get("id"),
                    "paper_title": payload.get("paper_title", paper_title),
                    "arxiv_id": payload.get("arxiv_id", arxiv_id),
                },
            )
        )
    if not chunks:
        return None

    if not toc_paths:
        toc_paths = _dedupe_preserve_order([chunk.headings_info for chunk in chunks if chunk.headings_info])
    toc_text = _format_toc(toc_paths)
    toc_chunk = PaperChunk(
        chunk_id="chunk-0000",
        type="toc",
        content=toc_text,
        headings_info="TOC",
        metadata={
            "section_order_index": -1,
            "source": "academic_search.html_parsing_chunking_upsert",
            "source_collection_name": collection_name,
            "chunks_upserted": chunking_result.get("chunks_upserted", 0),
        },
    )
    all_chunks = [toc_chunk, *chunks]
    for idx, chunk in enumerate(all_chunks):
        nearby_ids: list[str] = []
        if idx > 0:
            nearby_ids.append(all_chunks[idx - 1].chunk_id)
        if idx < len(all_chunks) - 1:
            nearby_ids.append(all_chunks[idx + 1].chunk_id)
        chunk.metadata["nearby_chunks"] = nearby_ids

    resolved_collection_id = collection_id or f"paper_to_code_{uuid.uuid4().hex[:12]}"
    token_index = _build_token_index(all_chunks)
    return {
        "collection_id": resolved_collection_id,
        "paper_title": paper_title,
        "chunks": [chunk.to_dict() for chunk in all_chunks],
        "toc_chunk_id": "chunk-0000",
        "toc_paths": toc_paths,
        "token_index": {key: dict(counter) for key, counter in token_index.items()},
        "overview": _collection_overview(all_chunks),
        "source_collection_name": collection_name,
        "source_chunks_upserted": chunking_result.get("chunks_upserted", 0),
    }


def _build_collection_from_spec_text(spec_text: str, collection_id: str | None = None) -> dict[str, Any]:
    normalized = _normalize_text(spec_text)
    sentences = _semantic_split_text(normalized, max_chars=1200)
    chunks = [
        PaperChunk(
            chunk_id=f"chunk-{idx:04d}",
            type="text",
            content=sentence,
            headings_info="Specification",
            metadata={"section_order_index": idx - 1, "source": "spec_text"},
        )
        for idx, sentence in enumerate(sentences, start=1)
        if sentence
    ]
    toc_chunk = PaperChunk(
        chunk_id="chunk-0000",
        type="toc",
        content="- Specification",
        headings_info="TOC",
        metadata={"section_order_index": -1, "source": "spec_text"},
    )
    all_chunks = [toc_chunk, *chunks]
    token_index = _build_token_index(all_chunks)
    return {
        "collection_id": collection_id or f"spec_to_code_{uuid.uuid4().hex[:12]}",
        "paper_title": "Specification",
        "chunks": [chunk.to_dict() for chunk in all_chunks],
        "toc_chunk_id": "chunk-0000",
        "toc_paths": ["Specification"],
        "token_index": {key: dict(counter) for key, counter in token_index.items()},
        "overview": _collection_overview(all_chunks),
    }


def prepare_vector_store_collection(
    html_content: str,
    paper_title: str = "",
    arxiv_id: str = "",
    collection_id: str | None = None,
    chunk_max_chars: int = 1200,
    reuse_academic_chunking: bool = True,
) -> dict[str, Any]:
    if reuse_academic_chunking and html_content and _academic_chunking_runtime_available():
        reused_collection = _build_collection_from_academic_chunking(
            html_content=html_content,
            paper_title=paper_title,
            arxiv_id=arxiv_id,
            collection_id=collection_id,
            chunk_max_chars=chunk_max_chars,
        )
        if reused_collection:
            return reused_collection

    parser = _PaperHtmlParser()
    parser.feed(html_content or "")
    parser.close()

    raw_chunks = parser.raw_chunks
    toc_paths = _dedupe_preserve_order(parser.toc_paths) or ["Document"]
    toc_text = _format_toc(toc_paths)

    chunks: list[PaperChunk] = []
    section_order = 0
    for raw in raw_chunks:
        chunk_type = str(raw.get("type", "text"))
        headings_info = str(raw.get("headings_info", "Document")).strip() or "Document"
        metadata = dict(raw.get("metadata") or {})
        metadata["section_order_index"] = section_order
        section_order += 1
        content = _normalize_text(str(raw.get("content", "")))
        if not content:
            continue

        if chunk_type == "text":
            for part in _semantic_split_text(content, max_chars=chunk_max_chars):
                if part:
                    chunks.append(
                        PaperChunk(
                            chunk_id="",
                            type="text",
                            content=part,
                            headings_info=headings_info,
                            metadata=dict(metadata),
                        )
                    )
            continue
        chunks.append(
            PaperChunk(
                chunk_id="",
                type=chunk_type,
                content=content,
                headings_info=headings_info,
                metadata=metadata,
            )
        )

    toc_chunk = PaperChunk(
        chunk_id="chunk-0000",
        type="toc",
        content=toc_text,
        headings_info="TOC",
        metadata={"section_order_index": -1, "source_html_node_path": "document"},
    )
    for idx, chunk in enumerate(chunks, start=1):
        chunk.chunk_id = f"chunk-{idx:04d}"

    all_chunks = [toc_chunk, *chunks]
    chunk_lookup = {chunk.chunk_id: chunk for chunk in all_chunks}
    for idx, chunk in enumerate(all_chunks):
        nearby_ids: list[str] = []
        if idx > 0:
            nearby_ids.append(all_chunks[idx - 1].chunk_id)
        if idx < len(all_chunks) - 1:
            nearby_ids.append(all_chunks[idx + 1].chunk_id)
        chunk.metadata["nearby_chunks"] = nearby_ids
        multimodal_links: list[str] = []
        for nearby_id in nearby_ids:
            nearby = chunk_lookup.get(nearby_id)
            if nearby and nearby.type in {"image", "table"} and chunk.type == "text":
                multimodal_links.append(nearby_id)
        if multimodal_links:
            chunk.metadata["multimodal_links"] = multimodal_links

    resolved_collection_id = collection_id or f"paper_to_code_{uuid.uuid4().hex[:12]}"
    token_index = _build_token_index(all_chunks)
    return {
        "collection_id": resolved_collection_id,
        "paper_title": paper_title,
        "chunks": [chunk.to_dict() for chunk in all_chunks],
        "toc_chunk_id": "chunk-0000",
        "toc_paths": toc_paths,
        "token_index": {key: dict(counter) for key, counter in token_index.items()},
        "overview": _collection_overview(all_chunks),
    }


def _extract_imports(content: str, language: str) -> list[str]:
    imports: list[str] = []
    if language == "python":
        pattern = re.compile(r"^\s*(?:from\s+([a-zA-Z0-9_\.]+)\s+import|import\s+([a-zA-Z0-9_\. ,]+))", re.MULTILINE)
        for a, b in pattern.findall(content):
            if a:
                imports.append(a.strip())
            if b:
                parts = [part.strip() for part in b.split(",") if part.strip()]
                imports.extend(parts)
    elif language in {"typescript", "javascript"}:
        pattern = re.compile(r"""import\s+(?:[^'"]+from\s+)?['"]([^'"]+)['"]|require\(['"]([^'"]+)['"]\)""")
        for a, b in pattern.findall(content):
            imports.append((a or b).strip())
    elif language == "java":
        imports.extend(re.findall(r"^\s*import\s+([a-zA-Z0-9_\.]+);", content, flags=re.MULTILINE))
    elif language == "go":
        imports.extend(re.findall(r'"([a-zA-Z0-9_/\.-]+)"', content))
    elif language == "rust":
        imports.extend(re.findall(r"^\s*use\s+([a-zA-Z0-9_:\.]+)", content, flags=re.MULTILINE))
    elif language == "cpp":
        imports.extend(re.findall(r'^\s*#include\s+[<"]([^>"]+)[>"]', content, flags=re.MULTILINE))
    return _dedupe_preserve_order(imports)[:200]


def _extract_symbols(content: str, language: str) -> list[dict[str, Any]]:
    lines = content.splitlines()
    symbols: list[dict[str, Any]] = []
    patterns: list[tuple[str, re.Pattern[str]]] = []

    if language == "python":
        patterns = [
            ("class", re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)")),
            ("function", re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
        ]
    elif language in {"typescript", "javascript"}:
        patterns = [
            ("class", re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)")),
            ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)")),
            ("function", re.compile(r"^\s*(?:export\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
        ]
    elif language == "java":
        patterns = [
            ("class", re.compile(r"^\s*(?:public\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)")),
            ("interface", re.compile(r"^\s*(?:public\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)")),
            ("method", re.compile(r"^\s*(?:public|private|protected).+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
        ]
    elif language == "go":
        patterns = [
            ("struct", re.compile(r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+struct\b")),
            ("interface", re.compile(r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+interface\b")),
            ("function", re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
        ]
    elif language == "rust":
        patterns = [
            ("struct", re.compile(r"^\s*(?:pub\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)")),
            ("trait", re.compile(r"^\s*(?:pub\s+)?trait\s+([A-Za-z_][A-Za-z0-9_]*)")),
            ("function", re.compile(r"^\s*(?:pub\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
        ]
    elif language == "cpp":
        patterns = [
            ("class", re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)")),
            ("struct", re.compile(r"^\s*struct\s+([A-Za-z_][A-Za-z0-9_]*)")),
            ("function", re.compile(r"^\s*[\w:<>,~*&\s]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{?")),
        ]

    for idx, line in enumerate(lines, start=1):
        for kind, pattern in patterns:
            match = pattern.search(line)
            if not match:
                continue
            name = match.group(1)
            symbols.append(
                {
                    "symbol_kind": kind,
                    "symbol_name": name,
                    "signature": line.strip(),
                    "line_start": idx,
                    "line_end": min(len(lines), idx + 25),
                    "docstring": "",
                }
            )
            break
    return symbols


def _extract_contracts(repo_path: str, language: str, content: str) -> list[InterfaceContract]:
    contracts: list[InterfaceContract] = []
    suffix = Path(repo_path).suffix.lower()
    entity_limit = 40

    if suffix == ".proto":
        entities = _dedupe_preserve_order(re.findall(r"\b(?:message|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", content))[:entity_limit]
        ops = _dedupe_preserve_order(re.findall(r"\brpc\s+([A-Za-z_][A-Za-z0-9_]*)", content))[:entity_limit]
        services = _dedupe_preserve_order(re.findall(r"\bservice\s+([A-Za-z_][A-Za-z0-9_]*)", content))[:entity_limit]
        contracts.append(
            InterfaceContract(
                contract_id=f"contract-{uuid.uuid4().hex[:10]}",
                contract_type="protobuf",
                repo_path=repo_path,
                language="protobuf",
                entities=entities + services,
                operations=ops,
            )
        )
    elif suffix == ".thrift":
        entities = _dedupe_preserve_order(re.findall(r"\b(?:struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", content))[:entity_limit]
        ops = _dedupe_preserve_order(re.findall(r"\bservice\s+([A-Za-z_][A-Za-z0-9_]*)", content))[:entity_limit]
        contracts.append(
            InterfaceContract(
                contract_id=f"contract-{uuid.uuid4().hex[:10]}",
                contract_type="thrift",
                repo_path=repo_path,
                language="thrift",
                entities=entities,
                operations=ops,
            )
        )
    elif suffix in {".graphql", ".gql"}:
        entities = _dedupe_preserve_order(re.findall(r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)", content))[:entity_limit]
        ops = _dedupe_preserve_order(re.findall(r"\b(query|mutation|subscription)\b", content, flags=re.IGNORECASE))[:entity_limit]
        contracts.append(
            InterfaceContract(
                contract_id=f"contract-{uuid.uuid4().hex[:10]}",
                contract_type="graphql",
                repo_path=repo_path,
                language="graphql",
                entities=entities,
                operations=ops,
            )
        )
    elif suffix in {".yaml", ".yml", ".json"} and ("openapi" in content.lower() or "swagger" in content.lower()):
        entities = _dedupe_preserve_order(re.findall(r"['\"](/[^'\"]+)['\"]\s*:", content))[:entity_limit]
        contracts.append(
            InterfaceContract(
                contract_id=f"contract-{uuid.uuid4().hex[:10]}",
                contract_type="openapi",
                repo_path=repo_path,
                language=language,
                entities=entities,
                operations=["rest"],
            )
        )
    elif suffix == ".sql" and re.search(r"\bcreate\s+table\b", content, flags=re.IGNORECASE):
        entities = _dedupe_preserve_order(re.findall(r"\bcreate\s+table\s+([A-Za-z_][A-Za-z0-9_]*)", content, flags=re.IGNORECASE))
        contracts.append(
            InterfaceContract(
                contract_id=f"contract-{uuid.uuid4().hex[:10]}",
                contract_type="db_schema",
                repo_path=repo_path,
                language="sql",
                entities=entities[:entity_limit],
                operations=["ddl"],
            )
        )
    return contracts


def _detect_build_targets(repo_root: Path, repo_files: list[str], languages_seen: set[str]) -> list[BuildTarget]:
    targets: list[BuildTarget] = []
    repo_file_set = set(repo_files)

    def _add_target(target_type: str, rel_path: str, languages: list[str], commands: list[str], metadata: dict[str, Any] | None = None) -> None:
        targets.append(
            BuildTarget(
                target_id=f"target-{uuid.uuid4().hex[:10]}",
                target_type=target_type,
                path=rel_path,
                languages=_dedupe_preserve_order(languages),
                commands=commands,
                metadata=metadata or {},
            )
        )

    for rel_path in sorted(repo_file_set):
        filename = Path(rel_path).name
        if filename not in BUILD_FILE_NAMES:
            continue
        if filename == "pyproject.toml":
            _add_target("python_project", rel_path, ["python"], ["python -m pytest -q", "python -m py_compile"])
        elif filename == "requirements.txt":
            _add_target("python_requirements", rel_path, ["python"], ["python -m pytest -q"])
        elif filename == "setup.py":
            _add_target("python_setup", rel_path, ["python"], ["python setup.py test"])
        elif filename == "package.json":
            _add_target("node_project", rel_path, ["typescript", "javascript"], ["npm run test --if-present", "npm run typecheck --if-present", "npm run build --if-present"])
        elif filename == "pom.xml":
            _add_target("maven_project", rel_path, ["java"], ["mvn -q test", "mvn -q -DskipTests package"])
        elif filename in {"build.gradle", "build.gradle.kts", "settings.gradle"}:
            _add_target("gradle_project", rel_path, ["java"], ["./gradlew test", "./gradlew build"])
        elif filename == "go.mod":
            _add_target("go_module", rel_path, ["go"], ["go test ./...", "go build ./..."])
        elif filename == "Cargo.toml":
            _add_target("rust_crate", rel_path, ["rust"], ["cargo test", "cargo check"])
        elif filename == "CMakeLists.txt":
            _add_target("cmake_project", rel_path, ["cpp"], ["cmake --build .", "ctest"])
        elif filename in {"BUILD", "BUILD.bazel", "WORKSPACE", "WORKSPACE.bazel"}:
            _add_target("bazel_project", rel_path, list(languages_seen), ["bazel test //..."])
        elif filename == "Makefile":
            _add_target("make_project", rel_path, list(languages_seen), ["make test", "make"])

    if not targets and languages_seen:
        fallback_commands: list[str] = []
        if "python" in languages_seen:
            fallback_commands.append("python -m py_compile")
        if {"typescript", "javascript"} & languages_seen:
            fallback_commands.append("npm run build --if-present")
        if "go" in languages_seen:
            fallback_commands.append("go test ./...")
        if "rust" in languages_seen:
            fallback_commands.append("cargo check")
        if "java" in languages_seen:
            fallback_commands.append("mvn -q test")
        if "cpp" in languages_seen:
            fallback_commands.append("cmake --build .")
        _add_target("inferred_target", str(repo_root), sorted(languages_seen), fallback_commands, {"inferred": True})
    return targets


def _walk_repository_files(repo_root: Path, include_paths: list[str], exclude_paths: list[str], max_files: int) -> list[Path]:
    discovered: list[Path] = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        root_path = Path(root)
        for filename in files:
            if filename.startswith("."):
                continue
            path = root_path / filename
            rel = path.relative_to(repo_root).as_posix()
            if include_paths and not _matches_any_prefix(rel, include_paths):
                continue
            if exclude_paths and _matches_any_prefix(rel, exclude_paths):
                continue
            discovered.append(path)
            if len(discovered) >= max_files:
                return discovered
    return discovered


def prepare_codebase_collection(
    repo_root: str,
    collection_id: str | None = None,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    max_files: int = 5000,
    max_file_bytes: int = 600_000,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"repo_root not found: {root}")

    include_paths = include_paths or []
    exclude_paths = exclude_paths or []
    discovered = _walk_repository_files(root, include_paths, exclude_paths, max_files=max_files)

    chunks: list[CodeChunk] = []
    module_rollup: dict[str, dict[str, Any]] = defaultdict(lambda: {"languages": set(), "file_count": 0, "symbol_count": 0})
    dependency_edges: list[dict[str, Any]] = []
    tests: list[str] = []
    configs: list[str] = []
    schemas: list[str] = []
    services: list[str] = []
    interface_contracts: list[InterfaceContract] = []
    languages_seen: set[str] = set()
    repo_files: list[str] = []

    for file_path in discovered:
        rel = file_path.relative_to(root).as_posix()
        repo_files.append(rel)
        suffix = file_path.suffix.lower()
        language = LANGUAGE_BY_EXTENSION.get(suffix, "")

        try:
            if file_path.stat().st_size > max_file_bytes:
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not content.strip():
            continue

        if language:
            languages_seen.add(language)
        module_id = rel.split("/", 1)[0] if "/" in rel else "root"
        module_rollup[module_id]["file_count"] += 1
        if language:
            module_rollup[module_id]["languages"].add(language)

        lower_rel = rel.lower()
        is_test = any(token in lower_rel for token in ["test", "spec"]) or lower_rel.startswith("tests/")
        if is_test:
            tests.append(rel)
        if suffix in {".yaml", ".yml", ".json", ".toml", ".ini", ".cfg"}:
            configs.append(rel)
        if suffix in {".sql", ".proto", ".thrift", ".graphql", ".gql"}:
            schemas.append(rel)
        if re.search(r"\b(route|endpoint|grpc|rpc|handler|service)\b", content, flags=re.IGNORECASE):
            services.append(rel)

        imports = _extract_imports(content, language)
        for imported in imports:
            dependency_edges.append({"source": rel, "target": imported, "edge_type": "import", "language": language})

        contracts = _extract_contracts(rel, language, content)
        interface_contracts.extend(contracts)

        chunks.append(
            CodeChunk(
                chunk_id=f"code-{uuid.uuid4().hex[:12]}",
                repo_path=rel,
                language=language or "unknown",
                symbol_kind="file",
                symbol_name=Path(rel).name,
                content=content[:3500],
                signature=f"file {rel}",
                docstring="",
                metadata={"module_id": module_id, "imports": imports[:80], "is_test": is_test, "line_count": len(content.splitlines())},
            )
        )

        symbols = _extract_symbols(content, language)
        lines = content.splitlines()
        for symbol in symbols:
            start = int(symbol.get("line_start", 1))
            end = int(symbol.get("line_end", start + 15))
            snippet = "\n".join(lines[max(0, start - 1): min(len(lines), end)])
            chunks.append(
                CodeChunk(
                    chunk_id=f"code-{uuid.uuid4().hex[:12]}",
                    repo_path=rel,
                    language=language or "unknown",
                    symbol_kind=str(symbol.get("symbol_kind", "symbol")),
                    symbol_name=str(symbol.get("symbol_name", "")),
                    content=snippet,
                    signature=str(symbol.get("signature", "")),
                    docstring=str(symbol.get("docstring", "")),
                    metadata={"module_id": module_id, "line_start": start, "line_end": end, "imports": imports[:80], "is_test": is_test},
                )
            )
            module_rollup[module_id]["symbol_count"] += 1

        for contract in contracts:
            chunks.append(
                CodeChunk(
                    chunk_id=f"code-{uuid.uuid4().hex[:12]}",
                    repo_path=rel,
                    language=contract.language,
                    symbol_kind="interface_contract",
                    symbol_name=contract.contract_type,
                    content=content[:3000],
                    signature=f"{contract.contract_type} {rel}",
                    docstring="",
                    metadata={
                        "module_id": module_id,
                        "contract_id": contract.contract_id,
                        "entities": contract.entities,
                        "operations": contract.operations,
                    },
                )
            )

    modules: list[RepositoryModule] = []
    for module_id, rollup in module_rollup.items():
        modules.append(
            RepositoryModule(
                module_id=module_id,
                path_prefix=module_id if module_id != "root" else "",
                languages=sorted(rollup["languages"]),
                file_count=int(rollup["file_count"]),
                symbol_count=int(rollup["symbol_count"]),
            )
        )
    modules.sort(key=lambda m: (m.module_id != "root", m.module_id))

    collection = RepositoryCollection(
        collection_id=collection_id or f"repo_collection_{uuid.uuid4().hex[:12]}",
        repo_root=str(root),
        chunks=chunks,
        modules=modules,
        build_targets=_detect_build_targets(root, repo_files, languages_seen),
        tests=_dedupe_preserve_order(tests),
        configs=_dedupe_preserve_order(configs),
        schemas=_dedupe_preserve_order(schemas),
        services=_dedupe_preserve_order(services),
        interface_contracts=interface_contracts,
        dependency_edges=dependency_edges,
        metadata={
            "overview": {
                "total_files_scanned": len(discovered),
                "total_chunks": len(chunks),
                "languages": sorted(languages_seen),
                "module_count": len(modules),
                "interface_contract_count": len(interface_contracts),
            }
        },
    )
    payload = collection.to_dict()
    payload["chunk_index"] = {"by_path": defaultdict(list), "by_symbol": defaultdict(list)}
    for chunk in payload["chunks"]:
        payload["chunk_index"]["by_path"][chunk["repo_path"]].append(chunk["chunk_id"])
        if chunk.get("symbol_name"):
            payload["chunk_index"]["by_symbol"][chunk["symbol_name"].lower()].append(chunk["chunk_id"])
    payload["chunk_index"]["by_path"] = dict(payload["chunk_index"]["by_path"])
    payload["chunk_index"]["by_symbol"] = dict(payload["chunk_index"]["by_symbol"])
    return payload


def _chunk_objects(collection: dict[str, Any]) -> list[PaperChunk]:
    chunks: list[PaperChunk] = []
    for chunk in collection.get("chunks", []) or []:
        if not isinstance(chunk, dict):
            continue
        chunks.append(
            PaperChunk(
                chunk_id=str(chunk.get("chunk_id", "")),
                type=str(chunk.get("type", "")),
                content=str(chunk.get("content", "")),
                headings_info=str(chunk.get("headings_info", "")),
                metadata=dict(chunk.get("metadata") or {}),
            )
        )
    return chunks


def _code_chunk_objects(collection: dict[str, Any]) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    for chunk in collection.get("chunks", []) or []:
        if not isinstance(chunk, dict):
            continue
        chunks.append(
            CodeChunk(
                chunk_id=str(chunk.get("chunk_id", "")),
                repo_path=str(chunk.get("repo_path", "")),
                language=str(chunk.get("language", "")),
                symbol_kind=str(chunk.get("symbol_kind", "")),
                symbol_name=str(chunk.get("symbol_name", "")),
                content=str(chunk.get("content", "")),
                signature=str(chunk.get("signature", "")),
                docstring=str(chunk.get("docstring", "")),
                metadata=dict(chunk.get("metadata") or {}),
            )
        )
    return chunks


def _repo_node_for_file(path: str) -> str:
    return f"file:{path}"


def _repo_node_for_symbol(path: str, symbol: str) -> str:
    return f"symbol:{path}:{symbol}"


def _repo_node_for_module(module_id: str) -> str:
    return f"module:{module_id}"


def _dedupe_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node.get("id", ""))
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        output.append(node)
    return output


def _build_import_graph(codebase_collection: dict[str, Any]) -> RepositoryGraph:
    chunks = _code_chunk_objects(codebase_collection)
    file_chunks = [chunk for chunk in chunks if chunk.symbol_kind == "file"]
    nodes = [{"id": _repo_node_for_file(chunk.repo_path), "type": "file", "repo_path": chunk.repo_path} for chunk in file_chunks]
    edges: list[GraphEdge] = []
    known_files = {chunk.repo_path for chunk in file_chunks}
    for chunk in file_chunks:
        imports = chunk.metadata.get("imports", []) or []
        for imported in imports:
            imported_clean = str(imported).strip()
            if not imported_clean:
                continue
            candidate_paths = []
            if imported_clean in known_files:
                candidate_paths.append(imported_clean)
            dot_path = imported_clean.replace(".", "/")
            for path in known_files:
                if path.endswith(f"{dot_path}.py") or path.endswith(f"{dot_path}.ts") or path.endswith(f"{dot_path}.js") or path.endswith(dot_path):
                    candidate_paths.append(path)
            if not candidate_paths:
                candidate_paths = [f"external:{imported_clean}"]
            for target in _dedupe_preserve_order(candidate_paths)[:4]:
                source_node = _repo_node_for_file(chunk.repo_path)
                target_node = _repo_node_for_file(target) if target in known_files else f"external:{target}"
                edges.append(GraphEdge(source=source_node, target=target_node, edge_type="imports", metadata={"import": imported_clean}))
    return RepositoryGraph(
        graph_id=f"graph-import-{uuid.uuid4().hex[:8]}",
        graph_type="file_import_graph",
        nodes=nodes,
        edges=edges,
    )


def _build_symbol_reference_graph(codebase_collection: dict[str, Any]) -> RepositoryGraph:
    chunks = _code_chunk_objects(codebase_collection)
    symbol_chunks = [chunk for chunk in chunks if chunk.symbol_kind not in {"file", "interface_contract"} and chunk.symbol_name]
    nodes = [
        {"id": _repo_node_for_symbol(chunk.repo_path, chunk.symbol_name), "type": chunk.symbol_kind, "repo_path": chunk.repo_path, "symbol_name": chunk.symbol_name}
        for chunk in symbol_chunks
    ]
    symbol_name_map: dict[str, list[CodeChunk]] = defaultdict(list)
    for chunk in symbol_chunks:
        symbol_name_map[chunk.symbol_name.lower()].append(chunk)
    edges: list[GraphEdge] = []
    for chunk in symbol_chunks:
        calls = _dedupe_preserve_order(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", chunk.content))[:80]
        for call in calls:
            for target_chunk in symbol_name_map.get(call.lower(), [])[:4]:
                if target_chunk.chunk_id == chunk.chunk_id:
                    continue
                edges.append(
                    GraphEdge(
                        source=_repo_node_for_symbol(chunk.repo_path, chunk.symbol_name),
                        target=_repo_node_for_symbol(target_chunk.repo_path, target_chunk.symbol_name),
                        edge_type="symbol_ref",
                        metadata={"token": call},
                    )
                )
    return RepositoryGraph(
        graph_id=f"graph-symbol-{uuid.uuid4().hex[:8]}",
        graph_type="symbol_reference_graph",
        nodes=nodes,
        edges=edges,
    )


def _build_module_dependency_graph(codebase_collection: dict[str, Any]) -> RepositoryGraph:
    modules = codebase_collection.get("modules", []) or []
    nodes = [
        {"id": _repo_node_for_module(str(module.get("module_id", "root"))), "type": "module", "module_id": str(module.get("module_id", "root"))}
        for module in modules
    ]
    edges: dict[tuple[str, str], int] = defaultdict(int)
    for dep in codebase_collection.get("dependency_edges", []) or []:
        source_path = str(dep.get("source", ""))
        target = str(dep.get("target", ""))
        source_module = source_path.split("/", 1)[0] if "/" in source_path else "root"
        target_module = target.split("/", 1)[0] if "/" in target else "external"
        if source_module and target_module and source_module != target_module:
            edges[(source_module, target_module)] += 1

    graph_edges: list[GraphEdge] = []
    for (source_module, target_module), weight in edges.items():
        graph_edges.append(
            GraphEdge(
                source=_repo_node_for_module(source_module),
                target=_repo_node_for_module(target_module),
                edge_type="module_depends_on",
                weight=float(weight),
            )
        )
    return RepositoryGraph(
        graph_id=f"graph-module-{uuid.uuid4().hex[:8]}",
        graph_type="module_dependency_graph",
        nodes=nodes,
        edges=graph_edges,
    )


def _build_build_target_graph(codebase_collection: dict[str, Any]) -> RepositoryGraph:
    targets = codebase_collection.get("build_targets", []) or []
    chunks = _code_chunk_objects(codebase_collection)
    file_chunks = [chunk for chunk in chunks if chunk.symbol_kind == "file"]
    nodes: list[dict[str, Any]] = []
    edges: list[GraphEdge] = []
    for target in targets:
        target_id = str(target.get("target_id", "target"))
        target_path = str(target.get("path", ""))
        target_languages = set(str(lang) for lang in (target.get("languages", []) or []))
        target_node = f"target:{target_id}"
        nodes.append({"id": target_node, "type": "build_target", "target_id": target_id, "path": target_path})
        for chunk in file_chunks:
            if target_languages and chunk.language not in target_languages and chunk.language != "unknown":
                continue
            edges.append(
                GraphEdge(
                    source=target_node,
                    target=_repo_node_for_file(chunk.repo_path),
                    edge_type="build_includes",
                    metadata={"language": chunk.language},
                )
            )
    return RepositoryGraph(
        graph_id=f"graph-target-{uuid.uuid4().hex[:8]}",
        graph_type="build_target_graph",
        nodes=nodes,
        edges=edges,
    )


def _build_service_dataflow_graph(codebase_collection: dict[str, Any]) -> RepositoryGraph:
    contracts = codebase_collection.get("interface_contracts", []) or []
    chunks = _code_chunk_objects(codebase_collection)
    file_chunks = [chunk for chunk in chunks if chunk.symbol_kind == "file"]
    nodes: list[dict[str, Any]] = []
    edges: list[GraphEdge] = []
    contract_entities: dict[str, list[str]] = {}

    for contract in contracts:
        cid = str(contract.get("contract_id", ""))
        node_id = f"contract:{cid}"
        entities = [str(entity) for entity in (contract.get("entities", []) or [])]
        contract_entities[node_id] = entities
        nodes.append({"id": node_id, "type": "contract", "contract_type": contract.get("contract_type", ""), "repo_path": contract.get("repo_path", "")})

    for chunk in file_chunks:
        file_node = _repo_node_for_file(chunk.repo_path)
        nodes.append({"id": file_node, "type": "file", "repo_path": chunk.repo_path})
        for contract_node, entities in contract_entities.items():
            mention_count = sum(1 for entity in entities if entity and entity in chunk.content)
            if mention_count <= 0:
                continue
            edges.append(GraphEdge(source=file_node, target=contract_node, edge_type="uses_contract", weight=float(mention_count)))

    return RepositoryGraph(
        graph_id=f"graph-dataflow-{uuid.uuid4().hex[:8]}",
        graph_type="service_dataflow_graph",
        nodes=_dedupe_nodes(nodes),
        edges=edges,
    )


def build_repository_graphs(codebase_collection: dict[str, Any]) -> dict[str, Any]:
    import_graph = _build_import_graph(codebase_collection)
    symbol_graph = _build_symbol_reference_graph(codebase_collection)
    module_graph = _build_module_dependency_graph(codebase_collection)
    target_graph = _build_build_target_graph(codebase_collection)
    dataflow_graph = _build_service_dataflow_graph(codebase_collection)

    bundle = RepositoryGraphBundle(
        import_graph=import_graph,
        symbol_reference_graph=symbol_graph,
        module_dependency_graph=module_graph,
        build_target_graph=target_graph,
        service_dataflow_graph=dataflow_graph,
        adjacency={},
    )
    adjacency: dict[str, set[str]] = defaultdict(set)
    for graph in [import_graph, symbol_graph, module_graph, target_graph, dataflow_graph]:
        for edge in graph.edges:
            adjacency[edge.source].add(edge.target)
            adjacency[edge.target].add(edge.source)
    bundle.adjacency = dict(adjacency)
    return bundle.to_dict() | {"adjacency": {k: sorted(v) for k, v in bundle.adjacency.items()}}


def _extract_goal_statements(chunks: list[PaperChunk], limit: int = 4) -> list[str]:
    focus_keywords = ("abstract", "introduction", "conclusion", "summary", "motivation", "specification")
    selected: list[str] = []
    for chunk in chunks:
        heading = chunk.headings_info.lower()
        if chunk.type != "text":
            continue
        if not any(keyword in heading for keyword in focus_keywords):
            continue
        for sentence in _sentence_split(chunk.content):
            if len(sentence.split()) < 6:
                continue
            selected.append(sentence)
            if len(selected) >= limit:
                return selected
    return selected


def _select_toc_scopes(toc_paths: list[str], keywords: list[str], fallback: int = 3) -> list[str]:
    if not toc_paths:
        return ["Document"]
    lower_keywords = [kw.lower() for kw in keywords if kw.strip()]
    matched = [path for path in toc_paths if any(kw in path.lower() for kw in lower_keywords)]
    if matched:
        return _dedupe_preserve_order(matched)[:8]
    return toc_paths[:fallback]


def _build_question_id(index: int) -> str:
    return f"Q-{index:04d}"


def planning_plane(
    collection: dict[str, Any],
    max_questions: int = 20,
    codebase_collection: dict[str, Any] | None = None,
    allowed_edit_paths: list[str] | None = None,
    forbidden_paths: list[str] | None = None,
    target_languages: list[str] | None = None,
) -> dict[str, Any]:
    chunks = _chunk_objects(collection)
    toc_paths = collection.get("toc_paths", []) or ["Document"]
    goals = _extract_goal_statements(chunks)
    if not goals:
        goals = ["Map specification requirements to repository implementation with explicit traceability."]

    codebase_collection = codebase_collection or {}
    modules = codebase_collection.get("modules", []) or []
    build_targets = codebase_collection.get("build_targets", []) or []
    interfaces = codebase_collection.get("interface_contracts", []) or []
    inferred_languages = sorted({str(chunk.get("language", "")) for chunk in codebase_collection.get("chunks", []) if chunk.get("language") in TARGET_CODE_LANGUAGES})
    planner_languages = target_languages or inferred_languages or ["python"]

    allowed = allowed_edit_paths or []
    forbidden = forbidden_paths or []
    plans: list[PlanQuestion] = []
    q_index = 1

    top_repo_paths = [str(module.get("path_prefix") or module.get("module_id") or "") for module in modules[:8]]
    top_repo_paths = [path for path in _dedupe_preserve_order(top_repo_paths) if path]
    build_target_ids = [str(target.get("target_id", "")) for target in build_targets][:8]

    root = PlanQuestion(
        question_id=_build_question_id(q_index),
        question_depth=0,
        question=(
            "What are the top-level architecture requirements from the paper/spec, and where are the owning "
            "subsystems in the repository? Which build targets and interfaces constrain changes?"
        ),
        question_type="structure",
        paper_scopes=_select_toc_scopes(toc_paths, ["overview", "method", "architecture", "system", "specification"], fallback=4),
        repo_paths=top_repo_paths,
        target_languages=planner_languages,
        target_symbols=[],
        build_targets=build_target_ids,
        subsystem_id="repository",
        allowed_edit_paths=allowed,
        forbidden_paths=forbidden,
        goal_alignment=goals[:3],
        expected_output_type="architecture_mapping",
        priority="high",
        module_id="framework",
    )
    root.toc_page_indexes = list(root.paper_scopes)
    plans.append(root)
    q_index += 1

    for module in modules[: max(1, min(8, max_questions // 2))]:
        if len(plans) >= max_questions:
            break
        module_id = str(module.get("module_id", "subsystem"))
        path_prefix = str(module.get("path_prefix", "")) or module_id
        module_langs = [str(lang) for lang in (module.get("languages", []) or []) if lang]
        question = PlanQuestion(
            question_id=_build_question_id(q_index),
            question_depth=1,
            question=(
                f"Where is `{module_id}` implemented, which symbols and files are affected, and what paper/spec "
                "requirements map to this subsystem?"
            ),
            question_type="subsystem_mapping",
            paper_scopes=_select_toc_scopes(toc_paths, [module_id, "module", "component", "pipeline"], fallback=3),
            repo_paths=[path_prefix],
            target_languages=module_langs or planner_languages,
            target_symbols=[],
            build_targets=build_target_ids,
            subsystem_id=module_id,
            allowed_edit_paths=allowed,
            forbidden_paths=forbidden,
            goal_alignment=goals[:2],
            expected_output_type="subsystem_mapping",
            priority="high",
            parent_question_id=root.question_id,
            module_id=_to_slug(module_id),
        )
        question.toc_page_indexes = list(question.paper_scopes)
        plans.append(question)
        q_index += 1

    if interfaces and len(plans) < max_questions:
        contract_paths = [str(contract.get("repo_path", "")) for contract in interfaces[:8] if contract.get("repo_path")]
        interface_question = PlanQuestion(
            question_id=_build_question_id(q_index),
            question_depth=1,
            question=(
                "Which cross-language contracts (protobuf/REST/gRPC/schema/DB/event/FFI) constrain implementation, "
                "and which modules consume or produce each contract?"
            ),
            question_type="interface_contract",
            paper_scopes=_select_toc_scopes(toc_paths, ["interface", "api", "data", "protocol", "schema"], fallback=3),
            repo_paths=_dedupe_preserve_order(contract_paths),
            target_languages=planner_languages,
            target_symbols=[],
            build_targets=build_target_ids,
            subsystem_id="interfaces",
            allowed_edit_paths=allowed,
            forbidden_paths=forbidden,
            goal_alignment=goals[:2],
            expected_output_type="interface_matrix",
            priority="high",
            parent_question_id=root.question_id,
            module_id="interface_contracts",
        )
        interface_question.toc_page_indexes = list(interface_question.paper_scopes)
        plans.append(interface_question)
        q_index += 1

    if build_targets and len(plans) < max_questions:
        build_question = PlanQuestion(
            question_id=_build_question_id(q_index),
            question_depth=1,
            question=(
                "Which build targets, tests, and static checks validate this feature, and what is the minimum "
                "bounded edit plan to keep buildability and interfaces consistent?"
            ),
            question_type="build_constraints",
            paper_scopes=_select_toc_scopes(toc_paths, ["evaluation", "experiment", "deployment", "implementation"], fallback=3),
            repo_paths=top_repo_paths,
            target_languages=planner_languages,
            target_symbols=[],
            build_targets=build_target_ids,
            subsystem_id="build_validation",
            allowed_edit_paths=allowed,
            forbidden_paths=forbidden,
            goal_alignment=goals[:2],
            expected_output_type="validation_plan",
            priority="medium",
            parent_question_id=root.question_id,
            module_id="build_validation",
        )
        build_question.toc_page_indexes = list(build_question.paper_scopes)
        plans.append(build_question)
        q_index += 1

    conditional_templates = [
        ("algorithm", ["algorithm", "objective", "equation", "procedure"], "What algorithmic steps and symbol-level changes are required for faithful implementation?"),
        ("data_flow", ["pipeline", "flow", "state", "interaction"], "How does data and control move across repository components and service boundaries?"),
        ("edge_case", ["limitation", "error", "robust"], "Which failure paths or edge cases need code-level handling across languages and interfaces?"),
        ("evaluation_protocol", ["evaluation", "metrics", "benchmark"], "What executable validation criteria must pass to accept the implementation?"),
    ]
    for qtype, keywords, prompt in conditional_templates:
        if len(plans) >= max_questions:
            break
        question = PlanQuestion(
            question_id=_build_question_id(q_index),
            question_depth=2,
            question=prompt,
            question_type=qtype,
            paper_scopes=_select_toc_scopes(toc_paths, keywords, fallback=3),
            repo_paths=top_repo_paths,
            target_languages=planner_languages,
            target_symbols=[],
            build_targets=build_target_ids,
            subsystem_id=qtype,
            allowed_edit_paths=allowed,
            forbidden_paths=forbidden,
            goal_alignment=goals[:3],
            expected_output_type="implementation_brief",
            priority=_priority_label(qtype),
            parent_question_id=root.question_id,
            module_id=qtype,
        )
        question.toc_page_indexes = list(question.paper_scopes)
        plans.append(question)
        q_index += 1

    return {
        "plan": [item.to_dict() for item in plans],
        "goals": goals,
        "planner_notes": {
            "strategy": "dual_grounded_progressive_decomposition",
            "working_set_narrowing": ["repository_map", "subsystem_map", "candidate_file_set", "candidate_symbol_set", "bounded_edit_set"],
            "supports_partial_capabilities": True,
            "paper_collection_id": collection.get("collection_id", ""),
            "repo_collection_id": codebase_collection.get("collection_id", ""),
        },
    }


def retrieve_paper_evidence(collection: dict[str, Any], question: str, paper_scopes: list[str] | None = None, top_k: int = 6) -> list[dict[str, Any]]:
    chunks = _chunk_objects(collection)
    question_tokens = Counter(_tokenize(question))
    if not question_tokens:
        return []
    scope_values = [scope.lower() for scope in (paper_scopes or []) if scope.strip()]
    scored: list[tuple[float, PaperChunk]] = []
    for chunk in chunks:
        if chunk.type == "toc":
            continue
        heading = chunk.headings_info.lower()
        scope_match = not scope_values or any(scope in heading for scope in scope_values)
        if not scope_match:
            continue
        chunk_tokens = Counter(_tokenize(f"{chunk.headings_info} {chunk.content}"))
        overlap = sum(min(chunk_tokens[token], count) for token, count in question_tokens.items())
        if overlap <= 0:
            continue
        score = float(overlap) + (1.0 if scope_values else 0.0) + (0.3 if chunk.type in {"image", "table"} else 0.0)
        score += min(len(chunk.content) / 1200.0, 0.8)
        scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    output: list[dict[str, Any]] = []
    for score, chunk in scored[:top_k]:
        output.append(
            {
                "chunk_id": chunk.chunk_id,
                "evidence_type": "paper",
                "type": chunk.type,
                "headings_info": chunk.headings_info,
                "content": chunk.content,
                "metadata": chunk.metadata,
                "score": round(score, 5),
            }
        )
    return output


def _graph_expand_nodes(adjacency: dict[str, list[str]], seeds: list[str], max_hops: int = 1, max_nodes: int = 200) -> dict[str, int]:
    if max_hops <= 0:
        return {}
    distances: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()
    for seed in seeds:
        queue.append((seed, 0))
        distances[seed] = 0
    while queue and len(distances) < max_nodes:
        node, dist = queue.popleft()
        if dist >= max_hops:
            continue
        for neighbor in adjacency.get(node, []) or []:
            if neighbor in distances:
                continue
            distances[neighbor] = dist + 1
            queue.append((neighbor, dist + 1))
            if len(distances) >= max_nodes:
                break
    return distances


def retrieve_code_evidence(
    codebase_collection: dict[str, Any],
    repository_graphs: dict[str, Any] | None,
    question: str,
    repo_paths: list[str] | None = None,
    target_languages: list[str] | None = None,
    target_symbols: list[str] | None = None,
    build_targets: list[str] | None = None,
    subsystem_id: str | None = None,
    top_k: int = 10,
    graph_expand_hops: int = 1,
) -> list[dict[str, Any]]:
    chunks = _code_chunk_objects(codebase_collection)
    if not chunks:
        return []
    question_tokens = Counter(_tokenize(question))
    if not question_tokens:
        return []
    repo_paths = [path for path in (repo_paths or []) if path]
    target_languages = [_normalize_language(lang) for lang in (target_languages or []) if lang]
    target_symbols = [symbol.lower() for symbol in (target_symbols or []) if symbol]
    adjacency = (repository_graphs or {}).get("adjacency", {}) or {}

    scored: list[tuple[float, CodeChunk]] = []
    for chunk in chunks:
        if repo_paths and not _matches_any_prefix(chunk.repo_path, repo_paths):
            continue
        if target_languages and chunk.language not in target_languages and chunk.language != "unknown":
            continue
        if target_symbols and chunk.symbol_name and chunk.symbol_name.lower() not in target_symbols:
            content_tokens = set(_tokenize(chunk.signature + " " + chunk.content[:500]))
            if not any(symbol in content_tokens for symbol in target_symbols):
                continue
        text = f"{chunk.repo_path} {chunk.symbol_name} {chunk.signature} {chunk.content[:2200]}"
        tokens = Counter(_tokenize(text))
        overlap = sum(min(tokens[token], count) for token, count in question_tokens.items())
        if overlap <= 0:
            continue
        score = float(overlap)
        if chunk.symbol_kind in {"function", "method", "class", "interface", "struct", "trait"}:
            score += 1.2
        if target_languages and chunk.language in target_languages:
            score += 1.0
        if target_symbols and chunk.symbol_name.lower() in target_symbols:
            score += 1.8
        if subsystem_id and subsystem_id.lower() in chunk.repo_path.lower():
            score += 0.8
        if build_targets and any(str(target) in chunk.repo_path for target in build_targets):
            score += 0.5
        score += min(len(chunk.content) / 1500.0, 0.6)
        scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)

    seed_items = scored[: max(top_k * 3, 24)]
    output: dict[str, dict[str, Any]] = {}
    seed_nodes: list[str] = []
    chunks_by_file: dict[str, list[CodeChunk]] = defaultdict(list)
    chunks_by_symbol: dict[str, list[CodeChunk]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_file[chunk.repo_path].append(chunk)
        if chunk.symbol_name:
            chunks_by_symbol[chunk.symbol_name.lower()].append(chunk)

    for score, chunk in seed_items:
        output[chunk.chunk_id] = {
            "chunk_id": chunk.chunk_id,
            "evidence_type": "code",
            "repo_path": chunk.repo_path,
            "language": chunk.language,
            "symbol_kind": chunk.symbol_kind,
            "symbol_name": chunk.symbol_name,
            "signature": chunk.signature,
            "content": chunk.content,
            "metadata": chunk.metadata,
            "score": round(score, 5),
            "retrieval_reason": "lexical_seed",
            "graph_distance": 0,
        }
        seed_nodes.append(_repo_node_for_file(chunk.repo_path))
        if chunk.symbol_name:
            seed_nodes.append(_repo_node_for_symbol(chunk.repo_path, chunk.symbol_name))

    expanded = _graph_expand_nodes(adjacency=adjacency, seeds=seed_nodes, max_hops=graph_expand_hops, max_nodes=max(top_k * 30, 120))
    for node_id, distance in expanded.items():
        if distance <= 0:
            continue
        candidates: list[CodeChunk] = []
        if node_id.startswith("file:"):
            candidates = chunks_by_file.get(node_id.removeprefix("file:"), [])
        elif node_id.startswith("symbol:"):
            candidates = chunks_by_symbol.get(node_id.split(":")[-1].lower(), [])
        for chunk in candidates[:10]:
            if chunk.chunk_id in output:
                continue
            base = 0.7 / float(distance + 1)
            output[chunk.chunk_id] = {
                "chunk_id": chunk.chunk_id,
                "evidence_type": "code",
                "repo_path": chunk.repo_path,
                "language": chunk.language,
                "symbol_kind": chunk.symbol_kind,
                "symbol_name": chunk.symbol_name,
                "signature": chunk.signature,
                "content": chunk.content,
                "metadata": chunk.metadata,
                "score": round(base, 5),
                "retrieval_reason": "graph_neighbor",
                "graph_distance": distance,
            }
    items = sorted(output.values(), key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return items[:top_k]


def merge_evidence(
    question: str,
    paper_evidence: list[dict[str, Any]],
    code_evidence: list[dict[str, Any]],
    target_symbols: list[str] | None = None,
    target_languages: list[str] | None = None,
) -> dict[str, Any]:
    paper_sentences: list[str] = []
    for item in paper_evidence[:8]:
        paper_sentences.extend(_sentence_split(str(item.get("content", "")))[:2])
    paper_supported_facts = _dedupe_preserve_order([sentence for sentence in paper_sentences if len(sentence.split()) >= 5])[:12]

    code_supported_facts: list[str] = []
    for item in code_evidence[:12]:
        signature = str(item.get("signature", "")).strip()
        path = str(item.get("repo_path", "")).strip()
        symbol = str(item.get("symbol_name", "")).strip()
        if signature:
            code_supported_facts.append(f"{path}: {signature}")
        elif symbol:
            code_supported_facts.append(f"{path}: {symbol}")
        else:
            code_supported_facts.append(path)
    code_supported_facts = _dedupe_preserve_order(code_supported_facts)

    conflicts: list[dict[str, Any]] = []
    unresolved_gaps: list[str] = []
    inferred_assumptions: list[str] = []
    if not paper_supported_facts:
        unresolved_gaps.append("No direct paper/spec facts retrieved for this question.")
        inferred_assumptions.append("Proceeding from repository evidence only.")
    if not code_supported_facts:
        unresolved_gaps.append("No repository evidence retrieved for this question.")
        inferred_assumptions.append("Implementation location must be inferred from architecture context.")

    code_text = " ".join(code_supported_facts).lower()
    for fact in paper_supported_facts[:10]:
        tokens = set(_tokenize(fact))
        if not tokens:
            continue
        overlap = len(tokens & set(_tokenize(code_text))) / max(len(tokens), 1)
        if overlap < 0.1:
            conflicts.append(
                {
                    "paper_fact": fact,
                    "code_evidence": "No strong lexical alignment in retrieved code evidence.",
                    "type": "paper_repo_alignment_gap",
                }
            )

    expected_symbols = [symbol.lower() for symbol in (target_symbols or []) if symbol]
    if expected_symbols:
        seen_symbols = {str(item.get("symbol_name", "")).lower() for item in code_evidence if item.get("symbol_name")}
        missing_symbols = [symbol for symbol in expected_symbols if symbol not in seen_symbols]
        if missing_symbols:
            unresolved_gaps.append(f"Target symbols not found in code evidence: {', '.join(missing_symbols[:10])}")

    expected_languages = {_normalize_language(lang) for lang in (target_languages or []) if lang}
    if expected_languages:
        seen_languages = {_normalize_language(str(item.get("language", ""))) for item in code_evidence if item.get("language")}
        if seen_languages and not (expected_languages & seen_languages):
            conflicts.append(
                {
                    "paper_fact": f"Expected languages: {', '.join(sorted(expected_languages))}",
                    "code_evidence": f"Retrieved languages: {', '.join(sorted(seen_languages))}",
                    "type": "language_constraint_mismatch",
                }
            )

    return {
        "question": question,
        "paper_supported_facts": paper_supported_facts,
        "codebase_supported_facts": code_supported_facts,
        "conflicts_between_paper_and_repo": conflicts,
        "unresolved_implementation_gaps": _dedupe_preserve_order(unresolved_gaps),
        "inferred_assumptions": _dedupe_preserve_order(inferred_assumptions),
        "confidence": round(max(0.1, min(0.95, 0.4 + 0.05 * len(paper_supported_facts) + 0.04 * len(code_supported_facts) - 0.08 * len(conflicts))), 3),
    }


def retrieve_chunks_for_question(
    collection: dict[str, Any],
    question: str,
    toc_page_indexes: list[str] | None = None,
    top_k: int = 6,
) -> list[dict[str, Any]]:
    return retrieve_paper_evidence(collection=collection, question=question, paper_scopes=toc_page_indexes, top_k=top_k)


def build_hierarchical_working_set(
    plan_item: dict[str, Any],
    codebase_collection: dict[str, Any],
    repository_graphs: dict[str, Any] | None,
    code_evidence: list[dict[str, Any]] | None = None,
    file_budget: int = 80,
    symbol_budget: int = 200,
) -> WorkingSet:
    modules = codebase_collection.get("modules", []) or []
    repository_map = [str(module.get("module_id", "root")) for module in modules]
    subsystem_id = str(plan_item.get("subsystem_id", "")).strip() or "repository"
    repo_paths = [str(path) for path in (plan_item.get("repo_paths", []) or []) if path]
    target_symbols = [str(symbol) for symbol in (plan_item.get("target_symbols", []) or []) if symbol]
    allowed = [str(path) for path in (plan_item.get("allowed_edit_paths", []) or []) if path]
    forbidden = [str(path) for path in (plan_item.get("forbidden_paths", []) or []) if path]

    chunk_objects = _code_chunk_objects(codebase_collection)
    candidate_files: list[str] = []
    for chunk in chunk_objects:
        if chunk.symbol_kind != "file":
            continue
        if repo_paths and not _matches_any_prefix(chunk.repo_path, repo_paths):
            continue
        if subsystem_id not in {"repository", "interfaces", "build_validation"} and subsystem_id not in chunk.repo_path:
            if repo_paths:
                continue
        candidate_files.append(chunk.repo_path)

    for evidence in code_evidence or []:
        path = str(evidence.get("repo_path", "")).strip()
        if path:
            candidate_files.append(path)
    candidate_files = _dedupe_preserve_order(candidate_files)[:file_budget]

    candidate_symbols: list[str] = list(target_symbols)
    for evidence in code_evidence or []:
        symbol = str(evidence.get("symbol_name", "")).strip()
        if symbol:
            candidate_symbols.append(symbol)
    candidate_symbols = _dedupe_preserve_order(candidate_symbols)[:symbol_budget]

    bounded = [path for path in candidate_files if _matches_any_prefix(path, allowed)] if allowed else list(candidate_files)
    if forbidden:
        bounded = [path for path in bounded if not _matches_any_prefix(path, forbidden)]
    if not bounded:
        bounded = candidate_files[: max(1, min(20, len(candidate_files)))]

    subsystem_map = {
        "subsystem_id": subsystem_id,
        "repo_paths": repo_paths,
        "module_candidates": [
            module for module in modules
            if subsystem_id in {"repository", "interfaces", "build_validation"} or subsystem_id in str(module.get("module_id", ""))
        ][:12],
        "graph_neighbors_count": len((repository_graphs or {}).get("adjacency", {}) or {}),
    }
    return WorkingSet(
        repository_map=_dedupe_preserve_order(repository_map),
        subsystem_map=subsystem_map,
        candidate_file_set=candidate_files,
        candidate_symbol_set=candidate_symbols,
        bounded_edit_set=bounded,
        metadata={"file_budget": file_budget, "symbol_budget": symbol_budget},
    )


def comprehension_and_design_plane(
    plan_item: dict[str, Any],
    retrieved_chunks: list[dict[str, Any]],
    code_evidence: list[dict[str, Any]] | None = None,
    merged_evidence: dict[str, Any] | None = None,
    working_set: WorkingSet | None = None,
    previous_state: dict[str, Any] | None = None,
) -> DesignAnswer:
    question_id = str(plan_item.get("question_id", "Q-0000"))
    question = str(plan_item.get("question", "")).strip()
    question_type = str(plan_item.get("question_type", "structure")).strip()
    module_name = str(plan_item.get("subsystem_id") or plan_item.get("module_id") or question_type or "module")
    code_evidence = code_evidence or []
    merged = merged_evidence or merge_evidence(
        question=question,
        paper_evidence=retrieved_chunks,
        code_evidence=code_evidence,
        target_symbols=list(plan_item.get("target_symbols", []) or []),
        target_languages=list(plan_item.get("target_languages", []) or []),
    )
    paper_facts = merged.get("paper_supported_facts", []) or []
    code_facts = merged.get("codebase_supported_facts", []) or []
    conflicts = merged.get("conflicts_between_paper_and_repo", []) or []
    unresolved = merged.get("unresolved_implementation_gaps", []) or []
    inferred = merged.get("inferred_assumptions", []) or []

    target_languages = [_normalize_language(str(lang)) for lang in (plan_item.get("target_languages", []) or [])]
    target_languages = [lang for lang in target_languages if lang]
    if not target_languages:
        target_languages = [_normalize_language(str(item.get("language", ""))) for item in code_evidence if item.get("language")]
    target_languages = _dedupe_preserve_order([lang for lang in target_languages if lang]) or ["python"]

    citations: list[dict[str, Any]] = []
    for chunk in retrieved_chunks[:8]:
        citations.append({"chunk_id": chunk.get("chunk_id", ""), "source_type": "paper", "headings_info": chunk.get("headings_info", ""), "score": chunk.get("score", 0.0)})
    for chunk in code_evidence[:8]:
        citations.append({"chunk_id": chunk.get("chunk_id", ""), "source_type": "code", "repo_path": chunk.get("repo_path", ""), "symbol_name": chunk.get("symbol_name", ""), "score": chunk.get("score", 0.0)})

    bounded_context = {
        "subsystem_id": plan_item.get("subsystem_id", ""),
        "repo_paths": plan_item.get("repo_paths", []) or [],
        "target_symbols": plan_item.get("target_symbols", []) or [],
        "target_languages": target_languages,
        "build_targets": plan_item.get("build_targets", []) or [],
        "allowed_edit_paths": plan_item.get("allowed_edit_paths", []) or [],
        "forbidden_paths": plan_item.get("forbidden_paths", []) or [],
        "working_set": working_set.to_dict() if working_set else {},
    }

    implementation_recommendations = [
        "Map each paper/spec fact to one owning symbol and one validation check.",
        "Edit only files inside bounded_edit_set unless refinement explicitly expands scope.",
        "Update interface/schema/build files together with code when contracts are touched.",
    ]
    if conflicts:
        implementation_recommendations.append("Resolve paper-vs-repo conflicts before code generation.")
    if previous_state and previous_state.get("failed_assertions"):
        implementation_recommendations.append("Prioritize unresolved validation failures from prior iteration.")

    brief = {
        "objective": f"Implement `{module_name}` for: {question}",
        "question_type": question_type,
        "module_name": module_name,
        "paper_supported_facts": paper_facts,
        "codebase_supported_facts": code_facts,
        "conflicts_between_paper_and_repo": conflicts,
        "unresolved_implementation_gaps": unresolved,
        "inferred_assumptions": inferred,
        "explicit_support": paper_facts[:8],
        "inferred_points": inferred[:8],
        "underspecified_points": unresolved[:8],
        "target_languages": target_languages,
        "target_symbols": plan_item.get("target_symbols", []) or [],
        "build_targets": plan_item.get("build_targets", []) or [],
        "bounded_context": bounded_context,
        "implementation_recommendations": implementation_recommendations,
        "citations": citations,
        "confidence": merged.get("confidence", 0.5),
    }
    return DesignAnswer(
        question_id=question_id,
        implementation_brief=brief,
        citations=citations,
        retrieved_chunks=retrieved_chunks,
        paper_evidence=retrieved_chunks,
        code_evidence=code_evidence,
        merged_evidence=merged,
    )


class CodeExecutionAdapter(ABC):
    adapter_id: str = "base_project_adapter"
    language: str = "generic"
    file_extension: str = ".txt"
    is_fallback: bool = False
    confidence_level: str = "high"

    def supports(self, target_language: str) -> bool:
        return _normalize_language(target_language) == self.language

    def locate_edit_points(
        self,
        brief: dict[str, Any],
        codebase_collection: dict[str, Any] | None,
        working_set: WorkingSet | None,
    ) -> list[str]:
        codebase_collection = codebase_collection or {}
        if working_set and working_set.bounded_edit_set:
            candidates = [path for path in working_set.bounded_edit_set if path.endswith(self.file_extension)]
            if candidates:
                return candidates[:8]
        chunks = _code_chunk_objects(codebase_collection)
        paths = [chunk.repo_path for chunk in chunks if chunk.symbol_kind == "file" and chunk.language == self.language]
        return _dedupe_preserve_order(paths)[:8]

    @abstractmethod
    def render(self, brief: dict[str, Any], question_id: str, module_slug: str, edit_points: list[str]) -> str:
        raise NotImplementedError

    def generate_tests(self, module_slug: str) -> list[str]:
        return []

    def update_build_hints(self) -> list[str]:
        return []

    def validation_hooks(self) -> list[str]:
        return []


class PythonProjectAdapter(CodeExecutionAdapter):
    adapter_id = "python_project_adapter"
    language = "python"
    file_extension = ".py"

    def render(self, brief: dict[str, Any], question_id: str, module_slug: str, edit_points: list[str]) -> str:
        facts = brief.get("paper_supported_facts", []) or []
        code_facts = brief.get("codebase_supported_facts", []) or []
        unresolved = brief.get("unresolved_implementation_gaps", []) or []
        return (
            "from __future__ import annotations\n\n"
            "from typing import Any\n\n"
            f"\"\"\"Dual-grounded scaffold for {question_id} ({module_slug}).\"\"\"\n\n"
            f"class {module_slug.title().replace('_', '')}Module:\n"
            "    def __init__(self, config: dict[str, Any]) -> None:\n"
            "        self.config = config\n\n"
            "    def run(self, inputs: dict[str, Any]) -> dict[str, Any]:\n"
            "        # Paper/spec facts:\n"
            + "\n".join([f"        # - {fact}" for fact in facts[:6]])
            + "\n        # Repository evidence:\n"
            + "\n".join([f"        # - {fact}" for fact in code_facts[:6]])
            + "\n        # Unresolved gaps:\n"
            + ("\n".join([f"        # - {gap}" for gap in unresolved[:6]]) if unresolved else "        # - none")
            + "\n        return {\"status\": \"scaffold\", \"inputs\": inputs}\n\n"
            f"def build_{module_slug}(config: dict[str, Any]) -> {module_slug.title().replace('_', '')}Module:\n"
            f"    return {module_slug.title().replace('_', '')}Module(config)\n"
            f"\n# Candidate edit points: {', '.join(edit_points) if edit_points else 'none'}\n"
        )

    def generate_tests(self, module_slug: str) -> list[str]:
        return [f"tests/test_{module_slug}.py"]

    def update_build_hints(self) -> list[str]:
        return ["python -m pytest -q"]

    def validation_hooks(self) -> list[str]:
        return ["python -m py_compile", "python -m pytest -q"]


class TypeScriptProjectAdapter(CodeExecutionAdapter):
    adapter_id = "typescript_project_adapter"
    language = "typescript"
    file_extension = ".ts"

    def render(self, brief: dict[str, Any], question_id: str, module_slug: str, edit_points: list[str]) -> str:
        name = module_slug.title().replace("_", "")
        return (
            f"// Dual-grounded scaffold for {question_id}\n"
            f"// Module: {module_slug}\n"
            f"// Candidate edit points: {', '.join(edit_points) if edit_points else 'none'}\n\n"
            f"export type {name}Config = Record<string, unknown>;\n\n"
            f"export function build{name}(config: {name}Config) {{\n"
            "  return {\n"
            "    status: 'scaffold',\n"
            "    config,\n"
            "  };\n"
            "}\n"
        )

    def generate_tests(self, module_slug: str) -> list[str]:
        return [f"tests/{module_slug}.test.ts"]

    def update_build_hints(self) -> list[str]:
        return ["npm run typecheck --if-present", "npm run test --if-present"]

    def validation_hooks(self) -> list[str]:
        return ["npm run build --if-present", "npm run test --if-present"]


class JavaProjectAdapter(CodeExecutionAdapter):
    adapter_id = "java_project_adapter"
    language = "java"
    file_extension = ".java"

    def render(self, brief: dict[str, Any], question_id: str, module_slug: str, edit_points: list[str]) -> str:
        class_name = module_slug.title().replace("_", "") + "Module"
        return (
            f"// Dual-grounded scaffold for {question_id}\n"
            f"public class {class_name} {{\n"
            "    public java.util.Map<String, Object> run(java.util.Map<String, Object> input) {\n"
            "        return java.util.Map.of(\"status\", \"scaffold\", \"input\", input);\n"
            "    }\n"
            "}\n"
        )

    def generate_tests(self, module_slug: str) -> list[str]:
        return [f"src/test/java/{module_slug.title().replace('_', '')}ModuleTest.java"]

    def update_build_hints(self) -> list[str]:
        return ["mvn -q test", "./gradlew test"]


class GoProjectAdapter(CodeExecutionAdapter):
    adapter_id = "go_project_adapter"
    language = "go"
    file_extension = ".go"

    def render(self, brief: dict[str, Any], question_id: str, module_slug: str, edit_points: list[str]) -> str:
        return (
            f"// Dual-grounded scaffold for {question_id}\n"
            "package main\n\n"
            "func Run(inputs map[string]any) map[string]any {\n"
            "    return map[string]any{\"status\": \"scaffold\", \"inputs\": inputs}\n"
            "}\n"
        )

    def generate_tests(self, module_slug: str) -> list[str]:
        return [f"{module_slug}_test.go"]

    def update_build_hints(self) -> list[str]:
        return ["go test ./...", "go build ./..."]


class RustProjectAdapter(CodeExecutionAdapter):
    adapter_id = "rust_project_adapter"
    language = "rust"
    file_extension = ".rs"

    def render(self, brief: dict[str, Any], question_id: str, module_slug: str, edit_points: list[str]) -> str:
        return (
            f"// Dual-grounded scaffold for {question_id}\n"
            "pub fn run(inputs: std::collections::HashMap<String, String>) -> std::collections::HashMap<String, String> {\n"
            "    let mut out = std::collections::HashMap::new();\n"
            "    out.insert(\"status\".to_string(), \"scaffold\".to_string());\n"
            "    out\n"
            "}\n"
        )

    def generate_tests(self, module_slug: str) -> list[str]:
        return [f"tests/{module_slug}_test.rs"]

    def update_build_hints(self) -> list[str]:
        return ["cargo check", "cargo test"]


class CppProjectAdapter(CodeExecutionAdapter):
    adapter_id = "cpp_project_adapter"
    language = "cpp"
    file_extension = ".cpp"

    def render(self, brief: dict[str, Any], question_id: str, module_slug: str, edit_points: list[str]) -> str:
        return (
            f"// Dual-grounded scaffold for {question_id}\n"
            "#include <string>\n#include <unordered_map>\n\n"
            "std::unordered_map<std::string, std::string> Run(const std::unordered_map<std::string, std::string>& inputs) {\n"
            "    return {{\"status\", \"scaffold\"}};\n"
            "}\n"
        )

    def generate_tests(self, module_slug: str) -> list[str]:
        return [f"tests/{module_slug}_test.cpp"]

    def update_build_hints(self) -> list[str]:
        return ["cmake --build .", "ctest"]


class GenericFallbackProjectAdapter(CodeExecutionAdapter):
    adapter_id = "generic_fallback_project_adapter"
    language = "generic"
    file_extension = ".txt"
    is_fallback = True
    confidence_level = "low"

    def supports(self, target_language: str) -> bool:
        return True

    def render(self, brief: dict[str, Any], question_id: str, module_slug: str, edit_points: list[str]) -> str:
        return (
            f"# Low-confidence fallback scaffold for {question_id}\n"
            f"# Module: {module_slug}\n"
            "# No language-specific backend available.\n"
            "# Implement manually using bounded context and traceability data.\n"
        )


class AdapterRegistry:
    def __init__(self, adapters: list[CodeExecutionAdapter] | None = None) -> None:
        self._adapters: list[CodeExecutionAdapter] = []
        for adapter in adapters or []:
            self.register(adapter)

    def register(self, adapter: CodeExecutionAdapter) -> None:
        self._adapters.append(adapter)

    def resolve(self, target_languages: list[str]) -> tuple[CodeExecutionAdapter, str]:
        normalized_targets = [_normalize_language(lang) for lang in target_languages if lang]
        fallback: CodeExecutionAdapter | None = None
        for adapter in self._adapters:
            if adapter.is_fallback:
                fallback = adapter
                continue
            for language in normalized_targets:
                if adapter.supports(language):
                    return adapter, language
        if fallback is None:
            raise RuntimeError("No fallback adapter configured.")
        return fallback, normalized_targets[0] if normalized_targets else "generic"


def _build_default_adapter_registry() -> AdapterRegistry:
    return AdapterRegistry(
        adapters=[
            PythonProjectAdapter(),
            TypeScriptProjectAdapter(),
            JavaProjectAdapter(),
            GoProjectAdapter(),
            RustProjectAdapter(),
            CppProjectAdapter(),
            GenericFallbackProjectAdapter(),
        ]
    )


_DEFAULT_ADAPTER_REGISTRY = _build_default_adapter_registry()


def code_agent_execution_plane(
    design_answer: DesignAnswer,
    output_dir: str | None = None,
    write_artifacts: bool = False,
    codebase_collection: dict[str, Any] | None = None,
    working_set: WorkingSet | None = None,
    adapter_registry: AdapterRegistry | None = None,
    preferred_language: str | None = None,
) -> CodeArtifact:
    brief = design_answer.implementation_brief
    question_id = design_answer.question_id
    module_slug = _to_slug(str(brief.get("module_name", "module")))
    target_languages = list(brief.get("target_languages", []) or [])
    if preferred_language:
        target_languages = [preferred_language, *target_languages]
    if not target_languages:
        target_languages = ["python"]

    registry = adapter_registry or _DEFAULT_ADAPTER_REGISTRY
    adapter, target_language = registry.resolve(target_languages)
    edit_points = adapter.locate_edit_points(brief, codebase_collection, working_set)
    generated_code = adapter.render(brief, question_id, module_slug, edit_points)
    filename = f"{question_id.lower()}_{module_slug}{adapter.file_extension}"

    execution_logs: list[str] = []
    files_changed: list[str] = []
    implementation_notes = list(brief.get("implementation_recommendations", []) or [])
    implementation_notes.extend([f"Validation hint: {hint}" for hint in adapter.update_build_hints()])

    if write_artifacts:
        target_dir = Path(output_dir or Path(__file__).resolve().parent / "generated")
        target_dir.mkdir(parents=True, exist_ok=True)
        source_path = target_dir / filename
        source_path.write_text(generated_code, encoding="utf-8")
        files_changed.append(str(source_path))
        plan_path = target_dir / f"{question_id.lower()}_{module_slug}.plan.json"
        plan_payload = {
            "question_id": question_id,
            "module_slug": module_slug,
            "target_language": target_language,
            "adapter_id": adapter.adapter_id,
            "edit_points": edit_points,
            "working_set": working_set.to_dict() if working_set else {},
            "traceability": brief.get("citations", []),
        }
        plan_path.write_text(json.dumps(plan_payload, ensure_ascii=True, indent=2), encoding="utf-8")
        files_changed.append(str(plan_path))
        execution_logs.append(f"Wrote scaffold and plan under {target_dir}")
    else:
        files_changed = edit_points[:8] if edit_points else [filename]
        execution_logs.append("Dry-run mode: scaffold generated in memory only.")

    summary = (
        f"Generated dual-grounded {target_language} scaffold for {question_id} using {adapter.adapter_id}; "
        f"bounded files={len(files_changed)}, conflicts={len(brief.get('conflicts_between_paper_and_repo', []))}, "
        f"gaps={len(brief.get('unresolved_implementation_gaps', []))}."
    )
    traceability = {
        "question_id": question_id,
        "language": target_language,
        "adapter_id": adapter.adapter_id,
        "adapter_confidence": adapter.confidence_level,
        "paper_citations": [item for item in design_answer.citations if item.get("source_type") == "paper"],
        "code_citations": [item for item in design_answer.citations if item.get("source_type") == "code"],
        "matched_part": brief.get("paper_supported_facts", []),
        "missing_part": brief.get("unresolved_implementation_gaps", []),
        "inferred_part": brief.get("inferred_assumptions", []),
        "implementation_locations": files_changed,
        "bounded_edit_set": working_set.bounded_edit_set if working_set else [],
        "proposed_tests": adapter.generate_tests(module_slug),
        "validation_hooks": adapter.validation_hooks(),
    }
    return CodeArtifact(
        artifact_id=f"artifact-{uuid.uuid4().hex[:10]}",
        question_id=question_id,
        files_changed=files_changed,
        summary=summary,
        traceability=traceability,
        execution_logs=execution_logs,
        implementation_notes=implementation_notes,
        generated_code=generated_code,
        language=target_language,
        adapter_id=adapter.adapter_id,
    )


def _statement_overlap_score(statement: str, implementation_text: str) -> float:
    statement_tokens = set(_tokenize(statement))
    impl_tokens = set(_tokenize(implementation_text))
    if not statement_tokens:
        return 0.0
    overlap = statement_tokens & impl_tokens
    return len(overlap) / max(len(statement_tokens), 1)


def _collect_validation_commands(repo_root: Path, target_languages: list[str], build_targets: list[dict[str, Any]]) -> list[str]:
    commands: list[str] = []
    for target in build_targets:
        for command in (target.get("commands", []) or []):
            if isinstance(command, str) and command.strip():
                commands.append(command.strip())
    if commands:
        return _dedupe_preserve_order(commands)
    languages = {_normalize_language(lang) for lang in target_languages if lang}
    if "python" in languages:
        commands.extend(["python -m py_compile", "python -m pytest -q"])
    if {"typescript", "javascript"} & languages:
        commands.extend(["npm run typecheck --if-present", "npm run test --if-present"])
    if "go" in languages:
        commands.append("go test ./...")
    if "rust" in languages:
        commands.append("cargo check")
    if "java" in languages:
        if (repo_root / "pom.xml").exists():
            commands.append("mvn -q test")
        if (repo_root / "build.gradle").exists() or (repo_root / "build.gradle.kts").exists():
            commands.append("./gradlew test")
    if "cpp" in languages:
        commands.append("cmake --build .")
    return _dedupe_preserve_order(commands)


def _run_validation_commands(repo_root: Path, commands: list[str], timeout_sec: int, enabled: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command in commands:
        if not enabled:
            results.append({"command": command, "status": "skipped", "exit_code": None, "stdout": "", "stderr": "Executable validation disabled."})
            continue
        try:
            proc = subprocess.run(
                command,
                cwd=str(repo_root),
                capture_output=True,
                shell=True,
                timeout=timeout_sec,
                text=True,
            )
            results.append(
                {
                    "command": command,
                    "status": "passed" if proc.returncode == 0 else "failed",
                    "exit_code": proc.returncode,
                    "stdout": (proc.stdout or "")[:2000],
                    "stderr": (proc.stderr or "")[:2000],
                }
            )
        except Exception as exc:
            results.append({"command": command, "status": "error", "exit_code": None, "stdout": "", "stderr": str(exc)})
    return results


def evaluation_plane(
    question_id: str,
    design_answer: DesignAnswer,
    artifact: CodeArtifact,
    repo_root: str | None = None,
    codebase_collection: dict[str, Any] | None = None,
    run_executable_validation: bool = False,
    validation_timeout_sec: int = 120,
) -> EvaluationRecord:
    brief = design_answer.implementation_brief
    explicit_support = [str(item) for item in brief.get("paper_supported_facts", []) if str(item).strip()]
    inferred_points = [str(item) for item in brief.get("inferred_assumptions", []) if str(item).strip()]
    underspecified = [str(item) for item in brief.get("unresolved_implementation_gaps", []) if str(item).strip()]
    conflicts = brief.get("conflicts_between_paper_and_repo", []) or []
    implementation_text = f"{artifact.summary}\n{artifact.generated_code}"

    matched_points: list[dict[str, Any]] = []
    missing_points: list[dict[str, Any]] = []
    for statement in explicit_support:
        score = _statement_overlap_score(statement, implementation_text)
        target = {"paper_statement": statement, "citation": "paper"}
        if score >= 0.2:
            matched_points.append({**target, "implementation_evidence": artifact.summary, "overlap_score": round(score, 3)})
        else:
            missing_points.append({**target, "issue_type": "not_implemented", "overlap_score": round(score, 3)})

    mismatch_points: list[dict[str, Any]] = []
    for conflict in conflicts[:20]:
        mismatch_points.append(
            {
                "paper_statement": str(conflict.get("paper_fact", "")),
                "implementation_evidence": str(conflict.get("code_evidence", "")),
                "issue_type": str(conflict.get("type", "alignment_gap")),
            }
        )

    if not explicit_support:
        faithfulness_status = "insufficient_paper_information"
    elif not missing_points and not mismatch_points:
        faithfulness_status = "faithful_match"
    elif matched_points:
        faithfulness_status = "partial_match"
    else:
        faithfulness_status = "mismatch"

    coverage_ratio = len(matched_points) / max(len(explicit_support), 1)
    paper_confidence = max(0.05, min(0.99, 0.35 + coverage_ratio * 0.6 - min(len(mismatch_points) * 0.08, 0.45)))

    root = Path(repo_root).resolve() if repo_root else None
    validation_commands = _collect_validation_commands(
        repo_root=root or Path.cwd(),
        target_languages=[artifact.language],
        build_targets=(codebase_collection or {}).get("build_targets", []) if isinstance(codebase_collection, dict) else [],
    )
    validation_results = _run_validation_commands(
        repo_root=root or Path.cwd(),
        commands=validation_commands,
        timeout_sec=validation_timeout_sec,
        enabled=bool(run_executable_validation and root and root.exists()),
    )
    failed_validations = [result for result in validation_results if result.get("status") in {"failed", "error"}]
    passed_validations = [result for result in validation_results if result.get("status") == "passed"]
    skipped_validations = [result for result in validation_results if result.get("status") == "skipped"]
    codebase_validity_status = "failed" if failed_validations else ("passed" if passed_validations else "skipped")

    risk_level = "low"
    if failed_validations or faithfulness_status == "mismatch":
        risk_level = "high"
    elif mismatch_points or missing_points or underspecified:
        risk_level = "medium"
    remaining_ambiguity = _dedupe_preserve_order(underspecified + [point.get("paper_statement", "") for point in mismatch_points if point.get("paper_statement")])

    if failed_validations:
        next_action = "fix_build_or_tests_then_refine"
    elif faithfulness_status in {"mismatch", "partial_match"}:
        next_action = "refine_current_module"
    elif faithfulness_status == "insufficient_paper_information":
        next_action = "retrieve_more_spec_or_confirm_assumptions"
    else:
        next_action = "move_to_next_module"

    evaluation = {
        "faithfulness_status": faithfulness_status,
        "matched_points": matched_points,
        "mismatched_points": mismatch_points,
        "missing_points": missing_points,
        "assumption_audit": {
            "directly_supported_count": len(explicit_support),
            "inferred_count": len(inferred_points),
            "underspecified_count": len(underspecified),
        },
        "information_gap_analysis": {
            "missing_from_code": [point.get("paper_statement", "") for point in missing_points],
            "missing_from_paper": underspecified,
            "present_but_not_retrieved": [] if design_answer.paper_evidence else ["No paper/spec evidence retrieved for this question."],
            "present_but_misunderstood": [point.get("paper_statement", "") for point in mismatch_points],
        },
        "paper_faithfulness": {"status": faithfulness_status, "coverage_ratio": round(coverage_ratio, 3), "confidence": round(paper_confidence, 3)},
        "codebase_validity": {
            "status": codebase_validity_status,
            "commands": validation_results,
            "passed_count": len(passed_validations),
            "failed_count": len(failed_validations),
            "skipped_count": len(skipped_validations),
        },
        "implementation_risk": {
            "risk_level": risk_level,
            "factors": {
                "faithfulness_status": faithfulness_status,
                "failed_validations": len(failed_validations),
                "unresolved_gaps": len(underspecified),
                "conflicts": len(mismatch_points),
            },
        },
        "remaining_ambiguity": remaining_ambiguity,
        "coverage_ratio": round(coverage_ratio, 3),
        "confidence": round(paper_confidence, 3),
        "next_action_recommendation": next_action,
    }
    return EvaluationRecord(question_id=question_id, evaluation=evaluation)


def refinement_plane(plan: list[dict[str, Any]], evaluations: list[EvaluationRecord]) -> dict[str, Any]:
    plan_by_id = {str(item.get("question_id")): item for item in plan if isinstance(item, dict)}
    existing_ids = [str(item.get("question_id")) for item in plan if isinstance(item, dict) and str(item.get("question_id", "")).startswith("Q-")]
    max_numeric_id = 0
    for question_id in existing_ids:
        try:
            max_numeric_id = max(max_numeric_id, int(question_id.split("-")[-1]))
        except Exception:
            continue

    refinement_decisions: list[dict[str, Any]] = []
    new_questions: list[dict[str, Any]] = []
    for record in evaluations:
        question_id = record.question_id
        current_item = plan_by_id.get(question_id)
        if not current_item:
            continue
        evaluation = record.evaluation
        faithfulness_status = str(evaluation.get("faithfulness_status", "partial_match"))
        validity_status = str(evaluation.get("codebase_validity", {}).get("status", "skipped"))
        risk_level = str(evaluation.get("implementation_risk", {}).get("risk_level", "medium"))
        next_action = str(evaluation.get("next_action_recommendation", "refine_current_module"))

        if faithfulness_status == "faithful_match" and validity_status in {"passed", "skipped"} and risk_level == "low":
            current_item["status"] = "completed"
            refinement_decisions.append({"question_id": question_id, "mode": "lateral_progression", "decision": "module_complete_move_to_next", "new_questions": []})
            continue
        if next_action == "move_to_next_module" and validity_status != "failed":
            current_item["status"] = "completed"
            refinement_decisions.append({"question_id": question_id, "mode": "lateral_progression", "decision": "sufficient_progress_move_laterally", "new_questions": []})
            continue

        current_item["status"] = "refined"
        max_numeric_id += 1
        followup_id = _build_question_id(max_numeric_id)
        followup = PlanQuestion(
            question_id=followup_id,
            question_depth=int(current_item.get("question_depth", 0)) + 1,
            question=(
                f"Deepen `{current_item.get('subsystem_id', current_item.get('module_id', 'module'))}`: "
                "Which symbol-level edits, interface updates, and validation fixes are still unresolved?"
            ),
            question_type="implementation_gap",
            paper_scopes=list(current_item.get("paper_scopes", current_item.get("toc_page_indexes", []))),
            repo_paths=list(current_item.get("repo_paths", [])),
            target_languages=list(current_item.get("target_languages", [])),
            target_symbols=list(current_item.get("target_symbols", [])),
            build_targets=list(current_item.get("build_targets", [])),
            subsystem_id=str(current_item.get("subsystem_id", current_item.get("module_id", "module"))),
            allowed_edit_paths=list(current_item.get("allowed_edit_paths", [])),
            forbidden_paths=list(current_item.get("forbidden_paths", [])),
            goal_alignment=list(current_item.get("goal_alignment", [])),
            expected_output_type="implementation_brief",
            priority="high",
            status="pending",
            parent_question_id=question_id,
            module_id=str(current_item.get("module_id", "module")),
            toc_page_indexes=list(current_item.get("toc_page_indexes", [])),
        ).to_dict()
        new_questions.append(followup)
        refinement_decisions.append({"question_id": question_id, "mode": "vertical_deepening", "decision": "add_followup_due_to_gaps", "new_questions": [followup_id]})

    plan.extend(new_questions)
    return {"updated_plan": plan, "new_questions": new_questions, "refinement_decisions": refinement_decisions}


def _build_toc_tree(toc_paths: list[str]) -> list[dict[str, Any]]:
    root: dict[str, Any] = {}
    for path in toc_paths:
        parts = [item.strip() for item in path.split(">") if item.strip()]
        node = root
        for part in parts:
            node = node.setdefault(part, {})

    def _to_nodes(tree: dict[str, Any], parent: str = "") -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        for name, child in tree.items():
            full_path = f"{parent} > {name}" if parent else name
            nodes.append({"name": name, "path": full_path, "children": _to_nodes(child, full_path)})
        return nodes

    return _to_nodes(root)


def _graph_summary(repository_graphs: dict[str, Any] | None) -> dict[str, Any]:
    repository_graphs = repository_graphs or {}
    summary: dict[str, Any] = {}
    for key in ["import_graph", "symbol_reference_graph", "module_dependency_graph", "build_target_graph", "service_dataflow_graph"]:
        graph = repository_graphs.get(key, {}) or {}
        graph_summary = graph.get("summary", {}) if isinstance(graph, dict) else {}
        summary[key] = {"node_count": int(graph_summary.get("node_count", 0)), "edge_count": int(graph_summary.get("edge_count", 0))}
    summary["adjacency_nodes"] = len(repository_graphs.get("adjacency", {}) or {})
    return summary


def build_dashboard(
    collection: dict[str, Any],
    plan: list[dict[str, Any]],
    retrieval_log: list[dict[str, Any]],
    design_answers: list[DesignAnswer],
    artifacts: list[CodeArtifact],
    evaluations: list[EvaluationRecord],
    codebase_collection: dict[str, Any] | None = None,
    repository_graphs: dict[str, Any] | None = None,
    working_set_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evaluation_by_question = {record.question_id: record.evaluation for record in evaluations}
    status_counter: Counter[str] = Counter(str(item.get("status", "pending")) for item in plan)
    faithfulness_counter: Counter[str] = Counter(str(record.evaluation.get("faithfulness_status", "unknown")) for record in evaluations)
    code_validity_counter: Counter[str] = Counter(str(record.evaluation.get("codebase_validity", {}).get("status", "unknown")) for record in evaluations)
    inferred_total = sum(len(answer.implementation_brief.get("inferred_assumptions", [])) for answer in design_answers)
    missing_total = sum(len(record.evaluation.get("missing_points", [])) for record in evaluations)
    ambiguity: list[str] = []
    for record in evaluations:
        ambiguity.extend(record.evaluation.get("remaining_ambiguity", []) or [])

    codebase_collection = codebase_collection or {}
    return {
        "paper_structure_view": {
            "toc_tree": _build_toc_tree(collection.get("toc_paths", []) or ["Document"]),
            "chunks_by_section": {
                chunk.get("headings_info", ""): chunk.get("chunk_id", "")
                for chunk in collection.get("chunks", [])
                if isinstance(chunk, dict) and chunk.get("type") != "toc"
            },
        },
        "repository_structure_view": {
            "repo_root": codebase_collection.get("repo_root", ""),
            "modules": codebase_collection.get("modules", []),
            "build_targets": codebase_collection.get("build_targets", []),
            "interface_contracts": codebase_collection.get("interface_contracts", []),
            "tests": codebase_collection.get("tests", []),
            "schemas": codebase_collection.get("schemas", []),
        },
        "graph_view": _graph_summary(repository_graphs),
        "planning_view": {"status_counts": dict(status_counter), "questions": plan},
        "working_set_view": {"history": working_set_history or []},
        "retrieval_evidence_view": {"question_to_chunks": retrieval_log},
        "implementation_coverage_view": {
            "faithfulness_counts": dict(faithfulness_counter),
            "codebase_validity_counts": dict(code_validity_counter),
            "missing_points_total": missing_total,
            "inferred_points_total": inferred_total,
            "per_question": evaluation_by_question,
        },
        "code_traceability_view": {"artifacts": [artifact.to_dict() for artifact in artifacts]},
        "gap_analysis_view": {
            "ambiguity_requiring_assumptions": _dedupe_preserve_order(ambiguity),
            "implementation_not_completed": [item.get("question_id") for item in plan if str(item.get("status", "")) not in {"completed"}],
            "high_risk_questions": [
                {"question_id": record.question_id, "risk": record.evaluation.get("implementation_risk", {})}
                for record in evaluations
                if record.evaluation.get("implementation_risk", {}).get("risk_level") == "high"
            ],
        },
    }


def _status_summary(plan: list[dict[str, Any]], evaluations: list[EvaluationRecord]) -> dict[str, Any]:
    plan_status = Counter(str(item.get("status", "pending")) for item in plan)
    eval_status = Counter(str(record.evaluation.get("faithfulness_status", "unknown")) for record in evaluations)
    code_validity = Counter(str(record.evaluation.get("codebase_validity", {}).get("status", "unknown")) for record in evaluations)
    return {
        "plan_status": dict(plan_status),
        "evaluation_status": dict(eval_status),
        "codebase_validity_status": dict(code_validity),
        "total_questions": len(plan),
        "evaluated_questions": len(evaluations),
    }


def _traceability_graph(design_answers: list[DesignAnswer], artifacts: list[CodeArtifact], evaluations: list[EvaluationRecord]) -> list[dict[str, Any]]:
    artifact_by_question = {artifact.question_id: artifact for artifact in artifacts}
    eval_by_question = {record.question_id: record for record in evaluations}
    graph: list[dict[str, Any]] = []
    for answer in design_answers:
        artifact = artifact_by_question.get(answer.question_id)
        evaluation = eval_by_question.get(answer.question_id)
        graph.append(
            {
                "question_id": answer.question_id,
                "paper_citations": [item for item in answer.citations if item.get("source_type") == "paper"],
                "code_citations": [item for item in answer.citations if item.get("source_type") == "code"],
                "matched_part": (artifact.traceability.get("matched_part", []) if artifact else []),
                "mismatched_part": (evaluation.evaluation.get("mismatched_points", []) if evaluation else []),
                "missing_part": (artifact.traceability.get("missing_part", []) if artifact else []),
                "inferred_part": (artifact.traceability.get("inferred_part", []) if artifact else []),
                "implementation_locations": (artifact.files_changed if artifact else []),
                "language": (artifact.language if artifact else ""),
                "adapter_id": (artifact.adapter_id if artifact else ""),
                "evaluation_status": (evaluation.evaluation.get("faithfulness_status", "not_evaluated") if evaluation else "not_evaluated"),
                "codebase_validity": (evaluation.evaluation.get("codebase_validity", {}).get("status", "not_evaluated") if evaluation else "not_evaluated"),
            }
        )
    return graph


async def _resolve_html_content(args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    spec_text = str(args.get("spec_text") or args.get("specification") or "").strip()
    if spec_text:
        html_content = f"<html><body><h1>Specification</h1><p>{html_lib.escape(spec_text)}</p></body></html>"
        return html_content, {"source": "spec_text"}
    html_content = str(args.get("html_content") or args.get("html") or "").strip()
    if html_content:
        return html_content, {"source": "inline"}
    html_path = str(args.get("html_path") or "").strip()
    if html_path:
        path = Path(html_path)
        if not path.exists():
            raise FileNotFoundError(f"html_path not found: {path}")
        return path.read_text(encoding="utf-8"), {"source": "path", "path": str(path)}
    html_url = str(args.get("html_url") or "").strip()
    if html_url:
        res = requests.get(html_url, timeout=60.0)
        if res.status_code >= 400:
            raise RuntimeError(f"Failed to fetch html_url ({res.status_code}): {res.text[:300]}")
        return res.text, {"source": "url", "url": html_url}
    arxiv_id = str(args.get("arxiv_id") or "").strip()
    if arxiv_id:
        html = await fetch_full_content(arxiv_id)
        return html, {"source": "arxiv", "arxiv_id": arxiv_id, "url": f"https://arxiv.org/html/{arxiv_id}"}
    if _coerce_bool(args.get("allow_empty_paper"), default=True):
        return "", {"source": "none"}
    raise ValueError("Provide one of: spec_text, html_content, html_path, html_url, or arxiv_id.")


def _select_next_questions(plan: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    pending = [item for item in plan if str(item.get("status", "pending")) in {"pending", "refined", "in_progress"}]
    pending.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(str(item.get("priority", "medium")), 1),
            int(item.get("question_depth", 0)),
            str(item.get("question_id", "")),
        )
    )
    return pending[:limit]


def architecture_blueprint() -> dict[str, Any]:
    return {
        "revised_architecture_description": {
            "controller": "progressive_paper_to_code orchestrates dual-grounded pipeline",
            "capabilities": [
                "paper/spec ingestion",
                "repository ingestion with first-class code chunks",
                "graph-aware retrieval and planning",
                "language/project backends with bounded edits",
                "paper faithfulness + executable validation",
                "dashboard and traceability artifacts",
            ],
            "partial_mode_support": "works when paper source, graph extraction, or executable validation is unavailable",
        },
        "new_dataclasses_and_interfaces": [
            "CodeChunk",
            "RepositoryModule",
            "BuildTarget",
            "InterfaceContract",
            "RepositoryCollection",
            "RepositoryGraph / GraphEdge / RepositoryGraphBundle",
            "PlanQuestion (dual-grounded fields)",
            "WorkingSet",
            "CodeExecutionAdapter backends (Python/TypeScript/Java/Go/Rust/Cpp/Fallback)",
        ],
        "revised_pipeline_stages": [
            "ingest_paper_or_spec",
            "ingest_repository",
            "build_repository_graphs",
            "dual_grounded_planning",
            "iterative_retrieval_merge_design_codegen_eval_refine",
            "dashboard_and_traceability_export",
        ],
        "retrieval_api_surface": [
            "retrieve_paper_evidence",
            "retrieve_code_evidence",
            "merge_evidence",
            "retrieve_chunks_for_question (compat wrapper)",
        ],
        "graph_schema_and_usage": {
            "graphs": [
                "file_import_graph",
                "symbol_reference_graph",
                "module_dependency_graph",
                "build_target_graph",
                "service_dataflow_graph",
            ],
            "usage_points": [
                "seed lexical retrieval then graph expansion",
                "subsystem planning and working set narrowing",
                "interface/build impact surfacing",
            ],
        },
        "backend_adapter_redesign": {
            "project_backends": [
                "PythonProjectAdapter",
                "TypeScriptProjectAdapter",
                "JavaProjectAdapter",
                "GoProjectAdapter",
                "RustProjectAdapter",
                "CppProjectAdapter",
            ],
            "fallback": "GenericFallbackProjectAdapter (low confidence)",
            "backend_contract": ["supports", "locate_edit_points", "render", "generate_tests", "update_build_hints", "validation_hooks"],
        },
        "evaluation_redesign": {
            "dimensions": ["paper_faithfulness", "codebase_validity", "implementation_risk", "remaining_ambiguity"],
            "executable_checks": "build/test/typecheck commands from build-target model when enabled",
        },
        "migration_notes": [
            "legacy entrypoints preserved: progressive_paper_to_code, paper_to_code, Progressive_Paper_to_Code",
            "legacy paper functions preserved: prepare_vector_store_collection, planning_plane, retrieve_chunks_for_question",
            "new dual-grounded fields are additive; old toc_page_indexes remains populated for compatibility",
        ],
    }


async def progressive_paper_to_code(args: dict[str, Any]) -> dict[str, Any]:
    payload = args or {}
    html_content, source_meta = await _resolve_html_content(payload)
    paper_title = str(payload.get("paper_title") or payload.get("title") or "Untitled Spec").strip()
    collection_id = str(payload.get("collection_id") or "").strip() or None
    repo_root = str(payload.get("repo_root") or Path.cwd()).strip()

    max_iterations = _coerce_int(payload.get("max_iterations", 3), default=3, low=1, high=10)
    questions_per_iteration = _coerce_int(payload.get("questions_per_iteration", 4), default=4, low=1, high=12)
    max_questions = _coerce_int(payload.get("max_questions", 24), default=24, low=4, high=80)
    top_k_paper = _coerce_int(payload.get("top_k_paper", payload.get("top_k", 6)), default=6, low=2, high=30)
    top_k_code = _coerce_int(payload.get("top_k_code", 10), default=10, low=3, high=50)
    graph_expand_hops = _coerce_int(payload.get("graph_expand_hops", 1), default=1, low=0, high=3)
    write_artifacts = _coerce_bool(payload.get("write_artifacts"), default=False)
    output_dir = str(payload.get("output_dir") or "").strip() or None
    save_output_path = str(payload.get("save_output_path") or "").strip()
    run_executable_validation = _coerce_bool(payload.get("run_executable_validation"), default=False)

    include_paths = [str(path) for path in (payload.get("include_paths", []) or []) if str(path).strip()]
    exclude_paths = [str(path) for path in (payload.get("exclude_paths", []) or []) if str(path).strip()]
    allowed_edit_paths = [str(path) for path in (payload.get("allowed_edit_paths", []) or []) if str(path).strip()]
    forbidden_paths = [str(path) for path in (payload.get("forbidden_paths", []) or []) if str(path).strip()]
    target_languages = [_normalize_language(str(lang)) for lang in (payload.get("target_languages", []) or []) if str(lang).strip()]

    if html_content:
        collection = prepare_vector_store_collection(
            html_content=html_content,
            paper_title=paper_title,
            arxiv_id=str(source_meta.get("arxiv_id", "")),
            collection_id=collection_id,
            chunk_max_chars=_coerce_int(payload.get("chunk_max_chars", 1200), 1200, 300, 4000),
            reuse_academic_chunking=_coerce_bool(payload.get("reuse_academic_chunking"), default=True),
        )
    else:
        collection = _build_collection_from_spec_text(spec_text=str(payload.get("spec_text") or paper_title), collection_id=collection_id)

    codebase_collection = prepare_codebase_collection(
        repo_root=repo_root,
        collection_id=str(payload.get("repo_collection_id") or "").strip() or None,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
        max_files=_coerce_int(payload.get("repo_max_files", 5000), 5000, 100, 20000),
        max_file_bytes=_coerce_int(payload.get("repo_max_file_bytes", 600_000), 600_000, 20_000, 5_000_000),
    )
    repository_graphs = build_repository_graphs(codebase_collection)

    plan_bundle = planning_plane(
        collection,
        max_questions=max_questions,
        codebase_collection=codebase_collection,
        allowed_edit_paths=allowed_edit_paths,
        forbidden_paths=forbidden_paths,
        target_languages=target_languages,
    )
    plan = list(plan_bundle.get("plan", []))

    logs: dict[str, list[dict[str, Any]]] = {
        "plan_generation_log": [
            _log_entry(
                question_id="PLAN",
                module_id="planner",
                cited_chunk_ids=[str(collection.get("toc_chunk_id", "chunk-0000"))],
                outcome_status="success",
                confidence=0.9,
                next_action="start_progressive_loop",
                details={
                    "root_goals": plan_bundle.get("goals", []),
                    "plan_items": len(plan),
                    "repo_overview": codebase_collection.get("metadata", {}).get("overview", {}),
                },
            )
        ],
        "retrieval_log": [],
        "paper_retrieval_log": [],
        "code_retrieval_log": [],
        "merge_log": [],
        "working_set_log": [],
        "comprehension_log": [],
        "codegen_log": [],
        "evaluation_log": [],
        "refinement_decision_log": [],
    }
    design_answers: list[DesignAnswer] = []
    artifacts: list[CodeArtifact] = []
    evaluations: list[EvaluationRecord] = []
    refinement_history: list[dict[str, Any]] = []
    working_set_history: list[dict[str, Any]] = []

    for _ in range(max_iterations):
        current_questions = _select_next_questions(plan, questions_per_iteration)
        if not current_questions:
            break
        current_evaluations: list[EvaluationRecord] = []

        for question in current_questions:
            question_id = str(question.get("question_id", "Q-0000"))
            question["status"] = "in_progress"
            module_id = str(question.get("module_id", "module"))

            working_set = build_hierarchical_working_set(
                plan_item=question,
                codebase_collection=codebase_collection,
                repository_graphs=repository_graphs,
                code_evidence=[],
                file_budget=_coerce_int(payload.get("working_set_file_budget", 80), 80, 10, 400),
                symbol_budget=_coerce_int(payload.get("working_set_symbol_budget", 200), 200, 20, 1000),
            )
            working_set_history.append({"question_id": question_id, **working_set.to_dict()})
            logs["working_set_log"].append(
                _log_entry(
                    question_id=question_id,
                    module_id=module_id,
                    cited_chunk_ids=[],
                    outcome_status="working_set_built",
                    confidence=0.85,
                    next_action="retrieve_evidence",
                    details=working_set.to_dict(),
                )
            )

            paper_scopes = list(question.get("paper_scopes", question.get("toc_page_indexes", []))) or []
            paper_evidence = retrieve_paper_evidence(
                collection=collection,
                question=str(question.get("question", "")),
                paper_scopes=paper_scopes,
                top_k=top_k_paper,
            )
            logs["paper_retrieval_log"].append(
                _log_entry(
                    question_id=question_id,
                    module_id=module_id,
                    cited_chunk_ids=[str(item.get("chunk_id", "")) for item in paper_evidence],
                    outcome_status="retrieved" if paper_evidence else "empty",
                    confidence=0.8 if paper_evidence else 0.3,
                    next_action="code_retrieval",
                    details={"paper_scopes": paper_scopes, "retrieved_count": len(paper_evidence)},
                )
            )

            code_repo_paths = list(question.get("repo_paths", [])) or working_set.candidate_file_set[:20]
            code_evidence = retrieve_code_evidence(
                codebase_collection=codebase_collection,
                repository_graphs=repository_graphs,
                question=str(question.get("question", "")),
                repo_paths=code_repo_paths,
                target_languages=list(question.get("target_languages", [])),
                target_symbols=list(question.get("target_symbols", [])),
                build_targets=list(question.get("build_targets", [])),
                subsystem_id=str(question.get("subsystem_id", "")),
                top_k=top_k_code,
                graph_expand_hops=graph_expand_hops,
            )
            logs["code_retrieval_log"].append(
                _log_entry(
                    question_id=question_id,
                    module_id=module_id,
                    cited_chunk_ids=[str(item.get("chunk_id", "")) for item in code_evidence],
                    outcome_status="retrieved" if code_evidence else "empty",
                    confidence=0.82 if code_evidence else 0.25,
                    next_action="merge_evidence",
                    details={"repo_paths": code_repo_paths[:20], "retrieved_count": len(code_evidence)},
                )
            )

            working_set = build_hierarchical_working_set(
                plan_item=question,
                codebase_collection=codebase_collection,
                repository_graphs=repository_graphs,
                code_evidence=code_evidence,
                file_budget=_coerce_int(payload.get("working_set_file_budget", 80), 80, 10, 400),
                symbol_budget=_coerce_int(payload.get("working_set_symbol_budget", 200), 200, 20, 1000),
            )
            working_set_history.append({"question_id": question_id, "refined": True, **working_set.to_dict()})

            merged = merge_evidence(
                question=str(question.get("question", "")),
                paper_evidence=paper_evidence,
                code_evidence=code_evidence,
                target_symbols=list(question.get("target_symbols", [])),
                target_languages=list(question.get("target_languages", [])),
            )
            logs["merge_log"].append(
                _log_entry(
                    question_id=question_id,
                    module_id=module_id,
                    cited_chunk_ids=[str(item.get("chunk_id", "")) for item in paper_evidence + code_evidence],
                    outcome_status="merged",
                    confidence=float(merged.get("confidence", 0.5)),
                    next_action="comprehension",
                    details={
                        "paper_facts": len(merged.get("paper_supported_facts", [])),
                        "code_facts": len(merged.get("codebase_supported_facts", [])),
                        "conflicts": len(merged.get("conflicts_between_paper_and_repo", [])),
                        "gaps": len(merged.get("unresolved_implementation_gaps", [])),
                    },
                )
            )

            design_answer = comprehension_and_design_plane(
                plan_item=question,
                retrieved_chunks=paper_evidence,
                code_evidence=code_evidence,
                merged_evidence=merged,
                working_set=working_set,
            )
            design_answers.append(design_answer)
            question["status"] = "answered"
            logs["comprehension_log"].append(
                _log_entry(
                    question_id=question_id,
                    module_id=module_id,
                    cited_chunk_ids=[citation.get("chunk_id", "") for citation in design_answer.citations if citation.get("chunk_id")],
                    outcome_status="answered",
                    confidence=float(design_answer.implementation_brief.get("confidence", 0.5)),
                    next_action="codegen",
                    details={
                        "conflicts": design_answer.implementation_brief.get("conflicts_between_paper_and_repo", []),
                        "gaps": design_answer.implementation_brief.get("unresolved_implementation_gaps", []),
                        "working_set_size": len(working_set.bounded_edit_set),
                    },
                )
            )

            artifact = code_agent_execution_plane(
                design_answer=design_answer,
                output_dir=output_dir,
                write_artifacts=write_artifacts,
                codebase_collection=codebase_collection,
                working_set=working_set,
                preferred_language=str(payload.get("target_language", "")).strip() or None,
            )
            artifacts.append(artifact)
            question["status"] = "coded"
            logs["codegen_log"].append(
                _log_entry(
                    question_id=question_id,
                    module_id=module_id,
                    cited_chunk_ids=[citation.get("chunk_id", "") for citation in design_answer.citations if citation.get("chunk_id")],
                    outcome_status="generated",
                    confidence=0.78 if artifact.adapter_id != "generic_fallback_project_adapter" else 0.45,
                    next_action="evaluation",
                    details={"files_changed": artifact.files_changed, "language": artifact.language, "adapter_id": artifact.adapter_id},
                )
            )

            evaluation = evaluation_plane(
                question_id=question_id,
                design_answer=design_answer,
                artifact=artifact,
                repo_root=repo_root,
                codebase_collection=codebase_collection,
                run_executable_validation=run_executable_validation,
                validation_timeout_sec=_coerce_int(payload.get("validation_timeout_sec", 120), 120, 20, 900),
            )
            evaluations.append(evaluation)
            current_evaluations.append(evaluation)
            question["status"] = "evaluated"
            logs["evaluation_log"].append(
                _log_entry(
                    question_id=question_id,
                    module_id=module_id,
                    cited_chunk_ids=[citation.get("chunk_id", "") for citation in design_answer.citations if citation.get("chunk_id")],
                    outcome_status=str(evaluation.evaluation.get("faithfulness_status", "partial_match")),
                    confidence=float(evaluation.evaluation.get("confidence", 0.5)),
                    next_action=str(evaluation.evaluation.get("next_action_recommendation", "refine_current_module")),
                    details={
                        "coverage_ratio": evaluation.evaluation.get("coverage_ratio", 0.0),
                        "codebase_validity": evaluation.evaluation.get("codebase_validity", {}),
                        "risk": evaluation.evaluation.get("implementation_risk", {}),
                    },
                )
            )

            logs["retrieval_log"].append(
                _log_entry(
                    question_id=question_id,
                    module_id=module_id,
                    cited_chunk_ids=[str(item.get("chunk_id", "")) for item in paper_evidence + code_evidence],
                    outcome_status="retrieved",
                    confidence=float(merged.get("confidence", 0.5)),
                    next_action="comprehension",
                    details={
                        "paper_retrieved": len(paper_evidence),
                        "code_retrieved": len(code_evidence),
                        "conflicts": len(merged.get("conflicts_between_paper_and_repo", [])),
                    },
                )
            )

        refinement = refinement_plane(plan, current_evaluations)
        plan = refinement.get("updated_plan", plan)
        refinement_history.append(refinement)
        for decision in refinement.get("refinement_decisions", []):
            logs["refinement_decision_log"].append(
                _log_entry(
                    question_id=str(decision.get("question_id", "")),
                    module_id="refinement",
                    cited_chunk_ids=[],
                    outcome_status=str(decision.get("mode", "lateral_progression")),
                    confidence=0.72,
                    next_action="continue",
                    details={"decision": decision.get("decision", ""), "new_questions": decision.get("new_questions", []) or []},
                )
            )

    dashboard = build_dashboard(
        collection=collection,
        plan=plan,
        retrieval_log=logs["retrieval_log"],
        design_answers=design_answers,
        artifacts=artifacts,
        evaluations=evaluations,
        codebase_collection=codebase_collection,
        repository_graphs=repository_graphs,
        working_set_history=working_set_history,
    )

    result = {
        "paper_title": paper_title,
        "source": source_meta,
        "collection": {
            "collection_id": collection.get("collection_id"),
            "paper_title": collection.get("paper_title"),
            "toc_chunk_id": collection.get("toc_chunk_id"),
            "overview": collection.get("overview"),
            "toc_paths": collection.get("toc_paths", []),
            "chunks": collection.get("chunks", []),
        },
        "codebase_collection": {
            "collection_id": codebase_collection.get("collection_id"),
            "repo_root": codebase_collection.get("repo_root"),
            "overview": codebase_collection.get("metadata", {}).get("overview", {}),
            "modules": codebase_collection.get("modules", []),
            "build_targets": codebase_collection.get("build_targets", []),
            "interface_contracts": codebase_collection.get("interface_contracts", []),
        },
        "repository_graphs": repository_graphs,
        "plan_bundle": {"goals": plan_bundle.get("goals", []), "planner_notes": plan_bundle.get("planner_notes", {}), "plan": plan},
        "design_answers": [answer.to_dict() for answer in design_answers],
        "code_artifacts": [artifact.to_dict() for artifact in artifacts],
        "evaluations": [record.to_dict() for record in evaluations],
        "refinement_history": refinement_history,
        "traceability_graph": _traceability_graph(design_answers, artifacts, evaluations),
        "dashboard": dashboard,
        "logs": logs,
        "status_summary": _status_summary(plan, evaluations),
        "architecture_blueprint": architecture_blueprint(),
    }
    if save_output_path:
        output_path = Path(save_output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
        result["saved_output_path"] = str(output_path)
    return result


async def paper_to_code(args: dict[str, Any]) -> dict[str, Any]:
    return await progressive_paper_to_code(args)


async def Progressive_Paper_to_Code(args: dict[str, Any]) -> dict[str, Any]:
    return await progressive_paper_to_code(args)
