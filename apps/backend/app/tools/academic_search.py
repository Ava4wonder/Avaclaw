from typing import Any

from datetime import datetime, timezone
import html as html_lib
from html.parser import HTMLParser
import json
import os
import re
import uuid

import httpx
import requests

from ..config import settings


async def academic_search(args: dict[str, Any]) -> dict:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("Query is required")

    limit_raw = args.get("limit", 5)
    try:
        limit = int(limit_raw)
    except Exception:
        limit = 5
    limit = max(1, min(limit, 30))

    from_year = args.get("from_year")
    to_year = args.get("to_year")
    has_fulltext = args.get("has_fulltext")

    filters = []
    if from_year and to_year:
        filters.append(f"publication_year:{from_year}-{to_year}")
    elif from_year:
        filters.append(f"publication_year:>{from_year - 1}")
    elif to_year:
        filters.append(f"publication_year:<{to_year + 1}")
    if has_fulltext:
        filters.append("has_fulltext:true")

    url = f"{settings.openalex_base}/works"
    params = {
        "search.semantic": query,
        # "search.title_and_abstract": query,
        "sort": "relevance_score:desc",
        "per-page": str(limit),
        "include_xpac": "true",
    }
    if filters:
        params["filter"] = ",".join(filters)

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        res = await client.get(url, params=params, headers={"User-Agent": "AvaClaw/0.1", "mailto": "contact@example.com"})
    if res.status_code >= 400:
        raise RuntimeError(f"OpenAlex error {res.status_code}: {res.text}")

    data = res.json()
    papers = []
    for paper in data.get("results", []) or []:
        abstract_index = paper.get("abstract_inverted_index", {})
        abstract = ""
        if abstract_index:
            word_list = []
            for word, positions in abstract_index.items():
                for pos in positions:
                    word_list.append((pos, word))
            word_list.sort(key=lambda x: x[0])
            abstract = " ".join([w[1] for w in word_list])

        authors = []
        for authorship in paper.get("authorships", []):
            author = authorship.get("author", {})
            if author.get("display_name"):
                authors.append(author.get("display_name"))

        primary_location = paper.get("primary_location") or {}
        pdf_url = primary_location.get("pdf_url") or ""
        landing_page_url = primary_location.get("landing_page_url") or ""
        
        # safely extract arxiv id
        arxiv_id = ""
        # 1. try from ids.arxiv
        arxiv_url = paper.get("ids", {}).get("arxiv")
        if arxiv_url:
            arxiv_id = arxiv_url.split("/")[-1]
        # 2. try from locations
        if not arxiv_id:
            for loc in paper.get("locations", []) or []:
                if not loc: continue
                l_url = loc.get("landing_page_url") or ""
                p_url = loc.get("pdf_url") or ""
                if "arxiv.org/abs/" in l_url:
                    arxiv_id = l_url.split("arxiv.org/abs/")[-1]
                    break
                elif "arxiv.org/pdf/" in p_url:
                    arxiv_id = p_url.split("arxiv.org/pdf/")[-1].replace(".pdf", "")
                    break

        papers.append(
            {
                "title": paper.get("title", ""),
                "authors": authors,
                "year": paper.get("publication_year"),
                "citationCount": paper.get("cited_by_count", 0),
                "abstract": abstract,
                "url": pdf_url or landing_page_url or paper.get("id", ""),
                "arxiv_id": arxiv_id,
                "type": paper.get("type", ""),
                "related_works": paper.get("related_works", [])
            }
        )

    return {"papers": papers}


def _coerce_bulk_num(raw_value: Any, default: int = 5) -> int:
    try:
        value = int(raw_value)
    except Exception:
        value = default
    return max(1, min(value, 20))


def _format_bulk_abstracts(papers: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, paper in enumerate(papers, start=1):
        title = str(paper.get("title", "")).strip()
        abstract = str(paper.get("abstract", "")).strip()
        lines.append(f'{index}. This is the Abstract of paper "{title}": {abstract}')
    return "\n".join(lines)

async def _ollama_chat(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    model: str | None
) -> str:
    payload = {
        "model": model or settings.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0}
    }
    url = f"{settings.ollama_base_url}/api/chat"
    # res = await client.post(url, json=payload)
    res = requests.post(url, json=payload, timeout=1200.0)
    print(f"LLM response status: {res.status_code}")  # Debug print for status code
    if res.status_code >= 400:
        raise RuntimeError(f"LLM error {res.status_code}: {res.text}")
    data = res.json()
    message = data.get("message") or {}
    return message.get("content", "")


