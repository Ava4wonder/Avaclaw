#!/usr/bin/env python3
"""
compact_headings_with_chunking.py

Based on File A:
- KEEP ALL heading detection + hierarchical breadcrumb logic unchanged
- ONLY add chunking logic to output:
  {
    "doc_info": {...},
    "chunks": [ ... ]
  }
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

import fitz  # PyMuPDF
from langchain_community.chat_models import ChatOllama

logger = logging.getLogger(__name__)

# ---------------------------
# 全局配置
# ---------------------------
OLLAMA_BASE_URL = os.getenv("DEFAULT_OLLAMA", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("DEFAULT_CHAT", "qwen3:30b")

# ---------------------------
# 数据结构定义
# ---------------------------
@dataclass
class HeadingMetadata:
    """存储标题级别决策所需的元数据"""
    text: str
    font_size: float
    is_bold: bool
    bbox: fitz.Rect
    num_segments: int  # 数字前缀的段数 (3.1.2 → 3段)
    dot_count: int     # 数字前缀的点数量 (3.1.2 → 2个点)
    alignment: str     # 'left', 'center', 'right', 'left_indented'
    has_colon_hyphen: bool  # 是否包含冒号/连字符（子标题标识）
    font_family: str   # 字体家族名称
    text_color: Optional[int]  # text color (PyMuPDF int RGB)
    page_num: int      # 标题所在页码
    vertical_gap_to_next_block: float  # 到下一个块的垂直间距
    block_id: Union[int, Tuple[int, int]]  # 块标识符
    case_style: str    # 大小写样式: ALLCAPS/TitleCase/SentenceCase


# ---------------------------
# 通用工具函数（File A 原样保留）
# ---------------------------
def _norm_text(s: str) -> str:
    """标准化文本（去除软连字符、多余空格）"""
    return " ".join((s or "").replace("\u00ad", "").split()).strip()

def _round_size(x: float) -> float:
    """四舍五入字体大小到1位小数"""
    return round(float(x), 1)

def _is_bold(span: Dict) -> bool:
    """判断文本是否为粗体"""
    font = (span.get("font") or "").lower()
    flags = span.get("flags", 0)
    return ("bold" in font) or (flags & (2**4))

def _get_table_bboxes_fallback(page: fitz.Page) -> List[fitz.Rect]:
    """获取页面中的表格边界框（PyMuPDF 原生检测）"""
    try:
        tables = page.find_tables()
        return [fitz.Rect(t.bbox) for t in getattr(tables, "tables", [])]
    except Exception:
        return []

def _in_any_table(span_rect: fitz.Rect, table_rects: Sequence[fitz.Rect]) -> bool:
    """判断文本是否在表格内"""
    for tr in table_rects:
        if (span_rect & tr).get_area() > 0.5 * span_rect.get_area():
            return True
    return False

def _get_line_data(l: Dict) -> Tuple[str, Tuple[float, bool, str, Optional[int]], fitz.Rect]:
    """提取单行文本的内容、样式和边界框"""
    spans = [s for s in (l.get("spans", []) or []) if _norm_text(s.get("text", ""))]
    if not spans:
        return "", (0.0, False, "", None), fitz.Rect()

    raw_text = "".join([s.get("text", "") for s in spans])
    max_size = _round_size(max(float(s.get("size", 0.0)) for s in spans))
    bold_all = all(_is_bold(s) for s in spans)
    total_chars = sum(len(s.get("text", "")) for s in spans)
    bold_chars = sum(len(s.get("text", "")) for s in spans if _is_bold(s))
    bold_80p = bold_chars >= 0.8 * total_chars if total_chars > 0 else False

    font_family = (spans[0].get("font") or "").strip()
    color_counts: Dict[int, int] = {}
    for s in spans:
        color = s.get("color")
        if color is None:
            continue
        color_counts[color] = color_counts.get(color, 0) + len(s.get("text", ""))
    text_color = max(color_counts.items(), key=lambda kv: kv[1])[0] if color_counts else None

    lb = fitz.Rect(l.get("bbox", spans[0]["bbox"]))
    for s in spans[1:]:
        lb |= fitz.Rect(s["bbox"])

    return _norm_text(raw_text), (max_size, bool(bold_80p), font_family, text_color), lb

def _merge_same_row_lines(
    items: List[Dict[str, Any]],
    y_tol: float = 1.5,
    x_gap_tol: float = 30.0,
) -> List[Dict[str, Any]]:
    if not items:
        return items

    def y_center(r: fitz.Rect) -> float:
        return (r.y0 + r.y1) / 2.0

    def is_number_token(t: str) -> bool:
        t = _norm_text(t)
        return bool(re.fullmatch(r"[\(\[]?(?:\d+(?:\.\d+)*|[IVXLCDM]+|[A-Z])[\)\]]?\.?", t))

    # 1) row clustering by y_center (NOT rounding)
    items_y = sorted(items, key=lambda d: y_center(d["rect"]))
    rows: List[Dict[str, Any]] = []
    for it in items_y:
        yc = y_center(it["rect"])
        placed = False
        for row in rows:
            if abs(yc - row["yc"]) <= y_tol:
                row["items"].append(it)
                # update running center to be stable
                row["yc"] = (row["yc"] * (len(row["items"]) - 1) + yc) / len(row["items"])
                placed = True
                break
        if not placed:
            rows.append({"yc": yc, "items": [it]})

    # 2) within each row, sort by x0 then merge
    merged_all: List[Dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: r["yc"]):
        row_items = sorted(row["items"], key=lambda d: d["rect"].x0)

        merged_row: List[Dict[str, Any]] = []
        for cur in row_items:
            if not merged_row:
                merged_row.append(cur)
                continue

            prev = merged_row[-1]
            same_style = (cur["style"] == prev["style"])
            x_gap = cur["rect"].x0 - prev["rect"].x1

            # allow larger gap if the LEFT fragment is numbering
            close_enough = (x_gap <= x_gap_tol) or is_number_token(prev["text"])

            if same_style and close_enough:
                prev["text"] = _norm_text(prev["text"] + " " + cur["text"])
                prev["rect"] |= cur["rect"]
            else:
                merged_row.append(cur)

        merged_all.extend(merged_row)

    return merged_all


def _get_alignment(bbox: fitz.Rect, page_width: float) -> str:
    """基于边界框位置判断文本对齐方式"""
    bw = max(0.0, bbox.x1 - bbox.x0)
    text_center_x = (bbox.x0 + bbox.x1) / 2
    page_center_x = page_width / 2
    tolerance = page_width * 0.1  # 10% 容差


    if abs(text_center_x - page_center_x) < tolerance:
        return "center"
    elif bbox.x0 < page_width * 0.2 and bw < page_width * 0.55:
        return "left"
    elif bbox.x1 > page_width * 0.8 and bw < page_width * 0.55:
        return "right"
    else:
        return "center"
    
def _extract_number_prefix_metrics(text: str) -> Tuple[int, int]:
    """
    提取数字前缀的度量指标（严格验证）
    返回: (num_segments, dot_count)
    - num_segments: 前缀段数 (3.1.2 → 3)
    - dot_count: 点的数量 (3.1.2 → 2)
    无有效前缀时返回 (0, 0)
    """
    p = re.compile(r'^(?P<prefix>(\d+(?:\.\d+)*\.?))')

    match = p.match(text)
    if not match:
        return 0, 0

    prefix = match.groups()[0].strip('.')
    dot_count = prefix.count('.')
    num_segments = dot_count + 1
    return num_segments, dot_count

def _extract_number_prefix_segments(text: str) -> List[int]:
    """提取数字前缀的分段列表（仅支持阿拉伯数字点分段）"""
    match = re.match(r"^(?P<prefix>\d+(?:\.\d+)*)\.?", text.strip())
    if not match:
        return []
    prefix = match.group("prefix")
    segments: List[int] = []
    for part in prefix.split("."):
        try:
            segments.append(int(part))
        except ValueError:
            return []
    return segments

def _extract_number_depth_value(text: str, num_segments: int) -> Optional[int]:
    """提取指定深度的编号值（k段编号取第k段值）"""
    segments = _extract_number_prefix_segments(text)
    if not segments or len(segments) != num_segments:
        return None
    return segments[-1]

def _update_numbering_state(
    num_segments: int,
    depth_value: Optional[int],
    head_values: Dict[int, int],
    console_log: List[str],
    page_num: int,
    text: str,
) -> Dict[str, bool]:
    """更新编号进度并检测跳跃"""
    state = {
        "has_numbering": False,
        "jump": False,
        "increment": False,
        "repeat": False,
        "first": False,
    }
    if num_segments <= 0 or depth_value is None:
        return state
    state["has_numbering"] = True
    if num_segments not in head_values:
        head_values[num_segments] = depth_value
        state["first"] = True
        return state
    prev_value = head_values[num_segments]
    if depth_value == prev_value:
        state["repeat"] = True
        return state
    if depth_value == prev_value + 1:
        head_values[num_segments] = depth_value
        state["increment"] = True
        return state
    state["jump"] = True
    console_log.append(
        f"[编号跳跃] 页码{page_num}: 深度{num_segments} 值{depth_value} "
        f"不符合 {prev_value} 或 {prev_value + 1} - 标题: {text}"
    )
    return state

def _old_extract_number_prefix_metrics(text: str) -> Tuple[int, int]:
    """
    提取数字前缀的度量指标（严格验证）
    返回: (num_segments, dot_count)
    - num_segments: 前缀段数 (3.1.2 → 3)
    - dot_count: 点的数量 (3.1.2 → 2)
    无有效前缀时返回 (0, 0)
    """
    roman = r"(?=[MDCLXVI])M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"

    p = re.compile(
        rf"^("
        rf"(?:"
        rf"\d+(?:\.\d+)*\.?"               # 数字格式: 3 / 3.1 / 3.1.2 / 3.
        rf"|{roman}\.?"                    # 罗马数字: IV / IV.
        rf"|[A-Z]\.(?:\d+(?:\.\d+)*)?"     # 字母+数字: A. / A.1 / A.1.2
        rf")"
        rf")"
        rf"(?:"
        rf"(?:\s+|(?<=\.)(?=[A-Za-z&]))"   # 分隔符: 空格 或 点后直接跟字母
        rf"(.+)"
        rf")?$"
    )
    match = p.match(text)
    if not match:
        return 0, 0

    prefix = match.groups()[0].strip('.')
    dot_count = prefix.count('.')
    num_segments = dot_count + 1
    return num_segments, dot_count

def _detect_case_style(text: str) -> str:
    """
    检测文本的大小写样式
    返回: ALLCAPS / TitleCase / SentenceCase
    """
    clean_text = re.sub(r"^[\dA-Z.]+\s+", "", text).strip()
    if not clean_text:
        return "Unknown"

    if clean_text.isupper():
        return "ALLCAPS"
    if clean_text[0].isupper() and clean_text[1:].islower():
        return "SentenceCase"
    return "TitleCase"

def _calculate_vertical_gap(curr_bbox: fitz.Rect, next_bbox: Optional[fitz.Rect]) -> float:
    """计算当前块到底部到下一个块顶部的垂直间距"""
    if next_bbox is None:
        return 0.0
    return next_bbox.y0 - curr_bbox.y1

def _is_heading_like(text: str, style: Tuple[float, bool, str], body_size: float) -> bool:
    """判断文本是否具备标题特征（用于避免过滤长标题）"""
    prefix_pattern = r"^(\d+\.){1,3}|\d+|[A-Z]\."
    if re.search(prefix_pattern, text.strip()):
        return True
    if style[0] > body_size + 1.0:
        return True
    if style[1] and style[0] >= body_size:
        return True
    clean_text = re.sub(r"^[\dA-Z.]+\s+", "", text).strip()
    if clean_text.isupper() or (clean_text and clean_text[0].isupper() and len(clean_text.split()) > 1):
        return True
    return False

def _has_filtered_punctuation(text: str, style: Optional[Tuple[float, bool, str]] = None, body_size: float = 12.0) -> bool:
    """
    重构后的过滤规则（避免过滤长标题）
    """
    if not text:
        return True
    if text[-1] == '.' or text[-1] == ',':
        return True
    if len(text) > 70:
        use_style = style if style is not None else (0.0, False, "", None)
        # if _is_heading_like(text, use_style, body_size):
        if use_style[1]:
            return False
        else:
            return True
    return False


# ---------------------------
# Step 1 (File A 原样保留)
# ---------------------------
def init_logger(log_path: str) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def extract_headings_first5pages(pdf_path: str, output_json: str) -> None:
    doc = fitz.open(pdf_path)
    max_pages = min(5, len(doc))

    headings = []
    all_font_sizes = []
    table_geom_by_page = []

    for page_idx in range(max_pages):
        page = doc[page_idx]
        t_geom = _get_table_bboxes_fallback(page)
        table_geom_by_page.append(t_geom)

        for b in page.get_text("dict").get("blocks", []):
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if not _in_any_table(fitz.Rect(s["bbox"]), t_geom):
                        all_font_sizes.append(_round_size(s.get("size", 0.0)))

    body_size = median(all_font_sizes) if all_font_sizes else 12.0

    for page_idx in range(max_pages):
        page = doc[page_idx]
        page_num = page_idx + 1
        page_width = page.rect.width
        t_geom = table_geom_by_page[page_idx]
        page_dict = page.get_text("dict")

        for block_idx, b in enumerate(page_dict.get("blocks", [])):
            if "lines" not in b:
                continue

            block_lines_data = []
            for l in b["lines"]:
                txt, style, r = _get_line_data(l)
                if txt and not _in_any_table(r, t_geom):
                    if style[0] > body_size * 1.05 or (style[0] > 0.9 * body_size and style[1]):
                        block_lines_data.append({
                            "text": txt,
                            "style": style,
                            "rect": r,
                            "font_size": style[0],
                            "is_bold": style[1],
                            "font_family": style[2],
                            "text_color": style[3]
                        })

            block_lines_data = _merge_same_row_lines(block_lines_data)

            for line_data in block_lines_data:
                if _has_filtered_punctuation(line_data["text"], line_data["style"], body_size):
                    # print(f"Filtered out non-heading line: {line_data['text']}")
                    continue

                bbox = line_data["rect"]
                heading = {
                    "text": line_data["text"],
                    "page_num": page_num,
                    "font_size": line_data["font_size"],
                    "is_bold": line_data["is_bold"],
                    "alignment": _get_alignment(bbox, page_width),
                    "has_colon_hyphen": ":" in line_data["text"] or "-" in line_data["text"],
                    "font_family": line_data["font_family"],
                    "text_color": line_data["text_color"],
                    "bbox": {
                        "x0": bbox.x0,
                        "y0": bbox.y0,
                        "x1": bbox.x1,
                        "y1": bbox.y1
                    },
                    "vertical_gap_to_next_block": 0.0,
                    "block_id": (page_idx, block_idx),
                    "case_style": _detect_case_style(line_data["text"])
                }
                headings.append(heading)

    output_data = {
        "file": os.path.basename(pdf_path),
        "headings": headings
    }

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    doc.close()


# ---------------------------
# Step 2 (File A 原样保留)
# ---------------------------
def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def short_heading_record(h: Dict[str, Any]) -> Dict[str, Any]:
    bbox = h.get("bbox") or {}
    return {
        "text": normalize_ws(h.get("text", ""))[:240],
        "page_num": h.get("page_num"),
        "font_size": h.get("font_size"),
        "is_bold": h.get("is_bold"),
        "alignment": h.get("alignment"),
        "has_colon_hyphen": h.get("has_colon_hyphen"),
        "font_family": h.get("font_family"),
        "text_color": h.get("text_color"),
        "bbox": {
            "x0": bbox.get("x0"),
            "y0": bbox.get("y0"),
            "x1": bbox.get("x1"),
            "y1": bbox.get("y1"),
        },
        "vertical_gap_to_next_block": h.get("vertical_gap_to_next_block"),
    }

def compress_context(headings: List[Dict[str, Any]], max_items: int = 80) -> List[Dict[str, Any]]:
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for h in headings:
        page = h.get("page_num", 999)
        bold = 1.0 if h.get("is_bold") else 0.0
        center = 1.0 if (h.get("alignment") == "center") else 0.0
        fs = float(h.get("font_size") or 0.0)

        score = (10.0 / max(page, 1)) + 1.5 * bold + 1.0 * center + 0.05 * fs
        scored.append((score, h))

    scored.sort(key=lambda x: x[0], reverse=True)
    kept = [short_heading_record(h) for _, h in scored[:max_items]]
    kept_in_order = [short_heading_record(h) for h in headings[: min(len(headings), 25)]]

    seen = set()
    merged: List[Dict[str, Any]] = []
    for item in kept_in_order + kept:
        key = (item.get("page_num"), item.get("text"))
        if key not in seen and item.get("text"):
            seen.add(key)
            merged.append(item)

    return merged[:max_items]

def safe_json_extract(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    snippet = m.group(0)
    try:
        return json.loads(snippet)
    except Exception:
        return None

def infer_metadata(
    input_json_path: str,
    output_json_path: str,
    model: str = OLLAMA_MODEL,
    temperature: float = 0.2,
) -> None:
    chat = ChatOllama(
        model=model,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
    )

    SYSTEM_PROMPT = """You are a document-structure analyst.
    You receive extracted "headings blocks" (mostly bold/centered lines from a PDF's first pages).
    Your job: infer *metadata attributes* about:
    (A) the document title (as normalized metadata, not long text)
    (B) the Level-1 heading style/pattern used in the document
    (C) the level-1 heading usually has a larger font size than body text and other headings, is often bolded, and may be centered.

    Rules:
    - Output MUST be VALID JSON only (no markdown, no commentary).
    - Do NOT output long text excerpts. Only compact metadata attributes.
    - Do NOT misunderstand document title vs. headings, headings are shown from body pages.
    - Use best-effort inference from visual/layout cues: bold/center, font family, relative position (bbox y0), early pages.
    - If uncertain, set fields to null and include a confidence score 0..1.
    """

    USER_PROMPT_TEMPLATE = """Context (headings blocks, first pages):
    {context_json}

    Task:
    Infer metadata attributes for:
    1) Document title metadata pattern
    2) Level-1 heading (First Level Chapter title) metadata pattern
    3) Level-2 heading (Second Level heading title) metadata pattern (if possible)
    Note: for "case_style", you should infer from the text captilization feature: `ALLCAPS` means Every letter of every word is uppercase, `TitleCase` means First letter of major words uppercase, SentenceCase means only first letter of first word uppercase

    Output JSON schema (STRICT):
    {{
    "source_file": "<string>",
    "doc_title": {{
        "normalized_title": "<string|null>",
        "doc_type": "<string|null>",
        "project_or_subject": "<string|null>",
        "issuer_or_agency": "<string|null>",
        "country_or_region": "<string|null>",
        "keywords": ["<string>", "..."],
        "confidence": <number>
    }},
    "level1_heading": {{
        "style": {{
        "font_size": <number|null>,
        "is_bold_usually": <boolean|null>,
        "alignment_usually": "<string|null>",
        "font_family_mode": "<string|null>",
        "num_segments_usually": <number|null>,
        "case_style": "<string|null>"
        }},
        "numbering_style": "<string|null>",
        "common_position": {{
        "page_bias": "<number|null>"
        }},
        "example_tokens": ["<string>", "<string>", "<string>"],
        "confidence": <number>
    }}
    "level2_heading": {{
        "style": {{
        "font_size": <number|null>,
        "is_bold_usually": <boolean|null>,
        "alignment_usually": "<string|null>",
        "font_family_mode": "<string|null>",
        "case_style": "<string|null>"
        }},
        "numbering_style": "<string|null>",
        "common_position": {{
        "page_bias": "<number|null>"
        }},
        "example_tokens": ["<string>", "<string>", "<string>"],
        "confidence": <number>
    }}
    }}

    Important constraints:
    - Keep normalized_title <= 140 chars
    - keywords must be short (1-4 words each)
    - example_tokens are tiny and non-verbatim-ish (no long copying)
    - Return JSON only.
    """

    data = json.load(open(input_json_path, "r", encoding="utf-8"))
    source_file = data.get("file") or os.path.basename(input_json_path)
    headings = data.get("headings") or []

    compact = compress_context(headings, max_items=80)
    context_obj = {
        "file": source_file,
        "headings_compact": compact,
    }
    context_json = json.dumps(context_obj, ensure_ascii=False, indent=2)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(context_json=context_json),
        },
    ]

    resp = chat.invoke(messages)
    raw = getattr(resp, "content", str(resp)).strip()
    print(f"[LLM Raw Output]: {raw}")
    parsed = safe_json_extract(raw)
    # print(f"[Parsed JSON]: {parsed}")

    if parsed is None:
        parsed = {
            "source_file": source_file,
            "error": "Failed to parse model output as JSON",
            "raw_model_output": raw[:4000],
        }

    parsed.setdefault("source_file", source_file)

    try:
        kws = parsed.get("doc_title", {}).get("keywords", [])
        if isinstance(kws, list):
            parsed["doc_title"]["keywords"] = [normalize_ws(str(x))[:40] for x in kws[:8]]
    except Exception:
        pass

    try:
        ex = parsed.get("level1_heading", {}).get("example_tokens", [])
        if isinstance(ex, list):
            parsed["level1_heading"]["example_tokens"] = [normalize_ws(str(x))[:40] for x in ex[:3]]
    except Exception:
        pass

    try:
        ex2 = parsed.get("level2_heading", {}).get("example_tokens", [])
        if isinstance(ex2, list):
            parsed["level2_heading"]["example_tokens"] = [normalize_ws(str(x))[:40] for x in ex2[:3]]
    except Exception:
        pass

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)


# ---------------------------
# Step 3 helpers (File A 原样保留)
# ---------------------------
def _load_inferred_metadata(json_path: str) -> Dict[str, Any]:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

def _match_h1_style(meta: HeadingMetadata, h1_style: Dict[str, Any]) -> bool:
    if not h1_style:
        return False

    font_size_match = abs(meta.font_size - (h1_style.get("font_size") or 0)) <= 1.0
    bold_match = meta.is_bold == h1_style.get("is_bold_usually")
    align_meta = meta.alignment.replace("_indented", "")
    align_h1 = (h1_style.get("alignment_usually") or "").lower()
    alignment_match = align_meta == align_h1 or (align_h1 == "unknown" and align_meta in ["left", "center", "right"])
    num_segments_h1 = h1_style.get("num_segments_usually")
    num_segments_match = False
    if num_segments_h1 is not None:
        num_segments_match = meta.num_segments == num_segments_h1

    font_family_match = True
    if h1_style.get("font_family_mode") and h1_style.get("font_family_mode") != "null":
        font_family_match = h1_style["font_family_mode"].lower() in meta.font_family.lower()

    # case_match = meta.case_style == h1_style.get("case_style") or h1_style.get("case_style") == "null"
    case_match = True
    color_match = True
    if h1_style.get("text_color") is not None or meta.text_color is not None:
        color_match = meta.text_color == h1_style.get("text_color")
    return all([font_size_match, bold_match, alignment_match, font_family_match, case_match, color_match, num_segments_match])

def _match_heading_style_numseg(meta: HeadingMetadata, ctx_style: Dict[str, Any]) -> bool:
    if not ctx_style:
        return False
    if meta.num_segments != ctx_style.get("num_segments", -1):
        return False
    if abs(meta.font_size - (ctx_style.get("font_size") or 0)) > 2.0:
        return False
    if meta.is_bold != ctx_style.get("is_bold"):
        return False

    align_meta = meta.alignment.replace("_indented", "")
    # align_ctx = ctx_style.get("alignment", "").replace("_indented", "")
    align_ctx = (ctx_style.get("alignment") or "").replace("_indented", "")
    if align_meta != align_ctx:
        return False

    # if ctx_style.get("font_family") and ctx_style["font_family"].lower() not in meta.font_family.lower():
    #     return False
    if ctx_style.get("text_color") is not None and ctx_style.get("text_color") != meta.text_color:
        return False
    return True


def _match_heading_style(meta: HeadingMetadata, ctx_style: Dict[str, Any]) -> bool:
    if not ctx_style:
        return False
    if meta.num_segments != ctx_style.get("num_segments", -1):
        return False
    if abs(meta.font_size - (ctx_style.get("font_size") or 0)) > 1.0:
        return False
    if meta.is_bold != ctx_style.get("is_bold"):
        return False

    align_meta = meta.alignment.replace("_indented", "")
    align_ctx = ctx_style.get("alignment", "").replace("_indented", "")
    if align_meta != align_ctx:
        return False

    if ctx_style.get("font_family") and ctx_style["font_family"].lower() not in meta.font_family.lower():
        return False
    if ctx_style.get("text_color") is not None and ctx_style.get("text_color") != meta.text_color:
        return False
    return True


# ============================================================
# Chunking additions ONLY (heading logic remains untouched)
# ============================================================

def _doc_fingerprint(pdf_path: str) -> str:
    """Stable doc fingerprint for chunks."""
    abs_path = os.path.abspath(pdf_path)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, abs_path))

def _chunk_uuid(doc_fp: str, idx: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_fp}:{idx}"))

def _block_text_full(block: Dict[str, Any]) -> str:
    """Extract full block text (normalized) from PyMuPDF block."""
    if "lines" not in block:
        return ""
    out_lines: List[str] = []
    for l in block.get("lines", []) or []:
        t, _, _ = _get_line_data(l)
        if t:
            out_lines.append(t)
    return _norm_text("\n".join(out_lines))

def _rect_to_bbox_list(r: fitz.Rect) -> List[float]:
    return [float(r.x0), float(r.y0), float(r.x1), float(r.y1)]

def _is_table_block(block: Dict[str, Any], block_rect: fitz.Rect, table_rects: Sequence[fitz.Rect]) -> bool:
    """Table block if text is mostly enclosed by table rectangles."""
    if not table_rects:
        return False
    if block_rect.get_area() <= 0:
        return False
    if "lines" in block:
        total = 0
        hit = 0
        for l in block.get("lines", []) or []:
            txt, _, r = _get_line_data(l)
            if not txt:
                continue
            total += 1
            if _in_any_table(r, table_rects):
                hit += 1
        if total > 0 and hit / total >= 0.6:
            return True
    return _in_any_table(block_rect, table_rects)

def _classify_block(block: Dict[str, Any], block_rect: fitz.Rect, table_rects: Sequence[fitz.Rect]) -> str:
    """
    Return one of: TEXT / TABLE / FIGURE
    """
    # PyMuPDF: image blocks usually have no "lines" and type==1
    if "lines" not in block:
        return "FIGURE"
    if _is_table_block(block, block_rect, table_rects):
        return "TABLE"
    return "TEXT"

def check_filter_condition(heading_text: str, heading_meta: HeadingMetadata) -> bool:
    """
    User-specified hook:
    - If True: do NOT split chunk, treat heading as body text.
    - If False: split chunk boundary at this heading.
    Default: False (split on all headings).
    """
    return False


def process_pdf_to_chunk_json(
    input_pdf: str,
    inferred_metadata_json: str,
    output_json_path: str,
    output_console: bool = False,
) -> None:
    """
    Keep heading logic identical to File A processing.
    Only add chunking output.
    """

    inferred_meta = _load_inferred_metadata(inferred_metadata_json)
    h1_style = inferred_meta.get("level1_heading", {}).get("style", {})
    h1_page_bias = int(inferred_meta.get("level1_heading", {}).get("common_position", {}).get("page_bias", 1))

    doc = fitz.open(input_pdf)
    doc_fp = _doc_fingerprint(input_pdf)

    # ---------------------------
    # Baseline calculation (File A logic preserved)
    # ---------------------------
    all_font_sizes = []
    table_geom_by_page = []

    for page in doc:
        t_geom = _get_table_bboxes_fallback(page)
        table_geom_by_page.append(t_geom)

        for b in page.get_text("dict").get("blocks", []):
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if not _in_any_table(fitz.Rect(s["bbox"]), t_geom):
                        all_font_sizes.append(_round_size(s.get("size", 0.0)))

    body_size = median(all_font_sizes) if all_font_sizes else 12.0

    # ---------------------------
    # First pass: heading style set (File A logic preserved)
    # ---------------------------
    heading_styles_set: Set[Tuple[float, bool, str, Optional[int]]] = set()
    for idx, page in enumerate(doc):
        t_geom = table_geom_by_page[idx]
        for b in page.get_text("dict").get("blocks", []):
            for l in b.get("lines", []):
                txt, style, r = _get_line_data(l)
                if txt and not _in_any_table(r, t_geom):
                    if style[0] > body_size * 1.05 or (style[0] >= body_size and style[1] is True):
                        heading_styles_set.add(style)

    # ---------------------------
    # Heading context init (File A logic preserved)
    # ---------------------------
    H_ctx: Dict[int, Dict[str, Any]] = {}
    H_state = 1
    previous_meta: Optional[HeadingMetadata] = None
    sorted_styles = sorted(list(heading_styles_set), key=lambda x: (x[0], x[1]), reverse=True)
    style_to_base_level = {st: i + 1 for i, st in enumerate(sorted_styles)}
    breadcrumb_stack: List[str] = []
    head_values: Dict[int, int] = {}
    numseg_to_hctx: Dict[int, int] = {}
    console_log: List[str] = []

    if h1_style and h1_style.get("font_size"):
        H_ctx[1] = {
            "font_size": h1_style.get("font_size"),
            "is_bold": h1_style.get("is_bold_usually"),
            "alignment": h1_style.get("alignment_usually"),
            "font_family": h1_style.get("font_family_mode"),
            "text_color": h1_style.get("text_color"),
            "case_style": h1_style.get("case_style"),
            "num_segments": h1_style.get("num_segments_usually"),
        }

    # ============================================================
    # Chunking state (NEW)
    # ============================================================
    chunks: List[Dict[str, Any]] = []
    curr_chunk: Dict[str, Any] = {}
    curr_H_context = ""  # " > ".join(breadcrumb_stack)

    # bbox tracking on CURRENT PAGE ONLY of the current chunk
    curr_page_num: Optional[int] = None
    curr_bbox: Optional[fitz.Rect] = None
    curr_body_char_count: int = 0
    chunk_index = 0
    running_continuation_flag = False

    # ----------------------------
    # ToC state (NEW)
    # ----------------------------
    toc_root: List[Dict[str, Any]] = []
    toc_stack: List[Dict[str, Any]] = []

    def toc_add(level: int, title: str, page: int) -> None:
        node = {
            "title": _norm_text(title),
            "page": int(page),
            "level": int(level),
            "children": []
        }

        if level <= 1 or not toc_stack:
            toc_root.append(node)
            toc_stack[:] = [node]
            return

        while len(toc_stack) >= level:
            toc_stack.pop()

        if len(toc_stack) >= level - 1:
            parent = toc_stack[level - 2]
        else:
            parent = toc_stack[-1]
        parent["children"].append(node)
        toc_stack.append(node)

    def _refresh_curr_H_context() -> str:
        return " > ".join([x for x in breadcrumb_stack if _norm_text(x)])

    def flush_chunk() -> None:
        """Re-init empty curr_chunk, set text to current breadcrumb."""
        nonlocal curr_chunk, curr_page_num, curr_bbox, curr_body_char_count, curr_H_context
        curr_H_context = _refresh_curr_H_context() + " > "
        curr_chunk = {
            "text": curr_H_context,
            "sec_name": _refresh_curr_H_context(),
        }
        curr_page_num = None
        curr_bbox = None
        curr_body_char_count = 0

    def add_chunk_if_valid() -> None:
        """Append finalized chunk into chunks if it has body text beyond breadcrumb."""
        nonlocal chunks, curr_chunk, chunk_index, curr_page_num, curr_bbox, curr_body_char_count, running_continuation_flag

        if curr_body_char_count <= 0:
            return

        # bbox from current page only (union of related blocks)
        if curr_bbox is None or curr_page_num is None:
            bbox = [0.0, 0.0, 0.0, 0.0]
            orig_size = [0.0, 0.0]
            page_number = 1
        else:
            bbox = [float(curr_bbox.x0), float(curr_bbox.y0), float(curr_bbox.x1), float(curr_bbox.y1)]
            page = doc[curr_page_num - 1]
            orig_size = [float(page.rect.width), float(page.rect.height)]
            page_number = curr_page_num

        chunk_id = _chunk_uuid(doc_fp, chunk_index)
        chunk_index += 1

        chunk_obj = {
            "chunk_id": chunk_id,
            "type": "TEXT",
            "text": curr_chunk.get("text", ""),
            "sec_name": curr_chunk.get("sec_name", ""),
            "metadata": {
                "CONTINUATION": running_continuation_flag
            },
            "page_number": int(page_number),
            "doc_fingerprint": doc_fp,
            "bbox": bbox,
            "orig_size": orig_size
        }
        chunks.append(chunk_obj)

    def append_block_to_chunk(block_text: str, block_rect: fitz.Rect, page_num: int, block_type: str) -> None:
        """
        Append content to curr_chunk['text'] following rules:
        - TEXT/TABLE: append text
        - FIGURE: append placeholder [!Figure]
        Track bbox only on current page.
        """
        nonlocal curr_chunk, curr_page_num, curr_bbox, curr_body_char_count

        if not curr_chunk:
            flush_chunk()

        piece = ""
        if block_type == "FIGURE":
            piece = "[!Figure]"
        else:
            piece = _norm_text(block_text)

        if not piece:
            return

        # If this is the first appended body content -> set first page
        if curr_page_num is None:
            curr_page_num = page_num

        # bbox updates ONLY when current block is on current page of chunk
        if page_num == curr_page_num:
            if curr_bbox is None:
                curr_bbox = fitz.Rect(block_rect)
            else:
                curr_bbox |= fitz.Rect(block_rect)

        # append text content with newline separation
        if curr_chunk.get("text", ""):
            curr_chunk["text"] = curr_chunk["text"].rstrip() + "\n" + piece
        else:
            curr_chunk["text"] = piece

        curr_body_char_count += len(piece)

    def render_toc(nodes: List[Dict[str, Any]], indent: int = 0) -> List[str]:
        lines: List[str] = []
        pad = "  " * indent
        for n in nodes:
            lines.append(f"{pad}- {n['title']} (p. {n['page']})")
            if n.get("children"):
                lines.extend(render_toc(n["children"], indent + 1))
        return lines

    # init chunk
    flush_chunk()

    # ============================================================
    # Main scan: KEEP File A heading logic, add chunk boundaries
    # ============================================================
    for page_idx, page in enumerate(doc):
        if page_idx > 0:
            add_chunk_if_valid()
            running_continuation_flag = True
            flush_chunk()

        current_page_num = page_idx + 1
        page_width = page.rect.width
        t_geom = table_geom_by_page[page_idx]
        page_dict = page.get_text("dict")
        all_blocks = page_dict.get("blocks", [])

        # precompute next block bbox list (File A does this for vertical gap)
        block_bboxes: List[Optional[fitz.Rect]] = []
        for b in all_blocks:
            if "lines" in b:
                block_bboxes.append(fitz.Rect(b["bbox"]))
            else:
                block_bboxes.append(fitz.Rect(b.get("bbox", [0, 0, 0, 0])))

        for block_idx, b in enumerate(all_blocks):
            block_rect = fitz.Rect(b.get("bbox", [0, 0, 0, 0]))
            block_type = _classify_block(b, block_rect, t_geom)

            if page_idx == 25:
                print(f">>> Processing block {block_idx} on page {current_page_num}, type: {block_type}")

            # next bbox (File A logic)
            next_bbox = None
            for future_idx in range(block_idx + 1, len(block_bboxes)):
                if block_bboxes[future_idx] is not None:
                    next_bbox = block_bboxes[future_idx]
                    break

            # FIGURE block -> append placeholder directly
            if block_type == "FIGURE":
                append_block_to_chunk("[!Figure]", block_rect, current_page_num, "FIGURE")
                continue

            # TABLE block -> handle line-by-line (only non-table lines can be headings)
            if block_type == "TABLE":
                if "lines" not in b:
                    continue
                block_lines_data = []
                for l in b.get("lines", []) or []:
                    txt, style, r = _get_line_data(l)
                    if not txt:
                        continue
                    block_lines_data.append({"text": txt, "style": style, "rect": r})

                block_lines_data = _merge_same_row_lines(block_lines_data)
                block_lines_data = [{'txt': item['text'], 'style': item['style'], 'rect': item['rect']} for item in block_lines_data]

                for l_idx, item in enumerate(block_lines_data):
                    txt = item["txt"]
                    style = item["style"]
                    r = fitz.Rect(item["rect"])

                    if _in_any_table(r, t_geom):
                        append_block_to_chunk(txt, r, current_page_num, "TABLE")
                        continue

                    if style not in style_to_base_level:
                        append_block_to_chunk(txt, r, current_page_num, "TEXT")
                        continue

                    num_segments, _ = _extract_number_prefix_metrics(txt)
                    depth_value = _extract_number_depth_value(txt, num_segments)
                    numbering_state_peek = _update_numbering_state(
                        num_segments,
                        depth_value,
                        dict(head_values),
                        [],
                        current_page_num,
                        txt,
                    )
                    if page_idx == 25:
                        print(f"TABLE line: '{txt}' | num_segments: {num_segments} | numbering_state_peek: {numbering_state_peek} | line_idx: {l_idx}")

                    if _has_filtered_punctuation(txt, style, body_size) and not (
                        numbering_state_peek["has_numbering"] and numbering_state_peek["increment"]
                    ):
                        append_block_to_chunk(txt, r, current_page_num, "TEXT")
                        continue

                    font_size = style[0]
                    is_bold = style[1]
                    font_family = style[2]
                    text_color = style[3]
                    num_segments, dot_count = _extract_number_prefix_metrics(txt)
                    alignment = _get_alignment(r, page_width)
                    has_colon_hyphen = _has_filtered_punctuation(txt)
                    vertical_gap = _calculate_vertical_gap(r, next_bbox)
                    case_style = _detect_case_style(txt)

                    curr_meta = HeadingMetadata(
                        text=txt,
                        font_size=font_size,
                        is_bold=is_bold,
                        bbox=r,
                        num_segments=num_segments,
                        dot_count=dot_count,
                        alignment=alignment,
                        has_colon_hyphen=has_colon_hyphen,
                        font_family=font_family,
                        text_color=text_color,
                        page_num=current_page_num,
                        vertical_gap_to_next_block=vertical_gap,
                        block_id=block_idx,
                        case_style=case_style
                    )

                    depth_value = _extract_number_depth_value(curr_meta.text, curr_meta.num_segments)
                    numbering_state_peek = _update_numbering_state(
                        curr_meta.num_segments,
                        depth_value,
                        dict(head_values),
                        [],
                        current_page_num,
                        curr_meta.text,
                    )

                    if not (curr_meta.num_segments > 0 and numbering_state_peek["increment"]):
                        append_block_to_chunk(curr_meta.text, curr_meta.bbox, current_page_num, "TEXT")
                        continue

                    numbering_state = _update_numbering_state(
                        curr_meta.num_segments,
                        depth_value,
                        head_values,
                        console_log,
                        current_page_num,
                        curr_meta.text,
                    )

                    # ----------------------------
                    # Chunk boundary PRE-heading-update (NEW)
                    # ----------------------------
                    if current_page_num >= h1_page_bias:
                        if not check_filter_condition(curr_meta.text, curr_meta):
                            add_chunk_if_valid()

                    # ----------------------------
                    # File A heading update logic (UNCHANGED)
                    # ----------------------------
                    if current_page_num >= h1_page_bias:
                        if _match_h1_style(curr_meta, h1_style):
                            H_state = 1
                            H_ctx[1]["num_segments"] = curr_meta.num_segments
                        else:
                            if curr_meta.num_segments > 0 and previous_meta and previous_meta.num_segments > 0:
                                if not numbering_state["jump"]:
                                    num_seg_diff = curr_meta.num_segments - previous_meta.num_segments
                                    if num_seg_diff != 0:
                                        level_delta = (1 if num_seg_diff > 0 else -1) * abs(num_seg_diff)
                                        new_level = max(1, H_state + level_delta)
                                        H_state = new_level
                                        if new_level not in H_ctx:
                                            H_ctx[new_level] = {
                                                "font_size": curr_meta.font_size,
                                                "is_bold": curr_meta.is_bold,
                                                "alignment": curr_meta.alignment,
                                                "font_family": curr_meta.font_family,
                                                "text_color": curr_meta.text_color,
                                                "case_style": curr_meta.case_style,
                                                "num_segments": curr_meta.num_segments
                                            }
                            else:
                                matched_level = None
                                for level, style in H_ctx.items():
                                    if _match_heading_style(curr_meta, style):
                                        matched_level = level
                                        break
                                if matched_level is not None:
                                    H_state = matched_level
                                else:
                                    H_state += 1
                                    H_ctx[H_state] = {
                                        "font_size": curr_meta.font_size,
                                        "is_bold": curr_meta.is_bold,
                                        "alignment": curr_meta.alignment,
                                        "font_family": curr_meta.font_family,
                                        "text_color": curr_meta.text_color,
                                        "case_style": curr_meta.case_style,
                                        "num_segments": curr_meta.num_segments
                                    }

                        numbering_force_replace = False
                        if numbering_state["has_numbering"] and not numbering_state["jump"]:
                            if curr_meta.num_segments not in numseg_to_hctx:
                                numseg_to_hctx[curr_meta.num_segments] = H_state
                            mapped_level = numseg_to_hctx.get(curr_meta.num_segments, H_state)
                            if numbering_state["increment"]:
                                H_state = mapped_level
                                numbering_force_replace = True

                        if H_state not in H_ctx:
                            H_ctx[H_state] = {
                                "font_size": curr_meta.font_size,
                                "is_bold": curr_meta.is_bold,
                                "alignment": curr_meta.alignment,
                                "font_family": curr_meta.font_family,
                                "text_color": curr_meta.text_color,
                                "case_style": curr_meta.case_style,
                                "num_segments": curr_meta.num_segments
                            }

                        keys_to_remove = [k for k in H_ctx.keys() if k > H_state]
                        for k in keys_to_remove:
                            del H_ctx[k]

                        append_condition = False
                        if (previous_meta and
                            isinstance(curr_meta.block_id, (int, tuple)) and
                            isinstance(previous_meta.block_id, (int, tuple))):

                            curr_block_page = page_idx if isinstance(curr_meta.block_id, int) else curr_meta.block_id[0]
                            curr_block_id = curr_meta.block_id if isinstance(curr_meta.block_id, int) else curr_meta.block_id[1]
                            prev_block_page = page_idx if isinstance(previous_meta.block_id, int) else previous_meta.block_id[0]
                            prev_block_id = previous_meta.block_id if isinstance(previous_meta.block_id, int) else previous_meta.block_id[1]

                            if (curr_block_page == prev_block_page and
                                curr_block_id == prev_block_id + 1 and
                                H_state == (getattr(previous_meta, 'H_state_prev', H_state))):
                                append_condition = True

                        if numbering_force_replace:
                            while len(breadcrumb_stack) > H_state - 1:
                                breadcrumb_stack.pop()
                            breadcrumb_stack.append(curr_meta.text)
                        elif append_condition:
                            breadcrumb_stack.append(curr_meta.text)
                        else:
                            while len(breadcrumb_stack) > H_state - 1:
                                breadcrumb_stack.pop()
                            breadcrumb_stack.append(curr_meta.text)

                        if previous_meta:
                            previous_meta.H_state_prev = H_state
                        curr_meta.H_state_prev = H_state

                        if H_state in H_ctx:
                            H_ctx[H_state].update({
                                "num_segments": curr_meta.num_segments,
                                "alignment": curr_meta.alignment,
                                "case_style": curr_meta.case_style,
                                "font_size": curr_meta.font_size,
                                "is_bold": curr_meta.is_bold,
                                "font_family": curr_meta.font_family,
                                "text_color": curr_meta.text_color
                            })

                    # ----------------------------
                    # Chunk boundary POST-heading-update (NEW)
                    # ----------------------------
                    if current_page_num >= h1_page_bias:
                        if not check_filter_condition(curr_meta.text, curr_meta):
                            toc_add(H_state, curr_meta.text, current_page_num)
                            running_continuation_flag = False
                            flush_chunk()
                        else:
                            append_block_to_chunk(curr_meta.text, curr_meta.bbox, current_page_num, "TEXT")

                    previous_meta = curr_meta
                continue

            # TEXT block from here; heading detection applies (File A preserved)
            if "lines" not in b:
                continue

            block_lines_data = []
            for l in b["lines"]:
                txt, style, r = _get_line_data(l)
                # if page_idx == 13:
                #     print(">>>> Line data:", txt, style, r)
                if txt and not _in_any_table(r, t_geom):
                    block_lines_data.append({'text': txt, 'style': style, 'rect': r, 'font_size': style[0], 'is_bold': style[1], 'font_family': style[2]})
            
            block_lines_data = _merge_same_row_lines(block_lines_data)
            # 格式还原（保持后续代码的key一致性：txt/style/rect）
            block_lines_data = [{'txt': item['text'], 'style': item['style'], 'rect': item['rect']} for item in block_lines_data]

            if not block_lines_data:
                continue

            all_lines_are_headings = all(item['style'] in style_to_base_level for item in block_lines_data)

            # --------------------------------------------------------
            # Case 1: Entire block is headings (File A preserved)
            # --------------------------------------------------------
            if all_lines_are_headings:
                full_txt = " ".join([i['txt'] for i in block_lines_data])
                combined_rect = fitz.Rect(b["bbox"])

                chosen_style = block_lines_data[0]['style']
                # if page_idx == 13:
                #     print(">>>>>> Block all-headings:", full_txt, chosen_style, body_size)

                # chosen_style = next(
                #     (it['style'] for it in block_lines_data if 'bold' in (it['style'][2] or '').lower()),
                #     block_lines_data[0]['style']
                # )

                if _has_filtered_punctuation(full_txt, chosen_style, body_size):
                    # print(f">>>>> Filtered out heading: {full_txt}")
                    append_block_to_chunk(full_txt, combined_rect, current_page_num, "TEXT")
                    continue

                font_size = chosen_style[0]
                is_bold = chosen_style[1]
                font_family = chosen_style[2]
                text_color = chosen_style[3]
                num_segments, dot_count = _extract_number_prefix_metrics(full_txt)
                alignment = _get_alignment(combined_rect, page_width)
                has_colon_hyphen = _has_filtered_punctuation(full_txt)
                vertical_gap = _calculate_vertical_gap(combined_rect, next_bbox)
                case_style = _detect_case_style(full_txt)

                curr_meta = HeadingMetadata(
                    text=full_txt,
                    font_size=font_size,
                    is_bold=is_bold,
                    bbox=combined_rect,
                    num_segments=num_segments,
                    dot_count=dot_count,
                    alignment=alignment,
                    has_colon_hyphen=has_colon_hyphen,
                    font_family=font_family,
                    text_color=text_color,
                    page_num=current_page_num,
                    vertical_gap_to_next_block=vertical_gap,
                    block_id=(page_idx, block_idx),
                    case_style=case_style
                )

                depth_value = _extract_number_depth_value(curr_meta.text, curr_meta.num_segments)
                print(curr_meta.text, ">> depth_value:", depth_value, "num_segments:", curr_meta.num_segments)
                numbering_state = _update_numbering_state(
                    curr_meta.num_segments,
                    depth_value,
                    head_values,
                    console_log,
                    current_page_num,
                    curr_meta.text,
                )

                # ----------------------------
                # Chunk boundary PRE-heading-update (NEW, does not modify heading logic)
                # ----------------------------
                if current_page_num >= h1_page_bias:
                    if not check_filter_condition(curr_meta.text, curr_meta):
                        add_chunk_if_valid()

                # ----------------------------
                # File A heading update logic (UNCHANGED)
                # ----------------------------  
                if current_page_num >= h1_page_bias:        
                    append_condition = False
                    if (previous_meta and
                        isinstance(curr_meta.block_id, tuple) and
                        isinstance(previous_meta.block_id, tuple) and
                        curr_meta.block_id[0] == previous_meta.block_id[0] and
                        curr_meta.block_id[1] == previous_meta.block_id[1] + 1):
                        # curr_meta.block_id[1] == previous_meta.block_id[1] + 1 and
                        # H_state == (getattr(previous_meta, 'H_state_prev', H_state))):
                        append_condition = True

                    # if append_condition:
                    #     print("###### Appending to breadcrumb stack (consecutive)", curr_meta.text, "breadcrumb_stack", breadcrumb_stack)
                    #     H_state += 1
                    #     H_ctx[H_state] = {
                    #         "font_size": curr_meta.font_size,
                    #         "is_bold": curr_meta.is_bold,
                    #         "alignment": curr_meta.alignment,
                    #         "font_family": curr_meta.font_family,
                    #         "text_color": curr_meta.text_color,
                    #         "case_style": curr_meta.case_style,
                    #         "num_segments": curr_meta.num_segments
                    #     }
                    #     numbering_force_replace = False
                    #     if numbering_state["has_numbering"] and not numbering_state["jump"]:
                    #         if curr_meta.num_segments not in numseg_to_hctx:
                    #             numseg_to_hctx[curr_meta.num_segments] = H_state
                    #         mapped_level = numseg_to_hctx.get(curr_meta.num_segments, H_state)
                    #         if numbering_state["increment"]:
                    #             H_state = mapped_level
                    #             numbering_force_replace = True

                    #     if numbering_force_replace:
                    #         while len(breadcrumb_stack) > H_state - 1:
                    #             if breadcrumb_stack:
                    #                 breadcrumb_stack.pop()
                    #             else:
                    #                 break
                    #     breadcrumb_stack.append(curr_meta.text)
                    #     # print(H_ctx)
                    #     # print(breadcrumb_stack, curr_meta.text, curr_meta.num_segments, _extract_number_prefix_metrics(curr_meta.text)[0])
                    #     if previous_meta:
                    #         previous_meta.H_state_prev = H_state
                    #     curr_meta.H_state_prev = H_state

                    #     if not check_filter_condition(curr_meta.text, curr_meta):
                    #         running_continuation_flag = False
                    #         flush_chunk()
                    #     else:
                    #         # filtered heading -> treat heading text as body
                    #         append_block_to_chunk(curr_meta.text, curr_meta.bbox, current_page_num, "TEXT")

                    #     previous_meta = curr_meta
                    #     # i = j
                    #     continue
                    if append_condition:
                        # 【核心修改1】删除 H_state += 1，不新增层级，保持当前层级
                        # 【核心修改2】更新H_ctx用**当前原有H_state**（而非自增后的），保留同层级元数据
                        H_ctx[H_state] = {
                            "font_size": curr_meta.font_size,
                            "is_bold": curr_meta.is_bold,
                            "alignment": curr_meta.alignment,
                            "font_family": curr_meta.font_family,
                            "text_color": curr_meta.text_color,
                            "case_style": curr_meta.case_style,
                            "num_segments": curr_meta.num_segments
                        }
                        # 编号状态校验：逻辑不变，仅用原有H_state（无自增，映射一致）
                        numbering_force_replace = False
                        if numbering_state["has_numbering"] and not numbering_state["jump"]:
                            if curr_meta.num_segments not in numseg_to_hctx:
                                numseg_to_hctx[curr_meta.num_segments] = H_state  # 用原H_state映射
                            mapped_level = numseg_to_hctx.get(curr_meta.num_segments, H_state)
                            if numbering_state["increment"]:
                                H_state = mapped_level
                                numbering_force_replace = True
                        # 【核心修改3】面包屑更新：不追加新元素，直接拼接当前层级最后一个元素的文本
                        if numbering_force_replace:
                            while len(breadcrumb_stack) > H_state - 1:
                                breadcrumb_stack.pop()
                        # 拼接逻辑：栈非空则拼接到最后一个元素（当前层级），空则兜底追加（避免索引错误）
                        if breadcrumb_stack:
                            breadcrumb_stack[-1] = f"{breadcrumb_stack[-1]} {curr_meta.text}"  # 拼接空格分隔
                        else:
                            breadcrumb_stack.append(curr_meta.text)  # 极端情况：栈空时兜底

                        # 元数据状态同步：逻辑不变，同步当前原有H_state
                        if previous_meta:
                            previous_meta.H_state_prev = H_state
                        curr_meta.H_state_prev = H_state

                        # Chunk上下文刷新：逻辑不变，保证合并后的完整标题作为Chunk前缀
                        if not check_filter_condition(curr_meta.text, curr_meta):
                            running_continuation_flag = False
                            flush_chunk()  # 刷新后Chunk的sec_name/text会用合并后的面包屑
                        else:
                            append_block_to_chunk(curr_meta.text, curr_meta.bbox, current_page_num, "TEXT")
                            
                if current_page_num >= h1_page_bias:
                    if _match_h1_style(curr_meta, h1_style):
                        H_state = 1
                        H_ctx[1]["num_segments"] = curr_meta.num_segments
                    else:
                        if curr_meta.num_segments > 0 and previous_meta and previous_meta.num_segments > 0 and curr_meta.num_segments - previous_meta.num_segments == 0:
                            H_state = previous_meta.H_state_prev if previous_meta and hasattr(previous_meta, 'H_state_prev') else H_state
                            if H_state in H_ctx:
                                H_ctx[H_state].update({
                                    "num_segments": curr_meta.num_segments,
                                    "alignment": curr_meta.alignment,
                                    "case_style": curr_meta.case_style,
                                    "font_size": curr_meta.font_size,
                                    "is_bold": curr_meta.is_bold,
                                    "font_family": curr_meta.font_family,
                                    "text_color": curr_meta.text_color
                                })
                        elif curr_meta.num_segments > 0:
                            matched_level = None
                            logger.info("##### Trying to match existing H_state styles... %s", curr_meta.text)
                            for level, style in H_ctx.items():
                                if _match_heading_style_numseg(curr_meta, style):
                                    matched_level = level
                                    break
                            if matched_level is not None:
                                logger.info("##### Matched existing H_state: %s for %s", matched_level, curr_meta.text)
                                H_state = matched_level
                            else:
                                H_state += 1
                                H_ctx[H_state] = {
                                    "font_size": curr_meta.font_size,
                                    "is_bold": curr_meta.is_bold,
                                    "alignment": curr_meta.alignment,
                                    "font_family": curr_meta.font_family,
                                    "text_color": curr_meta.text_color,
                                    "case_style": curr_meta.case_style,
                                    "num_segments": curr_meta.num_segments
                                }

                        # if curr_meta.num_segments > 0 and previous_meta and previous_meta.num_segments > 0:
                        #     num_seg_diff = curr_meta.num_segments - previous_meta.num_segments
                        #     if num_seg_diff != 0:
                        #         level_delta = (1 if num_seg_diff > 0 else -1) * abs(num_seg_diff)
                        #         new_level = max(1, H_state + level_delta)
                        #         insert_level = min(new_level, max(H_ctx.keys()) + 1)
                        #         new_level = insert_level
                        #         H_state = new_level
                        #         if new_level not in H_ctx:
                        #             H_ctx[new_level] = {
                        #                 "font_size": curr_meta.font_size,
                        #                 "is_bold": curr_meta.is_bold,
                        #                 "alignment": curr_meta.alignment,
                        #                 "font_family": curr_meta.font_family,
                        #                 "text_color": curr_meta.text_color,
                        #                 "case_style": curr_meta.case_style,
                        #                 "num_segments": curr_meta.num_segments
                        #             }
                        #         print(f"##### Adjusted H_state by num_segments: {H_state} for {curr_meta.text}")
                        else:
                            matched_level = None
                            logger.info("##### Trying to match existing H_state styles... %s", curr_meta.text)
                            for level, style in H_ctx.items():
                                if _match_heading_style(curr_meta, style):
                                    matched_level = level
                                    break
                            if matched_level is not None:
                                logger.info("##### Matched existing H_state: %s for %s", matched_level, curr_meta.text)
                                H_state = matched_level
                            else:
                                H_state += 1
                                H_ctx[H_state] = {
                                    "font_size": curr_meta.font_size,
                                    "is_bold": curr_meta.is_bold,
                                    "alignment": curr_meta.alignment,
                                    "font_family": curr_meta.font_family,
                                    "text_color": curr_meta.text_color,
                                    "case_style": curr_meta.case_style,
                                    "num_segments": curr_meta.num_segments
                                }

                    numbering_force_replace = False
                    if numbering_state["has_numbering"] and not numbering_state["jump"]:
                        if curr_meta.num_segments not in numseg_to_hctx:
                            numseg_to_hctx[curr_meta.num_segments] = H_state
                        mapped_level = numseg_to_hctx.get(curr_meta.num_segments, H_state)
                        if numbering_state["increment"]:
                            H_state = mapped_level
                            numbering_force_replace = True

                    if H_state not in H_ctx:
                        H_ctx[H_state] = {
                            "font_size": curr_meta.font_size,
                            "is_bold": curr_meta.is_bold,
                            "alignment": curr_meta.alignment,
                            "font_family": curr_meta.font_family,
                            "text_color": curr_meta.text_color,
                            "case_style": curr_meta.case_style,
                            "num_segments": curr_meta.num_segments
                        }

                    keys_to_remove = [k for k in H_ctx.keys() if k > H_state]
                    for k in keys_to_remove:
                        del H_ctx[k]

                    # append_condition = False
                    # if (previous_meta and
                    #     isinstance(curr_meta.block_id, tuple) and
                    #     isinstance(previous_meta.block_id, tuple) and
                    #     curr_meta.block_id[0] == previous_meta.block_id[0] and
                    #     curr_meta.block_id[1] == previous_meta.block_id[1] + 1):
                    #     # curr_meta.block_id[1] == previous_meta.block_id[1] + 1 and
                    #     # H_state == (getattr(previous_meta, 'H_state_prev', H_state))):
                    #     append_condition = True

                    # if curr_meta.block_id[0] == 9:
                    #     print(f"Debug: Page 10 Heading: {curr_meta.text}, H_state: {H_state}, block_id: {curr_meta.block_id[1]}")

                    # if append_condition:
                    if False:
                        breadcrumb_stack.append(curr_meta.text)
                    else:
                        if numbering_force_replace:
                            while len(breadcrumb_stack) > H_state - 1:
                                if breadcrumb_stack:
                                    breadcrumb_stack.pop()
                                else:
                                    break
                        else:
                            while len(breadcrumb_stack) > H_state - 1:
                                if breadcrumb_stack:
                                    breadcrumb_stack.pop()
                                else:
                                    break
                        breadcrumb_stack.append(curr_meta.text)
                        logger.info("%s", H_ctx)
                        logger.info("%s %s %s %s", breadcrumb_stack, curr_meta.text, curr_meta.num_segments, curr_meta.text_color)

                    if previous_meta:
                        previous_meta.H_state_prev = H_state
                    curr_meta.H_state_prev = H_state

                    if H_state in H_ctx:
                        H_ctx[H_state].update({
                            "num_segments": curr_meta.num_segments,
                            "alignment": curr_meta.alignment,
                            "case_style": curr_meta.case_style,
                            "font_size": curr_meta.font_size,
                            "is_bold": curr_meta.is_bold,
                            "font_family": curr_meta.font_family,
                            "text_color": curr_meta.text_color
                        })

                # ----------------------------
                # Chunk boundary POST-heading-update (NEW)
                # flush_chunk() sets text=breadCrumb for next body
                # ----------------------------
                if current_page_num >= h1_page_bias:
                    if not check_filter_condition(curr_meta.text, curr_meta):
                        toc_add(H_state, curr_meta.text, current_page_num)
                        running_continuation_flag = False
                        flush_chunk()
                    else:
                        # filtered heading -> treat heading text as body
                        append_block_to_chunk(curr_meta.text, curr_meta.bbox, current_page_num, "TEXT")

                previous_meta = curr_meta
                continue

            # --------------------------------------------------------
            # Case 2: Mixed block, handle line-by-line like File A
            # --------------------------------------------------------
            i = 0
            while i < len(block_lines_data):
                item = block_lines_data[i]
                # if page_idx == 13:
                #     print("### Line check:", item['txt'], item['style'])

                if item['style'] in style_to_base_level:
                    base_lvl = style_to_base_level[item['style']]
                    curr_txt = item['txt']
                    curr_rect = fitz.Rect(item['rect'])

                    j = i + 1
                    while j < len(block_lines_data) and style_to_base_level.get(block_lines_data[j]['style']) == base_lvl:
                        curr_txt += " " + block_lines_data[j]['txt']
                        curr_rect |= block_lines_data[j]['rect']
                        j += 1

                    num_segments, _ = _extract_number_prefix_metrics(curr_txt)
                    depth_value = _extract_number_depth_value(curr_txt, num_segments)
                    numbering_state_peek = _update_numbering_state(
                        num_segments,
                        depth_value,
                        dict(head_values),
                        [],
                        current_page_num,
                        curr_txt,
                    )

                    if _has_filtered_punctuation(curr_txt, item['style'], body_size) and not (
                        numbering_state_peek["has_numbering"] and numbering_state_peek["increment"]
                    ):
                        i = j
                        continue

                    font_size = item['style'][0]
                    is_bold = item['style'][1]
                    font_family = item['style'][2]
                    text_color = item['style'][3]
                    num_segments, dot_count = _extract_number_prefix_metrics(curr_txt)
                    alignment = _get_alignment(curr_rect, page_width)
                    has_colon_hyphen = _has_filtered_punctuation(curr_txt)
                    vertical_gap = _calculate_vertical_gap(curr_rect, next_bbox)
                    case_style = _detect_case_style(curr_txt)

                    curr_meta = HeadingMetadata(
                        text=curr_txt,
                        font_size=font_size,
                        is_bold=is_bold,
                        bbox=curr_rect,
                        num_segments=num_segments,
                        dot_count=dot_count,
                        alignment=alignment,
                        has_colon_hyphen=has_colon_hyphen,
                        font_family=font_family,
                        text_color=text_color,
                        page_num=current_page_num,
                        vertical_gap_to_next_block=vertical_gap,
                        block_id=block_idx,
                        case_style=case_style
                    )

                    depth_value = _extract_number_depth_value(curr_meta.text, curr_meta.num_segments)
                    # print('>>> Multiple lines>>>', curr_meta.text, ">> depth_value:", depth_value, "num_segments:", curr_meta.num_segments)
                    numbering_state = _update_numbering_state(
                        curr_meta.num_segments,
                        depth_value,
                        head_values,
                        console_log,
                        current_page_num,
                        curr_meta.text,
                    )

                    # ----------------------------
                    # Chunk boundary PRE-heading-update (NEW)
                    # ----------------------------
                    if current_page_num >= h1_page_bias:
                        if not check_filter_condition(curr_meta.text, curr_meta):
                            add_chunk_if_valid()

                    # ----------------------------
                    # File A heading update logic (UNCHANGED)
                    # ----------------------------
                    # if previous_meta and previous_meta.block_id == curr_meta.block_id:
                    #     previous_meta.text = _norm_text(previous_meta.text + " " + curr_txt)
                    #     previous_meta.bbox |= curr_rect
                    #     curr_meta = previous_meta
                    #     i = j
                    #     continue

                    if current_page_num >= h1_page_bias:
                        if _match_h1_style(curr_meta, h1_style):
                            H_state = 1
                            H_ctx[1]["num_segments"] = curr_meta.num_segments
                        else:
                            if curr_meta.num_segments > 0 and previous_meta and previous_meta.num_segments > 0:
                                if not numbering_state["jump"]:
                                    num_seg_diff = curr_meta.num_segments - previous_meta.num_segments
                                    if num_seg_diff != 0:
                                        level_delta = (1 if num_seg_diff > 0 else -1) * abs(num_seg_diff)
                                        new_level = max(1, H_state + level_delta)
                                        H_state = new_level
                                        if new_level not in H_ctx:
                                            H_ctx[new_level] = {
                                                "font_size": curr_meta.font_size,
                                                "is_bold": curr_meta.is_bold,
                                                "alignment": curr_meta.alignment,
                                                "font_family": curr_meta.font_family,
                                                "text_color": curr_meta.text_color,
                                                "case_style": curr_meta.case_style,
                                                "num_segments": curr_meta.num_segments
                                            }
                            else:
                                matched_level = None
                                for level, style in H_ctx.items():
                                    if _match_heading_style(curr_meta, style):
                                        matched_level = level
                                        break
                                if matched_level is not None:
                                    H_state = matched_level
                                else:
                                    H_state += 1
                                    H_ctx[H_state] = {
                                        "font_size": curr_meta.font_size,
                                        "is_bold": curr_meta.is_bold,
                                        "alignment": curr_meta.alignment,
                                        "font_family": curr_meta.font_family,
                                        "text_color": curr_meta.text_color,
                                        "case_style": curr_meta.case_style,
                                        "num_segments": curr_meta.num_segments
                                    }

                        numbering_force_replace = False
                        if numbering_state["has_numbering"] and not numbering_state["jump"]:
                            if curr_meta.num_segments not in numseg_to_hctx:
                                numseg_to_hctx[curr_meta.num_segments] = H_state
                            mapped_level = numseg_to_hctx.get(curr_meta.num_segments, H_state)
                            if numbering_state["increment"]:
                                H_state = mapped_level
                                numbering_force_replace = True

                        if H_state not in H_ctx:
                            H_ctx[H_state] = {
                                "font_size": curr_meta.font_size,
                                "is_bold": curr_meta.is_bold,
                                "alignment": curr_meta.alignment,
                                "font_family": curr_meta.font_family,
                                "text_color": curr_meta.text_color,
                                "case_style": curr_meta.case_style,
                                "num_segments": curr_meta.num_segments
                            }

                        keys_to_remove = [k for k in H_ctx.keys() if k > H_state]
                        for k in keys_to_remove:
                            del H_ctx[k]

                        append_condition = False
                        if (previous_meta and
                            isinstance(curr_meta.block_id, (int, tuple)) and
                            isinstance(previous_meta.block_id, (int, tuple))):

                            curr_block_page = page_idx if isinstance(curr_meta.block_id, int) else curr_meta.block_id[0]
                            curr_block_id = curr_meta.block_id if isinstance(curr_meta.block_id, int) else curr_meta.block_id[1]
                            prev_block_page = page_idx if isinstance(previous_meta.block_id, int) else previous_meta.block_id[0]
                            prev_block_id = previous_meta.block_id if isinstance(previous_meta.block_id, int) else previous_meta.block_id[1]

                            if (curr_block_page == prev_block_page and
                                curr_block_id == prev_block_id + 1 and
                                H_state == (getattr(previous_meta, 'H_state_prev', H_state))):
                                append_condition = True

                        if numbering_force_replace:
                            while len(breadcrumb_stack) > H_state - 1:
                                breadcrumb_stack.pop()
                            breadcrumb_stack.append(curr_meta.text)
                        elif append_condition:
                            breadcrumb_stack.append(curr_meta.text)
                        else:
                            while len(breadcrumb_stack) > H_state - 1:
                                breadcrumb_stack.pop()
                            breadcrumb_stack.append(curr_meta.text)

                        if previous_meta:
                            previous_meta.H_state_prev = H_state
                        curr_meta.H_state_prev = H_state

                        if H_state in H_ctx:
                            H_ctx[H_state].update({
                                "num_segments": curr_meta.num_segments,
                                "alignment": curr_meta.alignment,
                                "case_style": curr_meta.case_style,
                                "font_size": curr_meta.font_size,
                                "is_bold": curr_meta.is_bold,
                                "font_family": curr_meta.font_family,
                                "text_color": curr_meta.text_color
                            })

                    # ----------------------------
                    # Chunk boundary POST-heading-update (NEW)
                    # ----------------------------
                    if current_page_num >= h1_page_bias:
                        if not check_filter_condition(curr_meta.text, curr_meta):
                            toc_add(H_state, curr_meta.text, current_page_num)
                            running_continuation_flag = False
                            flush_chunk()
                        else:
                            append_block_to_chunk(curr_meta.text, curr_meta.bbox, current_page_num, "TEXT")

                    previous_meta = curr_meta
                    i = j
                    continue

                # ----------------------------------------------------
                # Non-heading line => append to chunk as body (NEW)
                # ----------------------------------------------------
                append_block_to_chunk(item['txt'], fitz.Rect(item['rect']), current_page_num, "TEXT")
                i += 1

    # end doc: add last chunk
    add_chunk_if_valid()

    # ---------------------------
    # Render ToC + append final chunk (NEW)
    # ---------------------------
    toc_text = "TABLE OF CONTENTS\n" + "\n".join(render_toc(toc_root))
    toc_chunk = {
        "chunk_id": _chunk_uuid(doc_fp, chunk_index),
        "type": "TOC",
        "text": toc_text,
        "sec_name": "",
        "metadata": {
            "TABLE_OF_CONTENTS": True,
            "CONTINUATION": False
        },
        "page_number": 1,
        "doc_fingerprint": doc_fp,
        "bbox": [0.0, 0.0, 0.0, 0.0],
        "orig_size": [float(doc[0].rect.width), float(doc[0].rect.height)]
    }
    chunks.append(toc_chunk)
    chunk_index += 1

    # ---------------------------
    # Build doc_info from inferred metadata
    # ---------------------------
    dt = inferred_meta.get("doc_title", {}) or {}
    doc_info = {
        "doc_title": dt.get("normalized_title"),
        "doc_type": dt.get("doc_type"),
        "project_or_subject": dt.get("project_or_subject"),
        "issuer_or_agency": dt.get("issuer_or_agency"),
        "country_or_region": dt.get("country_or_region"),
    }

    out_obj = {
        "doc_info": doc_info,
        "chunks": chunks
    }

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)

    doc.close()

# ---------------------------
# Public API
# ---------------------------
def create_chunks_rfp(
    pdf_path: str,
    *,
    backend: str = "pymupdf",
    verbose: bool = True,
    model: str = OLLAMA_MODEL,
    temperature: float = 0.2,
) -> List[Dict[str, Any]]:
    """
    Run rich-heading RFP chunking pipeline and return the chunk list.
    """
    import pathlib

    if backend != "pymupdf":
        raise ValueError(f"Unsupported backend: {backend}. Only 'pymupdf' is supported.")

    pdf_path_obj = pathlib.Path(pdf_path)
    if not pdf_path_obj.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    pdf_stem = pdf_path_obj.stem
    output_json = pdf_path_obj.with_name(f"{pdf_stem}_chunks.json").as_posix()
    log_file = pdf_path_obj.with_name(f"{pdf_stem}_chunking_log.txt").as_posix()
    init_logger(log_file)

    if verbose:
        logger.info("[Step 1] Extract headings first 5 pages")
    headings_json = pdf_path_obj.with_name(f"{pdf_stem}_headings_first5pages.json").as_posix()
    extract_headings_first5pages(pdf_path, headings_json)

    if verbose:
        logger.info("[Step 2] Infer metadata")
    metadata_json = pdf_path_obj.with_name(f"{pdf_stem}_inferred_metadata.json").as_posix()
    infer_metadata(headings_json, metadata_json, model, temperature)

    if verbose:
        logger.info("[Step 3] Parse PDF with running heading breadcrumb + chunking")
    process_pdf_to_chunk_json(
        input_pdf=pdf_path,
        inferred_metadata_json=metadata_json,
        output_json_path=output_json,
        output_console=False,
    )

    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("chunks", [])



# ---------------------------
# Main
# ---------------------------
def main():
    parser = argparse.ArgumentParser(description="PDF heading context + chunking (File A + chunking only)")
    parser.add_argument("pdf", help="输入PDF文件路径")
    parser.add_argument("--output-json", default=None, help="输出chunk json文件路径")
    parser.add_argument("--model", help="Ollama模型名称", default=OLLAMA_MODEL)
    parser.add_argument("--temperature", type=float, help="采样温度", default=0.2)
    parser.add_argument("--log-file", default=None, help="Log file for progress/info output")
    args = parser.parse_args()

    pdf_path = args.pdf
    pdf_stem = Path(pdf_path).stem

    output_json = args.output_json or f"{pdf_stem}_chunks.json"
    log_file = args.log_file or f"{pdf_stem}_chunking_log.txt"
    init_logger(log_file)

    # Step 1
    headings_json = f"{pdf_stem}_headings_first5pages.json"
    logger.info("[Step 1] Extract headings first 5 pages -> %s", headings_json)
    extract_headings_first5pages(pdf_path, headings_json)

    # Step 2
    metadata_json = f"{pdf_stem}_inferred_metadata.json"
    logger.info("[Step 2] Infer metadata -> %s", metadata_json)
    infer_metadata(headings_json, metadata_json, args.model, args.temperature)

    # Step 3 + Chunking
    logger.info("[Step 3] Parse PDF with running heading breadcrumb + chunking -> %s", output_json)
    process_pdf_to_chunk_json(
        input_pdf=pdf_path,
        inferred_metadata_json=metadata_json,
        output_json_path=output_json,
        output_console=False,
    )
    logger.info("Done. Chunk JSON saved to: %s", output_json)
if __name__ == "__main__":
    main()
