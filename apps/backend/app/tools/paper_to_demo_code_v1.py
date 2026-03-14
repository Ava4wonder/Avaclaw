"""
Faithful paper-to-demo-code generator.

This version is intentionally simpler than the full progressive paper-to-code
system, but it preserves the technically critical stages needed for a higher-
quality demo implementation:

1. Paper ingestion and chunking
2. Structured planning plane
3. Scoped evidence retrieval
4. Comprehension and design synthesis
5. Module-level code generation with traceability
6. Faithfulness-oriented evaluation
7. Refinement of unanswered / underspecified modules
8. README + metadata export

It does NOT attempt full repository grounding, executable HDL generation, or
EDA validation. Those belong to the full system. However, unlike the shallow
version, this file does not skip the planning and evidence-merging stages that
are necessary for faithful simplified demos.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import html as html_lib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
import uuid

import httpx
import requests

from ..config import settings
from .academic_search import fetch_full_content, html_parsing_chunking_upsert


QUESTION_TYPE_PRIORITY = {
    "structure": 5,
    "method": 5,
    "module_design": 5,
    "interface_contract": 4,
    "algorithm": 4,
    "data_flow": 4,
    "evaluation_protocol": 3,
    "implementation_gap": 2,
}

SUPPORTED_LANGUAGES = {"python", "typescript", "javascript", "java", "go", "rust", "cpp"}
DEFAULT_LANGUAGE = "python"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    text = html_lib.unescape(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", (text or "").lower())


def _sentence_split(text: str) -> list[str]:
    if not text:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


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
        extra = len(sentence) + (1 if current else 0)
        if current and current_len + extra > max_chars:
            chunks.append(" ".join(current).strip())
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len += extra
    if current:
        chunks.append(" ".join(current).strip())
    return [chunk for chunk in chunks if chunk]


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


def _priority_label(question_type: str) -> str:
    score = QUESTION_TYPE_PRIORITY.get(question_type, 1)
    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _extract_json_from_text(raw: str) -> Any | None:
    raw = (raw or "").strip()
    if not raw:
        return None

    code_block_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
    if code_block_match:
        raw = code_block_match.group(1).strip()

    decoder = json.JSONDecoder()
    for i, ch in enumerate(raw):
        if ch not in {"{", "["}:
            continue
        try:
            obj, _ = decoder.raw_decode(raw[i:])
            return obj
        except Exception:
            continue
    return None


def _extract_code_blocks(text: str) -> list[dict[str, str]]:
    pattern = r"```(\w+)?\s*\n(.*?)\n```"
    matches = re.findall(pattern, text or "", re.DOTALL)
    return [{"language": (lang or "").strip() or "text", "code": code.strip()} for lang, code in matches]


def _extract_object_number(caption: str, kind: str) -> str:
    if not caption:
        return ""
    if kind == "image":
        match = re.search(r"\b(?:fig(?:ure)?\.?)\s*([0-9A-Za-z._-]+)", caption, flags=re.IGNORECASE)
    else:
        match = re.search(r"\btable\s*([0-9A-Za-z._-]+)", caption, flags=re.IGNORECASE)
    return match.group(1) if match else ""


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
class PlanQuestion:
    question_id: str
    question_depth: int
    question: str
    question_type: str
    paper_scopes: list[str] = field(default_factory=list)
    expected_output_type: str = "design_spec"
    priority: str = "medium"
    status: str = "pending"
    parent_question_id: str | None = None
    module_id: str = "framework"
    goal_alignment: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DesignAnswer:
    question_id: str
    implementation_brief: dict[str, Any]
    citations: list[dict[str, Any]]
    paper_evidence: list[dict[str, Any]]
    merged_evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodeArtifact:
    artifact_id: str
    question_id: str
    module_name: str
    filename: str
    purpose: str
    code: str
    language: str
    traceability: dict[str, Any]
    evaluation_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationRecord:
    question_id: str
    evaluation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _PaperHtmlParser(HTMLParser):
    """
    HTML parser that preserves headings, text blocks, figures, and tables.
    Used when academic_search-based chunk reuse is unavailable.
    """

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
        return " > ".join(self.heading_stack) if self.heading_stack else "Document"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}

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
            content = _normalize_text(" ".join(self._figure_buffer)) or caption
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


def _build_collection_from_manual_parse(
    html_content: str,
    paper_title: str,
    collection_id: str | None = None,
    chunk_max_chars: int = 1200,
) -> dict[str, Any]:
    parser = _PaperHtmlParser()
    parser.feed(html_content or "")
    parser.close()

    toc_paths = _dedupe_preserve_order(parser.toc_paths) or ["Document"]
    toc_text = _format_toc(toc_paths)

    chunks: list[PaperChunk] = [
        PaperChunk(
            chunk_id="chunk-0000",
            type="toc",
            content=toc_text,
            headings_info="TOC",
            metadata={"section_order_index": -1, "source": "manual_html_parser"},
        )
    ]

    section_order = 0
    for raw in parser.raw_chunks:
        chunk_type = str(raw.get("type", "text"))
        headings = str(raw.get("headings_info", "Document")).strip() or "Document"
        content = _normalize_text(str(raw.get("content", "")))
        metadata = dict(raw.get("metadata") or {})
        if not content:
            continue

        if chunk_type == "text":
            parts = _semantic_split_text(content, max_chars=chunk_max_chars)
        else:
            parts = [content]

        for part in parts:
            if not part:
                continue
            section_order += 1
            chunks.append(
                PaperChunk(
                    chunk_id=f"chunk-{section_order:04d}",
                    type=chunk_type,
                    content=part,
                    headings_info=headings,
                    metadata={**metadata, "section_order_index": section_order},
                )
            )

    return {
        "collection_id": collection_id or f"paper_demo_{uuid.uuid4().hex[:12]}",
        "paper_title": paper_title,
        "toc_paths": toc_paths,
        "toc_chunk_id": "chunk-0000",
        "chunks": [chunk.to_dict() for chunk in chunks],
        "overview": {
            "total_chunks": len(chunks),
            "types": {
                "text": sum(1 for c in chunks if c.type == "text"),
                "image": sum(1 for c in chunks if c.type == "image"),
                "table": sum(1 for c in chunks if c.type == "table"),
            },
        },
    }


def prepare_paper_collection(
    html_content: str,
    paper_title: str,
    arxiv_id: str = "",
    collection_id: str | None = None,
    chunk_max_chars: int = 1200,
    reuse_academic_chunking: bool = True,
) -> dict[str, Any]:
    """
    Prepare a paper collection. First tries to reuse academic_search chunking/upsert
    because it often yields better section structure. Falls back to local HTML parse.
    """
    if reuse_academic_chunking and html_content:
        try:
            chunking_result = html_parsing_chunking_upsert(
                html_content=html_content,
                paper_title=paper_title,
                arxiv_id=arxiv_id,
                chunk_size=chunk_max_chars,
                chunk_overlap=max(100, int(chunk_max_chars * 0.15)),
            )
            text_toc = str(chunking_result.get("text_toc", "")).strip()
            collection_name = str(chunking_result.get("collection_name", "")).strip()
            if collection_name and text_toc:
                points = _qdrant_scroll_all(collection_name)
                chunks: list[PaperChunk] = [
                    PaperChunk(
                        chunk_id="chunk-0000",
                        type="toc",
                        content=text_toc,
                        headings_info="TOC",
                        metadata={
                            "section_order_index": -1,
                            "source": "academic_search.html_parsing_chunking_upsert",
                            "source_collection_name": collection_name,
                            "chunks_upserted": chunking_result.get("chunks_upserted", 0),
                        },
                    )
                ]
                for idx, point in enumerate(points, start=1):
                    payload = point.get("payload") or {}
                    content = _normalize_text(str(payload.get("chunk_text", "")))
                    if not content:
                        continue
                    headings = str(payload.get("headings_info", "Document")).strip() or "Document"
                    chunks.append(
                        PaperChunk(
                            chunk_id=f"chunk-{idx:04d}",
                            type="text",
                            content=content,
                            headings_info=headings,
                            metadata={
                                "section_order_index": idx,
                                "source": "academic_search.html_parsing_chunking_upsert",
                                "qdrant_point_id": point.get("id"),
                                "paper_title": payload.get("paper_title", paper_title),
                                "arxiv_id": payload.get("arxiv_id", arxiv_id),
                            },
                        )
                    )
                if len(chunks) > 1:
                    toc_paths = _dedupe_preserve_order(
                        [line.strip("- ").strip() for line in text_toc.splitlines() if line.strip()]
                    ) or ["Document"]
                    return {
                        "collection_id": collection_id or f"paper_demo_{uuid.uuid4().hex[:12]}",
                        "paper_title": paper_title,
                        "toc_paths": toc_paths,
                        "toc_chunk_id": "chunk-0000",
                        "chunks": [chunk.to_dict() for chunk in chunks],
                        "overview": {
                            "total_chunks": len(chunks),
                            "types": {"text": len(chunks) - 1},
                            "source_collection_name": collection_name,
                        },
                    }
        except Exception:
            pass

    return _build_collection_from_manual_parse(
        html_content=html_content,
        paper_title=paper_title,
        collection_id=collection_id,
        chunk_max_chars=chunk_max_chars,
    )


def _qdrant_base_url() -> str:
    return f"http://{settings.qdrant_host}:{settings.qdrant_port}"


def _qdrant_scroll_all(collection_name: str, page_size: int = 256) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    url = f"{_qdrant_base_url()}/collections/{collection_name}/points/scroll"
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


def _chunk_objects(collection: dict[str, Any]) -> list[PaperChunk]:
    chunks: list[PaperChunk] = []
    for item in collection.get("chunks", []) or []:
        if not isinstance(item, dict):
            continue
        chunks.append(
            PaperChunk(
                chunk_id=str(item.get("chunk_id", "")),
                type=str(item.get("type", "")),
                content=str(item.get("content", "")),
                headings_info=str(item.get("headings_info", "")),
                metadata=dict(item.get("metadata") or {}),
            )
        )
    return chunks


def _extract_goal_statements(chunks: list[PaperChunk], limit: int = 4) -> list[str]:
    focus_keywords = ("abstract", "introduction", "conclusion", "summary", "motivation")
    selected: list[str] = []
    for chunk in chunks:
        if chunk.type != "text":
            continue
        heading = chunk.headings_info.lower()
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


def planning_plane(collection: dict[str, Any], max_questions: int = 12) -> dict[str, Any]:
    """
    Critical stage: this is intentionally preserved as a real planning plane,
    not collapsed into a single architecture prompt.
    """
    chunks = _chunk_objects(collection)
    toc_paths = collection.get("toc_paths", []) or ["Document"]
    goals = _extract_goal_statements(chunks)
    if not goals:
        goals = ["Produce a faithful simplified implementation scaffold with explicit traceability to the paper."]

    plans: list[PlanQuestion] = []
    q_index = 1

    root = PlanQuestion(
        question_id=_build_question_id(q_index),
        question_depth=0,
        question="What are the paper's top-level architecture, objectives, major modules, and execution flow?",
        question_type="structure",
        paper_scopes=_select_toc_scopes(toc_paths, ["overview", "method", "architecture", "system"], fallback=4),
        expected_output_type="architecture_mapping",
        priority="high",
        module_id="framework",
        goal_alignment=goals[:3],
    )
    plans.append(root)
    q_index += 1

    templates = [
        (
            "method",
            "What are the main method stages, agent roles, and information flow required by the paper?",
            ["method", "pipeline", "framework", "approach"],
            "pipeline",
        ),
        (
            "module_design",
            "What core software modules are required to represent the paper faithfully in demo form?",
            ["method", "architecture", "implementation"],
            "core_modules",
        ),
        (
            "algorithm",
            "What algorithmic steps, state transitions, or loops are critical and must not be reduced to placeholders?",
            ["algorithm", "procedure", "design", "generation", "validation"],
            "algorithmic_core",
        ),
        (
            "interface_contract",
            "What structured inputs, outputs, schemas, or intermediate representations are required between stages?",
            ["interface", "format", "description", "representation", "library"],
            "interfaces",
        ),
        (
            "data_flow",
            "How does information propagate across stages, and what feedback loops or refinement loops exist?",
            ["flow", "loop", "validation", "optimization", "retrieval"],
            "dataflow",
        ),
        (
            "evaluation_protocol",
            "What evaluation criteria, metrics, or experiments should the demo preserve or expose?",
            ["evaluation", "experiment", "benchmark", "results"],
            "evaluation",
        ),
    ]

    for qtype, question, keywords, module_id in templates:
        if len(plans) >= max_questions:
            break
        plans.append(
            PlanQuestion(
                question_id=_build_question_id(q_index),
                question_depth=1,
                question=question,
                question_type=qtype,
                paper_scopes=_select_toc_scopes(toc_paths, keywords, fallback=3),
                expected_output_type="implementation_brief",
                priority=_priority_label(qtype),
                parent_question_id=root.question_id,
                module_id=module_id,
                goal_alignment=goals[:2],
            )
        )
        q_index += 1

    return {
        "plan": [item.to_dict() for item in plans],
        "goals": goals,
        "planner_notes": {
            "strategy": "paper_grounded_progressive_decomposition",
            "critical_preservation": [
                "planning_plane",
                "scoped_retrieval",
                "design_synthesis",
                "traceability",
                "evaluation",
                "refinement",
            ],
            "paper_collection_id": collection.get("collection_id", ""),
        },
    }


def retrieve_paper_evidence(
    collection: dict[str, Any],
    question: str,
    paper_scopes: list[str] | None = None,
    top_k: int = 6,
) -> list[dict[str, Any]]:
    chunks = _chunk_objects(collection)
    question_tokens = set(_tokenize(question))
    if not question_tokens:
        return []

    scope_values = [scope.lower() for scope in (paper_scopes or []) if scope.strip()]
    scored: list[tuple[float, PaperChunk]] = []

    for chunk in chunks:
        if chunk.type == "toc":
            continue
        heading = chunk.headings_info.lower()
        if scope_values and not any(scope in heading for scope in scope_values):
            continue

        token_set = set(_tokenize(f"{chunk.headings_info} {chunk.content}"))
        overlap = len(question_tokens & token_set)
        if overlap <= 0:
            continue

        score = float(overlap)
        if chunk.type in {"image", "table"}:
            score += 0.3
        score += min(len(chunk.content) / 1400.0, 0.6)
        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    out: list[dict[str, Any]] = []
    for score, chunk in scored[:top_k]:
        out.append(
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
    return out


def merge_paper_evidence(question: str, paper_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    supported_facts: list[str] = []
    for item in paper_evidence[:8]:
        supported_facts.extend(_sentence_split(str(item.get("content", "")))[:2])

    supported_facts = _dedupe_preserve_order(
        [fact for fact in supported_facts if len(fact.split()) >= 5]
    )[:12]

    unresolved: list[str] = []
    if not supported_facts:
        unresolved.append("No direct paper evidence retrieved for this planning question.")

    confidence = max(0.1, min(0.95, 0.35 + 0.06 * len(supported_facts)))
    return {
        "question": question,
        "paper_supported_facts": supported_facts,
        "unresolved_implementation_gaps": unresolved,
        "confidence": round(confidence, 3),
    }


def comprehension_and_design_plane(
    plan_item: dict[str, Any],
    paper_evidence: list[dict[str, Any]],
    merged_evidence: dict[str, Any],
) -> DesignAnswer:
    question_id = str(plan_item.get("question_id", "Q-0000"))
    question = str(plan_item.get("question", "")).strip()
    question_type = str(plan_item.get("question_type", "structure")).strip()
    module_name = str(plan_item.get("module_id", "module")).strip() or "module"

    citations = [
        {
            "chunk_id": item.get("chunk_id", ""),
            "source_type": "paper",
            "headings_info": item.get("headings_info", ""),
            "score": item.get("score", 0.0),
        }
        for item in paper_evidence[:8]
    ]

    brief = {
        "objective": f"Implement demo module `{module_name}` for: {question}",
        "question_type": question_type,
        "module_name": module_name,
        "paper_supported_facts": merged_evidence.get("paper_supported_facts", []),
        "unresolved_implementation_gaps": merged_evidence.get("unresolved_implementation_gaps", []),
        "explicit_support": merged_evidence.get("paper_supported_facts", [])[:8],
        "implementation_recommendations": [
            "Preserve process semantics, not just naming similarity.",
            "Keep critical loops, representations, and stage boundaries explicit.",
            "Use placeholders only for details the paper does not operationalize.",
        ],
        "citations": citations,
        "confidence": merged_evidence.get("confidence", 0.5),
    }

    return DesignAnswer(
        question_id=question_id,
        implementation_brief=brief,
        citations=citations,
        paper_evidence=paper_evidence,
        merged_evidence=merged_evidence,
    )


async def _ollama_chat(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.2,
) -> str:
    payload = {
        "model": model or settings.ollama_code_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    url = f"{settings.ollama_base_url}/api/chat"
    res = await client.post(url, json=payload, timeout=600.0)
    if res.status_code >= 400:
        raise RuntimeError(f"LLM error {res.status_code}: {res.text}")
    data = res.json() or {}
    message = data.get("message") or {}
    return str(message.get("content", "") or "")


async def _generate_module_contract(
    client: httpx.AsyncClient,
    design_answer: DesignAnswer,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Generates a structured contract first. This is important because direct codegen
    from raw paper snippets is one of the root causes of shallow outputs.
    """
    brief = design_answer.implementation_brief
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert research-to-software translator. "
                "Produce strict JSON only. "
                "Design a faithful simplified module contract from paper evidence. "
                "Do not collapse critical algorithmic or planner behavior into vague placeholders. "
                "Output schema: "
                '{"module_name":"...",'
                '"purpose":"...",'
                '"responsibilities":["..."],'
                '"inputs":[{"name":"...","type":"...","description":"..."}],'
                '"outputs":[{"name":"...","type":"...","description":"..."}],'
                '"internal_state":[{"name":"...","type":"...","description":"..."}],'
                '"core_methods":[{"name":"...","purpose":"...","must_preserve":true}],'
                '"must_preserve_semantics":["..."],'
                '"can_be_stubbed":["..."],'
                '"evaluation_hooks":["..."],'
                '"suggested_filename":"..."}'
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question_id": design_answer.question_id,
                    "brief": brief,
                    "paper_evidence": design_answer.paper_evidence,
                },
                indent=2,
            ),
        },
    ]
    raw = await _ollama_chat(client, messages, model=model, temperature=0.1)
    contract = _extract_json_from_text(raw)
    if isinstance(contract, dict) and contract.get("module_name"):
        return contract

    module_name = str(brief.get("module_name", "module"))
    return {
        "module_name": module_name,
        "purpose": brief.get("objective", f"Module for {module_name}"),
        "responsibilities": brief.get("paper_supported_facts", [])[:4],
        "inputs": [{"name": "paper_context", "type": "dict[str, Any]", "description": "Paper-grounded context"}],
        "outputs": [{"name": "result", "type": "dict[str, Any]", "description": "Structured module result"}],
        "internal_state": [],
        "core_methods": [{"name": "run", "purpose": "Execute module logic", "must_preserve": True}],
        "must_preserve_semantics": brief.get("paper_supported_facts", [])[:5],
        "can_be_stubbed": brief.get("unresolved_implementation_gaps", [])[:3],
        "evaluation_hooks": ["traceability_complete"],
        "suggested_filename": f"{_to_slug(module_name)}.py",
    }