async def bulk_abstract_llm_inference(
    client: httpx.AsyncClient,
    abstracts_text: str,
    model: str | None
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a research analyst. Extract structured summaries from paper abstracts. "
                "Return one JSON object per paper as JSONL. Do not add markdown or extra text."
            ),
        },
        {
            "role": "user",
            "content": (
                "Given the following paper abstracts, produce JSONL with one line per paper. "
                "Each JSON object must include the fields: "
                "title, challenge, angle, solution, evaluation. "
                "Use concise phrases. If a field is missing, use null.\n\n"
                f"Abstracts:\n{abstracts_text}"
            ),
        },
    ]
    return (await _ollama_chat(client, messages, model)).strip()


async def final_abstract_llm_inference(
    client: httpx.AsyncClient,
    temp_answer: str,
    model: str | None
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a research analyst. Compare and synthesize across multiple papers. "
                "Output only a markdown code block in jsonl format."
            ),
        },
        {
            "role": "user",
            "content": (
                "You will receive JSONL lines, each describing a paper with fields "
                "title, challenge, angle, solution, evaluation.\n"
                "Tasks:\n"
                "1. Deduplicate or merge near-duplicate papers by title.\n"
                "2. Output a markdown code block in jsonl format.\n\n"
                "Within the code block:\n"
                "- One JSONL line per paper with fields: "
                'type="paper_summary", title, challenge, angle, solution, evaluation, metrics.\n'
                "- One final JSONL line with fields: "
                'type="overall_summary", common_challenges, common_angles, common_solutions, common_metrics.\n'
                "Metrics should be an array of strings derived from evaluations.\n\n"
                f"Input JSONL:\n{temp_answer}"
            ),
        },
    ]
    return (await _ollama_chat(client, messages, model)).strip()


async def read_bulk_abstract(args: dict[str, Any]) -> dict:
    payload = args or {}
    papers = payload.get("papers") or []
    if not isinstance(papers, list):
        raise ValueError("papers must be a list")

    bulk_num = _coerce_bulk_num(payload.get("bulk_num", 10))
    model = payload.get("model")

    if not papers:
        return {
            "papers_processed": 0,
            "bulk_num": bulk_num,
            "chunks": 0,
            "temp_answer": "",
            "final_answer": ""
        }

    temp_parts: list[str] = []
    async with httpx.AsyncClient(timeout=60) as client:
        for start in range(0, len(papers), bulk_num):
            print(f"Processing papers {start + 1} to {min(start + bulk_num, len(papers))}...")  # Debug print for progress
            chunk = papers[start:start + bulk_num]
            abstracts_text = _format_bulk_abstracts(chunk)
            chunk_answer = await bulk_abstract_llm_inference(client, abstracts_text, model)
            print(chunk_answer)  # Debug print for each chunk's answer
            if chunk_answer:
                temp_parts.append(chunk_answer)

        temp_answer = "\n".join(temp_parts).strip()
        final_answer = await final_abstract_llm_inference(client, temp_answer, model)

    return {
        "papers_processed": len(papers),
        "bulk_num": bulk_num,
        "chunks": len(temp_parts),
        "temp_answer": temp_answer,
        "final_answer": final_answer
    }


class _ArxivHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_stack: list[str] = []
        self._heading_level: int | None = None
        self._heading_buffer: list[str] = []
        self._text_tag: str | None = None
        self._text_buffer: list[str] = []
        self.heading_stack: list[str] = []
        self.sections: list[dict[str, str]] = []
        self.toc_paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._skip_stack.append(tag)
            return
        if self._skip_stack:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_level = int(tag[1])
            self._heading_buffer = []
            return
        if tag in {"p", "li", "blockquote", "pre"}:
            self._text_tag = tag
            self._text_buffer = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_stack:
            if tag == self._skip_stack[-1]:
                self._skip_stack.pop()
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._heading_level:
            heading_text = _normalize_text("".join(self._heading_buffer))
            if heading_text:
                level = self._heading_level
                if level <= len(self.heading_stack):
                    self.heading_stack = self.heading_stack[: level - 1]
                self.heading_stack.append(heading_text)
                path = ">".join(self.heading_stack)
                self.toc_paths.append(path)
            self._heading_level = None
            self._heading_buffer = []
            return
        if self._text_tag and tag == self._text_tag:
            text = _normalize_text("".join(self._text_buffer))
            if text:
                self.sections.append(
                    {
                        "headings_info": ">".join(self.heading_stack),
                        "text": text
                    }
                )
            self._text_tag = None
            self._text_buffer = []

    def handle_data(self, data: str) -> None:
        if self._skip_stack:
            return
        if self._heading_level:
            self._heading_buffer.append(data)
        elif self._text_tag:
            self._text_buffer.append(data)


def _normalize_text(text: str) -> str:
    text = html_lib.unescape(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _build_text_toc(paths: list[str]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path and path not in seen:
            seen.add(path)
            ordered.append(path)
    return "\n".join(ordered)


def _ollama_embed(text: str, model: str | None = None) -> list[float]:
    payload = {"model": model or settings.ollama_embedding_model, "prompt": text}
    url = f"{settings.ollama_base_url}/api/embeddings"
    res = requests.post(url, json=payload, timeout=120.0)
    if res.status_code >= 400:
        raise RuntimeError(f"Embedding error {res.status_code}: {res.text}")
    data = res.json()
    embedding = data.get("embedding")
    if embedding is None and isinstance(data.get("data"), list):
        first = data["data"][0] if data["data"] else {}
        embedding = first.get("embedding")
    if not isinstance(embedding, list):
        raise RuntimeError("Embedding response missing embedding vector")
    return embedding


def _qdrant_base_url() -> str:
    return f"http://{settings.qdrant_host}:{settings.qdrant_port}"


def _qdrant_create_collection(collection_name: str, vector_size: int) -> None:
    url = f"{_qdrant_base_url()}/collections/{collection_name}"
    payload = {"vectors": {"size": vector_size, "distance": "Cosine"}}
    res = requests.put(url, json=payload, timeout=30.0)
    if res.status_code not in {200, 201, 202, 409}:
        raise RuntimeError(f"Qdrant create error {res.status_code}: {res.text}")


def _qdrant_upsert_points(collection_name: str, points: list[dict[str, Any]]) -> None:
    if not points:
        return
    url = f"{_qdrant_base_url()}/collections/{collection_name}/points"
    payload = {"points": points}
    res = requests.put(url, json=payload, timeout=60.0)
    if res.status_code >= 400:
        raise RuntimeError(f"Qdrant upsert error {res.status_code}: {res.text}")


def _qdrant_search(collection_name: str, vector: list[float], limit: int = 5) -> list[dict[str, Any]]:
    url = f"{_qdrant_base_url()}/collections/{collection_name}/points/search"
    payload = {"vector": vector, "limit": limit, "with_payload": True}
    res = requests.post(url, json=payload, timeout=60.0)
    if res.status_code >= 400:
        raise RuntimeError(f"Qdrant search error {res.status_code}: {res.text}")
    data = res.json() or {}
    return data.get("result", []) or []


async def _llm_filter(
    client: httpx.AsyncClient,
    abstract: str,
    model: str | None = None
) -> bool:
    if not abstract:
        return False
    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict classifier. Answer only True or False."
            )
        },
        {
            "role": "user",
            "content": (
                "Question: whether this paper has solid evaluation with quantitative and noticable improvement number(s).\n"
                f"Abstract: {abstract}\n\nAnswer:"
            )
        }
    ]
    content = (await _ollama_chat(client, messages, model)).strip().lower()
    if "true" in content and "false" not in content:
        return True
    if "false" in content and "true" not in content:
        return False
    return bool(re.search(r"\d", abstract))