async def _generate_module_code(
    client: httpx.AsyncClient,
    design_answer: DesignAnswer,
    module_contract: dict[str, Any],
    language: str = DEFAULT_LANGUAGE,
    model: str | None = None,
) -> CodeArtifact:
    language = (language or DEFAULT_LANGUAGE).strip().lower()
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    brief = design_answer.implementation_brief
    module_name = str(module_contract.get("module_name", brief.get("module_name", "module")))
    suggested_filename = str(module_contract.get("suggested_filename", f"{_to_slug(module_name)}.py")).strip()
    if language == "python" and not suggested_filename.endswith(".py"):
        suggested_filename = f"{Path(suggested_filename).stem}.py"

    messages = [
        {
            "role": "system",
            "content": (
                f"You are an expert {language} engineer implementing a research-faithful demo module. "
                "Generate one self-contained module. "
                "Preserve the planner plane, structured representations, evidence-aware logic, "
                "and critical algorithmic steps. "
                "Use TODO only for details that truly cannot be derived from the evidence. "
                "Include docstrings, type hints where appropriate, and explicit traceability comments. "
                "Return code in a markdown code block."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question_id": design_answer.question_id,
                    "implementation_brief": brief,
                    "module_contract": module_contract,
                    "paper_evidence": design_answer.paper_evidence,
                },
                indent=2,
            ),
        },
    ]

    raw = await _ollama_chat(client, messages, model=model, temperature=0.2)
    code_blocks = _extract_code_blocks(raw)
    main_code = ""
    for block in code_blocks:
        if block["language"] in {language, "python", "typescript", "javascript", "java", "go", "rust", "cpp"}:
            main_code = block["code"]
            break
    if not main_code and code_blocks:
        main_code = code_blocks[0]["code"]

    if not main_code:
        main_code = f'''"""
{module_name} module.

Purpose:
{module_contract.get("purpose", "")}
"""

from __future__ import annotations
from typing import Any


class {_to_slug(module_name).title().replace("_", "")}:
    """
    Research-faithful demo scaffold.
    Critical semantics preserved from paper evidence should be implemented here.
    """

    def __init__(self) -> None:
        self.traceability: list[str] = []

    def run(self, paper_context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the core logic for this module.
        """
        # Critical facts to preserve:
{chr(10).join([f"        # - {fact}" for fact in brief.get("paper_supported_facts", [])[:6]])}
        # TODO: Replace this scaffold with faithful implementation details.
        return {{"status": "scaffold", "module": "{module_name}", "paper_context": paper_context}}
'''

    traceability = {
        "question_id": design_answer.question_id,
        "module_name": module_name,
        "paper_citations": design_answer.citations,
        "paper_supported_facts": brief.get("paper_supported_facts", []),
        "unresolved_gaps": brief.get("unresolved_implementation_gaps", []),
        "must_preserve_semantics": module_contract.get("must_preserve_semantics", []),
        "contract": module_contract,
    }

    return CodeArtifact(
        artifact_id=f"artifact-{uuid.uuid4().hex[:10]}",
        question_id=design_answer.question_id,
        module_name=module_name,
        filename=suggested_filename,
        purpose=str(module_contract.get("purpose", brief.get("objective", ""))),
        code=main_code,
        language=language,
        traceability=traceability,
        evaluation_hints=list(module_contract.get("evaluation_hooks", []) or []),
    )