async def fetch_full_content(arxiv_id: str) -> str:
    if not arxiv_id:
        return ""
    url = f"https://arxiv.org/html/{arxiv_id}"
    res = requests.get(url, timeout=60.0, verify=False)
    if res.status_code >= 400:
        raise RuntimeError(f"arXiv HTML error {res.status_code}: {res.text}")
    else:
        print(f"Fetched HTML content for arXiv ID {arxiv_id}")  # Debug print for successful fetch
    return res.text


def html_parsing_chunking_upsert(
    html_content: str,
    paper_title: str,
    arxiv_id: str,
    chunk_size: int = 2200,
    chunk_overlap: int = 200
) -> dict[str, Any]:
    parser = _ArxivHtmlParser()
    parser.feed(html_content)
    text_toc = _build_text_toc(parser.toc_paths)

    chunks: list[dict[str, str]] = []
    print(f"Total sections parsed: {len(parser.sections)}")  # Debug print for number of sections
    print(f"Sample section headings info: {[s['headings_info'] for s in parser.sections]}")  # Debug print for sample headings
    for section in parser.sections:
        for chunk_text in _chunk_text(section["text"], chunk_size, chunk_overlap):
            print(f"Chunking section '{section['headings_info']}' into chunk starting with: {chunk_text[:50]}...")  # Debug print for chunking
            chunks.append(
                {
                    "headings_info": section.get("headings_info", ""),
                    "chunk_text": chunk_text
                }
            )

    if not chunks:
        return {
            "collection_name": "",
            "text_toc": text_toc,
            "chunks_upserted": 0
        }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    collection_name = f"comprehesion_paperreading_{timestamp}_{uuid.uuid4().hex[:8]}"
    first_vector = _ollama_embed(
        f"{chunks[0]['headings_info']}\n{chunks[0]['chunk_text']}".strip()
    )
    _qdrant_create_collection(collection_name, len(first_vector))

    points: list[dict[str, Any]] = []
    for chunk in chunks:
        text_for_embedding = f"{chunk['headings_info']}\n{chunk['chunk_text']}".strip()
        vector = _ollama_embed(text_for_embedding)
        points.append(
            {
                "id": uuid.uuid4().hex,
                "vector": vector,
                "payload": {
                    "chunk_text": chunk["chunk_text"],
                    "headings_info": chunk["headings_info"],
                    "paper_title": paper_title,
                    "arxiv_id": arxiv_id
                }
            }
        )

    _qdrant_upsert_points(collection_name, points)

    return {
        "collection_name": collection_name,
        "text_toc": text_toc,
        "chunks_upserted": len(points)
    }


def markdown_parsing_chunking_upsert(
    paper_md: str,
    paper_title: str,
    arxiv_id: str
) -> dict[str, Any]:
    """Parse markdown into one chunk per heading-defined section and upsert to Qdrant."""
    lines = paper_md.splitlines()
    chunks: list[dict[str, str]] = []
    toc_paths: list[str] = []
    heading_stack: list[str] = []
    current_heading_path = ""
    current_text_lines: list[str] = []

    def flush_chunk() -> None:
        nonlocal current_text_lines
        chunk_text = "\n".join(current_text_lines).strip()
        if chunk_text:
            chunks.append(
                {
                    "headings_info": current_heading_path,
                    "chunk_text": chunk_text
                }
            )
        current_text_lines = []

    for raw_line in lines:
        line = raw_line.rstrip()
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            flush_chunk()
            level = len(match.group(1))
            heading_text = re.sub(r"\s+", " ", match.group(2)).strip()
            if not heading_text:
                current_heading_path = ""
                continue
            heading_stack = heading_stack[:level - 1]
            heading_stack.append(heading_text)
            current_heading_path = ">".join(heading_stack)
            toc_paths.append(current_heading_path)
            continue

        if line.strip() or current_text_lines:
            current_text_lines.append(line)

    flush_chunk()

    text_toc = _build_text_toc(toc_paths)

    if not chunks:
        return {
            "collection_name": "",
            "text_toc": text_toc,
            "chunks_upserted": 0
        }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    collection_name = f"comprehesion_paperreading_{timestamp}_{uuid.uuid4().hex[:8]}"
    first_vector = _ollama_embed(
        f"{chunks[0]['headings_info']}\n{chunks[0]['chunk_text']}".strip()
    )
    _qdrant_create_collection(collection_name, len(first_vector))

    points: list[dict[str, Any]] = []
    for chunk in chunks:
        text_for_embedding = f"{chunk['headings_info']}\n{chunk['chunk_text']}".strip()
        vector = _ollama_embed(text_for_embedding)
        points.append(
            {
                "id": uuid.uuid4().hex,
                "vector": vector,
                "payload": {
                    "chunk_text": chunk["chunk_text"],
                    "headings_info": chunk["headings_info"],
                    "paper_title": paper_title,
                    "arxiv_id": arxiv_id
                }
            }
        )

    _qdrant_upsert_points(collection_name, points)

    return {
        "collection_name": collection_name,
        "text_toc": text_toc,
        "chunks_upserted": len(points)
    }


def _retrieve_chunks(
    collection_name: str,
    query: str,
    top_k: int = 5,
    search_k: int = 20,
    filter_headings: list[str] | None = None
) -> list[dict[str, Any]]:
    vector = _ollama_embed(query)
    hits = _qdrant_search(collection_name, vector, limit=search_k)
    if filter_headings:
        lowered = [h.lower() for h in filter_headings if h]
        filtered = [
            hit for hit in hits
            if any(h in str((hit.get("payload") or {}).get("headings_info", "")).lower() for h in lowered)
        ]
        if filtered:
            hits = filtered
    return hits[:top_k]


async def _rag_answer(
    client: httpx.AsyncClient,
    question: str,
    chunks: list[dict[str, Any]],
    model: str | None = None
) -> str:
    context_parts: list[str] = []
    for hit in chunks:
        payload = hit.get("payload") or {}
        chunk_text = payload.get("chunk_text", "")
        headings_info = payload.get("headings_info", "")
        context_parts.append(f"[{headings_info}] {chunk_text}")
    context = "\n".join(context_parts)
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert research scientist. Answer using the provided context. "
                "If the context is insufficient, say so explicitly."
            )
        },
        {
            "role": "user",
            "content": f"Question: {question}\n\nContext:\n{context}"
        }
    ]
    return (await _ollama_chat(client, messages, model)).strip()


def _extract_json_from_text(raw: str) -> Any | None:
    raw = raw.strip()
    if not raw:
        return None
    decoder = json.JSONDecoder()
    for index, ch in enumerate(raw):
        if ch not in {"{", "["}:
            continue
        try:
            obj, _ = decoder.raw_decode(raw[index:])
            return obj
        except Exception:
            continue
    return None


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_plan_item(item: Any, fallback_id: str) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    question = str(item.get("question", "")).strip()
    if not question:
        return None
    question_id = str(item.get("question_id") or fallback_id).strip()
    question_type = str(item.get("question_type") or "analysis").strip()
    toc_page_index = _coerce_str_list(item.get("toc_page_index"))
    why_this_matters = str(item.get("why_this_matters") or "").strip()
    return {
        "question_id": question_id,
        "question": question,
        "question_type": question_type,
        "toc_page_index": toc_page_index,
        "why_this_matters": why_this_matters
    }


def _parse_root_plan(raw: str) -> list[dict[str, Any]]:
    obj = _extract_json_from_text(raw)
    if isinstance(obj, dict) and isinstance(obj.get("plan"), list):
        plan_items = []
        for idx, item in enumerate(obj["plan"], start=1):
            normalized = _normalize_plan_item(item, f"q_root_{idx}")
            if normalized:
                plan_items.append(normalized)
        return plan_items
    return []


def _parse_followup_plan(raw: str, depth: int) -> tuple[list[dict[str, Any]], bool, str]:
    obj = _extract_json_from_text(raw)
    followups: list[dict[str, Any]] = []
    should_continue = False
    stop_reason = ""
    if isinstance(obj, dict):
        should_continue = bool(obj.get("should_continue", False))
        stop_reason = str(obj.get("stop_reason") or "")
        raw_followups = obj.get("followups")
        if isinstance(raw_followups, list):
            for idx, item in enumerate(raw_followups, start=1):
                normalized = _normalize_plan_item(item, f"q_followup_{depth}_{idx}")
                if normalized:
                    normalized["depth"] = depth
                    normalized["parent_question_id"] = str(item.get("parent_question_id") or "")
                    followups.append(normalized)
    return followups, should_continue, stop_reason