def evaluation_plane(design_answer: DesignAnswer, artifact: CodeArtifact) -> EvaluationRecord:
    brief = design_answer.implementation_brief
    explicit_support = [str(item) for item in brief.get("paper_supported_facts", []) if str(item).strip()]
    implementation_text = artifact.code

    matched_points: list[dict[str, Any]] = []
    missing_points: list[dict[str, Any]] = []

    impl_tokens = set(_tokenize(implementation_text))
    for statement in explicit_support:
        stmt_tokens = set(_tokenize(statement))
        overlap = len(stmt_tokens & impl_tokens) / max(len(stmt_tokens), 1)
        row = {"paper_statement": statement, "overlap_score": round(overlap, 3)}
        if overlap >= 0.18:
            matched_points.append(row)
        else:
            missing_points.append({**row, "issue_type": "not_explicitly_reflected"})

    if not explicit_support:
        status = "insufficient_paper_information"
    elif not missing_points:
        status = "faithful_match"
    elif matched_points:
        status = "partial_match"
    else:
        status = "mismatch"

    coverage_ratio = len(matched_points) / max(len(explicit_support), 1)
    confidence = max(0.05, min(0.99, 0.35 + coverage_ratio * 0.6 - 0.08 * len(missing_points)))

    evaluation = {
        "faithfulness_status": status,
        "matched_points": matched_points,
        "missing_points": missing_points,
        "paper_faithfulness": {
            "status": status,
            "coverage_ratio": round(coverage_ratio, 3),
            "confidence": round(confidence, 3),
        },
        "remaining_ambiguity": brief.get("unresolved_implementation_gaps", []),
        "next_action_recommendation": (
            "move_to_next_module" if status == "faithful_match" else "refine_current_module"
        ),
    }
    return EvaluationRecord(question_id=design_answer.question_id, evaluation=evaluation)