async def comprehension_progressive_qa(
    client: httpx.AsyncClient,
    paper: dict[str, Any],
    collection_name: str,
    text_toc: str
) -> dict[str, Any]:
    max_depth_raw = os.getenv("COMPREHENSION_MAX_DEPTH", "1")
    try:
        max_depth = max(1, int(max_depth_raw))
    except Exception:
        max_depth = 1
    retrieval_top_k = 5
    search_k = 25

    output_dir = os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    filename = f"comprehension_{collection_name}.jsonl"
    output_path = os.path.join(output_dir, filename)

    planner_messages = [
        {
            "role": "system",
            "content": (
                "You are an expert computer science researcher with 20+ years of engineering experience. "
                "Generate an in-depth reading plan rooted in the abstract and TOC. "
                "Output strict JSON with shape: {\"plan\": ["
                "{\"question_id\":\"q_root_1\",\"question\":\"...\",\"question_type\":\"...\","
                "\"toc_page_index\":[\"Heading\"],\"why_this_matters\":\"...\"}]}"
            )
        },
        {
            "role": "user",
            "content": (
                "Use the paper abstract as the anchor. Propose deep technical questions that dissect "
                "problem definition, assumptions, method design, module roles, evaluation design, results, "
                "and hidden concerns. toc_page_index must be per-question and match the TOC headings.\n\n"
                f"Abstract:\n{paper.get('abstract', '')}\n\nTOC:\n{text_toc}"
            )
        }
    ]
    planner_raw = await _ollama_chat(client, planner_messages, settings.ollama_code_model)
    root_plan = _parse_root_plan(planner_raw)

    total_records = 0
    for root_index, root_item in enumerate(root_plan, start=1):
        insufficiency_count = 0
        root_id = root_item["question_id"] or f"q_root_{root_index}"
        root_question = root_item["question"]
        root_toc = root_item.get("toc_page_index", [])
        root_type = root_item.get("question_type", "analysis")

        filtered_hits = _retrieve_chunks(
            collection_name,
            root_question,
            top_k=retrieval_top_k,
            search_k=search_k,
            filter_headings=root_toc
        )
        if not filtered_hits:
            insufficiency_count += 1
        print(f"Answering Root question '{root_question}' >> root_toc: {root_toc}")  # Debug print for retrieval results
        filtered_answer = await _rag_answer(client, root_question, filtered_hits, settings.ollama_model)

        root_record = {
            "type": "paper_qa",
            "paper_title": paper.get("title", ""),
            "arxiv_id": paper.get("arxiv_id", ""),
            "collection_name": collection_name,
            "question_id": root_id,
            "parent_question_id": None,
            "root_question_id": root_id,
            "depth": 0,
            "question_type": root_type,
            "question": root_question,
            "toc_page_index": root_toc,
            "filtered_answer": filtered_answer,
            "retrieval_top_k": retrieval_top_k,
            "why_this_matters": root_item.get("why_this_matters", "")
        }
        total_records += 1
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(root_record, ensure_ascii=True) + "\n")

        current_frontier = [
            {
                "question_id": root_id,
                "root_question_id": root_id,
                "question": root_question,
                "answer": filtered_answer,
                "toc_page_index": root_toc,
                "question_type": root_type
            }
        ]

        for depth in range(1, max_depth + 1):
            if insufficiency_count >= 2:
                break
            next_frontier: list[dict[str, Any]] = []
            for parent_node in current_frontier:
                followup_messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert researcher. Based on the previous answer, propose "
                            "deeper follow-up questions. Output strict JSON: "
                            "{\"followups\":[{\"question_id\":\"q_root_1_d1_f1\","
                            "\"parent_question_id\":\"q_root_1\",\"question\":\"...\","
                            "\"question_type\":\"...\",\"toc_page_index\":[\"Heading\"],"
                            "\"why_this_matters\":\"...\",\"depth\":1}],"
                            "\"should_continue\":true,\"stop_reason\":\"\"}"
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            "Generate deeper follow-up questions conditioned on the root question, "
                            "current question, previous answer, and TOC. Focus on unclear or under-"
                            "justified areas.\n\n"
                            f"Root Question: {root_question}\n\n"
                            f"Current Question: {parent_node['question']}\n\n"
                            f"Previous Answer: {parent_node['answer']}\n\n"
                            f"TOC:\n{text_toc}\n"
                        )
                    }
                ]
                followup_raw = await _ollama_chat(client, followup_messages, settings.ollama_code_model)
                followups, should_continue, _ = _parse_followup_plan(followup_raw, depth)
                if not should_continue or not followups:
                    continue

                for idx, followup in enumerate(followups, start=1):
                    question_id = followup.get("question_id") or f"{root_id}_d{depth}_f{idx}"
                    question = followup["question"]
                    toc_page_index = followup.get("toc_page_index", [])
                    question_type = followup.get("question_type", "analysis")

                    hits = _retrieve_chunks(
                        collection_name,
                        question,
                        top_k=retrieval_top_k,
                        search_k=search_k,
                        filter_headings=toc_page_index
                    )
                    if not hits:
                        insufficiency_count += 1
                    print(f"Answering Follow-up question '{question}' >> toc_page_index: {toc_page_index}")  # Debug print for retrieval results
                    answer = await _rag_answer(client, question, hits, settings.ollama_model)

                    record = {
                        "type": "paper_qa",
                        "paper_title": paper.get("title", ""),
                        "arxiv_id": paper.get("arxiv_id", ""),
                        "collection_name": collection_name,
                        "question_id": question_id,
                        "parent_question_id": parent_node["question_id"],
                        "root_question_id": root_id,
                        "depth": depth,
                        "question_type": question_type,
                        "question": question,
                        "toc_page_index": toc_page_index,
                        "filtered_answer": answer,
                        "retrieval_top_k": retrieval_top_k,
                        "why_this_matters": followup.get("why_this_matters", "")
                    }
                    total_records += 1
                    with open(output_path, "a", encoding="utf-8") as handle:
                        handle.write(json.dumps(record, ensure_ascii=True) + "\n")

                    next_frontier.append(
                        {
                            "question_id": question_id,
                            "root_question_id": root_id,
                            "question": question,
                            "answer": answer,
                            "toc_page_index": toc_page_index,
                            "question_type": question_type
                        }
                    )

            if not next_frontier:
                break
            current_frontier = next_frontier

    return {
        "root_questions": len(root_plan),
        "total_records": total_records,
        "output_path": output_path,
        "max_depth_used": max_depth
    }


async def Comprehension_of_papers_withnoticablemetrics(args: dict[str, Any]) -> dict:
    payload = args or {}
    papers = payload.get("papers") or []
    if not isinstance(papers, list):
        raise ValueError("papers must be a list")

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=60) as client:
        for paper in papers:
            abstract = str(paper.get("abstract", "")).strip()
            passed = await _llm_filter(client, abstract, settings.ollama_model)
            paper_result = {
                "title": paper.get("title", ""),
                "arxiv_id": paper.get("arxiv_id", ""),
                "passed_filter": passed
            }
            if not passed:
                results.append(paper_result)
                continue

            arxiv_id = str(paper.get("arxiv_id", "")).strip()
            if not arxiv_id:
                paper_result["error"] = "Missing arxiv_id"
                results.append(paper_result)
                continue

            try:
                html_content = await fetch_full_content(arxiv_id)
                chunk_result = html_parsing_chunking_upsert(
                    html_content,
                    paper_title=str(paper.get("title", "")).strip(),
                    arxiv_id=arxiv_id
                )
                paper_result.update(chunk_result)

                if chunk_result.get("collection_name"):
                    qa_result = await comprehension_progressive_qa(
                        client,
                        paper,
                        chunk_result["collection_name"],
                        chunk_result.get("text_toc", "")
                    )
                    paper_result.update(qa_result)
            except Exception as exc:
                paper_result["error"] = str(exc)

            results.append(paper_result)

    return {"papers_processed": len(papers), "results": results}