def refinement_plane(plan: list[dict[str, Any]], evaluations: list[EvaluationRecord]) -> dict[str, Any]:
    plan_by_id = {str(item.get("question_id")): item for item in plan if isinstance(item, dict)}

    existing_ids = [str(item.get("question_id")) for item in plan if str(item.get("question_id", "")).startswith("Q-")]
    max_numeric_id = 0
    for qid in existing_ids:
        try:
            max_numeric_id = max(max_numeric_id, int(qid.split("-")[-1]))
        except Exception:
            pass

    new_questions: list[dict[str, Any]] = []
    refinement_decisions: list[dict[str, Any]] = []

    for record in evaluations:
        current = plan_by_id.get(record.question_id)
        if not current:
            continue

        status = str(record.evaluation.get("faithfulness_status", "partial_match"))
        if status == "faithful_match":
            current["status"] = "completed"
            refinement_decisions.append(
                {"question_id": record.question_id, "decision": "module_complete_move_to_next"}
            )
            continue

        current["status"] = "refined"
        max_numeric_id += 1
        followup_id = _build_question_id(max_numeric_id)
        followup = PlanQuestion(
            question_id=followup_id,
            question_depth=int(current.get("question_depth", 0)) + 1,
            question=f"Refine `{current.get('module_id', 'module')}`: what critical paper semantics remain underimplemented?",
            question_type="implementation_gap",
            paper_scopes=list(current.get("paper_scopes", [])),
            expected_output_type="implementation_brief",
            priority="high",
            status="pending",
            parent_question_id=str(current.get("question_id", "")),
            module_id=str(current.get("module_id", "module")),
            goal_alignment=list(current.get("goal_alignment", [])),
        ).to_dict()
        new_questions.append(followup)
        refinement_decisions.append(
            {"question_id": record.question_id, "decision": "add_followup_due_to_gaps", "new_question_id": followup_id}
        )

    plan.extend(new_questions)
    return {
        "updated_plan": plan,
        "new_questions": new_questions,
        "refinement_decisions": refinement_decisions,
    }


async def _generate_project_readme(
    client: httpx.AsyncClient,
    paper_title: str,
    plan: list[dict[str, Any]],
    artifacts: list[CodeArtifact],
    evaluations: list[EvaluationRecord],
    model: str | None = None,
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a technical writer. Generate a concise but precise README.md for a research-faithful "
                "demo implementation. Include overview, module structure, setup, usage, known limitations, "
                "and traceability notes."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "paper_title": paper_title,
                    "plan": plan,
                    "artifacts": [artifact.to_dict() for artifact in artifacts],
                    "evaluations": [record.to_dict() for record in evaluations],
                },
                indent=2,
            ),
        },
    ]
    raw = await _ollama_chat(client, messages, model=model, temperature=0.2)
    code_blocks = _extract_code_blocks(raw)
    for block in code_blocks:
        if block["language"] in {"markdown", "md", "text"}:
            return block["code"]

    if "# " in raw:
        return raw

    module_lines = "\n".join([f"- `{artifact.filename}`: {artifact.purpose}" for artifact in artifacts])
    return f"""# Demo Implementation: {paper_title}

