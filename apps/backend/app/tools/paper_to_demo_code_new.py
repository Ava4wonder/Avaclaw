"""
Paper-to-demo-code tool with module-oriented recursive progressive QA before codegen.

Compared with the simplified version, this file adds:

1. Multi-level question tree per module
2. Answer-conditioned follow-up planning
3. Parent-child question relations
4. Depth control for recursive QA
5. Frontier-based progressive expansion
6. Insufficiency-aware QA branching
7. Structured QA persistence (JSONL)
8. Decoupling between comprehension and code generation

Pipeline:
    paper HTML -> chunk/retrieve -> architecture plan
    -> per-module progressive comprehension QA
    -> per-module implementation brief
    -> single-pass code generation
    -> README + metadata
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import requests

from ..config import settings
from .academic_search import (
    fetch_full_content,
    html_parsing_chunking_upsert,
    markdown_parsing_chunking_upsert,
)


def _utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def _ollama_embed(text: str, model: str | None = None) -> list[float]:
    """Generate embeddings using Ollama."""
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
    """Get Qdrant base URL."""
    return f"http://{settings.qdrant_host}:{settings.qdrant_port}"


def _qdrant_search(
    collection_name: str,
    vector: list[float],
    limit: int = 5
) -> list[dict[str, Any]]:
    """Search in Qdrant collection."""
    url = f"{_qdrant_base_url()}/collections/{collection_name}/points/search"
    payload = {"vector": vector, "limit": limit, "with_payload": True}
    res = requests.post(url, json=payload, timeout=60.0)
    if res.status_code >= 400:
        raise RuntimeError(f"Qdrant search error {res.status_code}: {res.text}")
    data = res.json() or {}
    return data.get("result", []) or []


def _retrieve_chunks(
    collection_name: str,
    query: str,
    top_k: int = 5,
    search_k: int = 20,
    filter_headings: list[str] | None = None
) -> list[dict[str, Any]]:
    """Retrieve relevant chunks from vector store."""
    vector = _ollama_embed(query)
    hits = _qdrant_search(collection_name, vector, limit=search_k)
    if filter_headings:
        lowered = [heading.lower() for heading in filter_headings if heading]
        filtered = [
            hit for hit in hits
            if any(
                heading in str((hit.get("payload") or {}).get("headings_info", "")).lower()
                for heading in lowered
            )
        ]
        if filtered:
            hits = filtered
    return hits[:top_k]


async def _ollama_chat(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    model: str | None = None
) -> str:
    """Call Ollama chat API."""
    payload = {
        "model": model or settings.ollama_code_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3},
    }
    url = f"{settings.ollama_base_url}/api/chat"
    res = await client.post(url, json=payload, timeout=600.0)
    if res.status_code >= 400:
        raise RuntimeError(f"LLM error {res.status_code}: {res.text}")
    data = res.json()
    message = data.get("message") or {}
    return message.get("content", "")


def _extract_json_from_text(raw: str) -> Any | None:
    """Extract JSON object from text that may contain markdown or other formatting."""
    raw = raw.strip()
    if not raw:
        return None

    code_block_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
    if code_block_match:
        raw = code_block_match.group(1).strip()

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


def _extract_code_blocks(text: str) -> list[dict[str, str]]:
    """Extract code blocks from markdown text."""
    pattern = r"```(\w+)?\s*\n(.*?)\n```"
    matches = re.findall(pattern, text, re.DOTALL)

    blocks = []
    for lang, code in matches:
        blocks.append({
            "language": lang.strip() if lang else "text",
            "code": code.strip(),
        })
    return blocks


def _coerce_str_list(value: Any) -> list[str]:
    """Normalize a value into a list of non-empty strings."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_plan_item(item: Any, fallback_id: str) -> dict[str, Any] | None:
    """Normalize a planner item into a root-plan shape."""
    if not isinstance(item, dict):
        return None
    question = str(item.get("question", "")).strip()
    if not question:
        return None
    return {
        "question_id": str(item.get("question_id") or fallback_id).strip(),
        "question": question,
        "question_type": str(item.get("question_type") or "implementation").strip(),
        "toc_page_index": _coerce_str_list(item.get("toc_page_index")),
        "why_this_matters": str(item.get("why_this_matters") or "").strip(),
    }


def _parse_root_plan(raw: str) -> list[dict[str, Any]]:
    """Parse strict JSON planner output into normalized root plan items."""
    obj = _extract_json_from_text(raw)
    if isinstance(obj, dict) and isinstance(obj.get("plan"), list):
        plan_items = []
        for idx, item in enumerate(obj["plan"], start=1):
            normalized = _normalize_plan_item(item, f"q_root_{idx}")
            if normalized:
                plan_items.append(normalized)
        return plan_items
    return []


def _normalize_followup_item(
    item: Any,
    fallback_question_id: str,
    fallback_parent_question_id: str,
    depth: int
) -> dict[str, Any] | None:
    """Normalize a follow-up planner item."""
    if not isinstance(item, dict):
        return None

    question = str(item.get("question", "")).strip()
    if not question:
        return None

    return {
        "question_id": str(item.get("question_id") or fallback_question_id).strip(),
        "parent_question_id": str(
            item.get("parent_question_id") or fallback_parent_question_id
        ).strip(),
        "question": question,
        "question_type": str(item.get("question_type") or "analysis").strip(),
        "toc_page_index": _coerce_str_list(item.get("toc_page_index")),
        "why_this_matters": str(item.get("why_this_matters") or "").strip(),
        "depth": depth,
    }


def _parse_followup_plan(raw: str, depth: int) -> tuple[list[dict[str, Any]], bool, str]:
    """
    Parse follow-up planner output.

    Expected JSON:
    {
      "followups": [
        {
          "question_id": "...",
          "parent_question_id": "...",
          "question": "...",
          "question_type": "...",
          "toc_page_index": ["..."],
          "why_this_matters": "...",
          "depth": 1
        }
      ],
      "should_continue": true,
      "stop_reason": ""
    }
    """
    obj = _extract_json_from_text(raw)
    if not isinstance(obj, dict):
        return [], False, "invalid_json"

    should_continue = bool(obj.get("should_continue", False))
    stop_reason = str(obj.get("stop_reason") or "").strip()

    followups_raw = obj.get("followups", [])
    if not isinstance(followups_raw, list):
        return [], should_continue, stop_reason

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(followups_raw, start=1):
        parent_id = str(item.get("parent_question_id") or "").strip() or "unknown_parent"
        qid = str(item.get("question_id") or f"{parent_id}_d{depth}_f{idx}").strip()
        node = _normalize_followup_item(
            item=item,
            fallback_question_id=qid,
            fallback_parent_question_id=parent_id,
            depth=depth,
        )
        if node:
            normalized.append(node)

    return normalized, should_continue, stop_reason


async def _rag_answer(
    client: httpx.AsyncClient,
    question: str,
    hits: list[dict[str, Any]],
    model: str | None = None
) -> str:
    """Answer a question grounded in retrieved chunks."""
    context_parts: list[str] = []
    for hit in hits[:8]:
        payload = hit.get("payload") or {}
        headings_info = str(payload.get("headings_info", "")).strip()
        chunk_text = str(payload.get("chunk_text", "")).strip()
        if chunk_text:
            context_parts.append(f"[{headings_info}] {chunk_text}")

    context = "\n\n".join(context_parts).strip()

    if not context:
        return (
            "Insufficient evidence found in retrieved paper chunks to answer this question faithfully. "
            "The implementation should treat this point as unresolved and avoid inventing details."
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert computer science researcher and implementation analyst. "
                "Answer the question strictly grounded in the provided paper context. "
                "Do not fabricate missing details. "
                "If evidence is partial, explicitly say what is known and what remains unclear. "
                "Focus on implementation-relevant facts, assumptions, algorithms, interfaces, and constraints."
            )
        },
        {
            "role": "user",
            "content": (
                f"Question:\n{question}\n\n"
                f"Retrieved paper context:\n{context}\n\n"
                "Produce a precise technical answer. "
                "Separate confirmed facts from unresolved or underspecified details."
            )
        }
    ]
    return await _ollama_chat(client, messages, model)


async def _generate_architecture_plan(
    client: httpx.AsyncClient,
    paper_context: str,
    toc: str,
    model: str | None = None
) -> dict[str, Any]:
    """Generate high-level architecture plan from paper."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert software architect. Based on a research paper, "
                "create a high-level implementation architecture plan. "
                "Output strict JSON with shape: "
                '{"title": "...", "overview": "...", "modules": ['
                '{"module_name": "...", "purpose": "...", "complexity": "low|medium|high"}], '
                '"dependencies": [{"from": "...", "to": "..."}], '
                '"language": "python", "framework_suggestions": [...]}'
            )
        },
        {
            "role": "user",
            "content": (
                "Based on this paper, design a demo implementation architecture:\n\n"
                f"Paper context:\n{paper_context}\n\n"
                f"Table of Contents:\n{toc}\n\n"
                "Create a modular architecture with clear separation of concerns. "
                "Identify all key modules needed to demonstrate the core concepts faithfully to the paper "
                "and use the same terminology as much as possible."
            )
        }
    ]

    response = await _ollama_chat(client, messages, model)
    plan = _extract_json_from_text(response)

    if not plan or not isinstance(plan, dict):
        return {
            "title": "Demo Implementation",
            "overview": "Demo implementation of the paper's concepts",
            "modules": [
                {"module_name": "main", "purpose": "Entry point and orchestration", "complexity": "low"},
                {"module_name": "core", "purpose": "Core algorithms and logic", "complexity": "high"},
                {"module_name": "utils", "purpose": "Helper functions and utilities", "complexity": "low"},
            ],
            "dependencies": [],
            "language": "python",
            "framework_suggestions": [],
        }

    return plan


async def _plan_module_root_questions(
    client: httpx.AsyncClient,
    module_info: dict[str, Any],
    architecture_plan: dict[str, Any],
    text_toc: str,
    model: str | None = None
) -> list[dict[str, Any]]:
    """Plan root comprehension questions for a module before codegen."""
    module_name = str(module_info.get("module_name", "module")).strip() or "module"
    purpose = str(module_info.get("purpose", "")).strip()
    complexity = str(module_info.get("complexity", "medium")).strip()

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert CS researcher and software architect. "
                "Generate a module-oriented in-depth reading plan before implementation. "
                "Output strict JSON with shape: "
                "{\"plan\": ["
                "{\"question_id\":\"q_root_1\","
                "\"question\":\"...\","
                "\"question_type\":\"domain|io|algorithm|modification|reference|constraint|evaluation\","
                "\"toc_page_index\":[\"Heading\"],"
                "\"why_this_matters\":\"...\"}"
                "]}"
            )
        },
        {
            "role": "user",
            "content": (
                f"Generate 5 to 7 root questions for faithfully implementing module '{module_name}'.\n\n"
                f"Purpose: {purpose}\n"
                f"Complexity: {complexity}\n\n"
                f"Architecture:\n{json.dumps(architecture_plan, indent=2)}\n\n"
                f"TOC:\n{text_toc}\n\n"
                "The root questions must collectively cover:\n"
                "1. What domain/problem this module belongs to in the paper.\n"
                "2. Key inputs.\n"
                "3. Key outputs.\n"
                "4. Key methods/algorithms used.\n"
                "5. Any highlight modifications to classic/traditional algorithms.\n"
                "6. Any specific references, equations, sections, or prior work needed for faithful implementation.\n"
                "7. Important constraints, assumptions, or edge cases.\n\n"
                "Each question must include toc_page_index matched to relevant TOC headings."
            )
        }
    ]

    raw = await _ollama_chat(client, messages, model)
    plan_items = _parse_root_plan(raw)

    if plan_items:
        return plan_items

    return [
        {
            "question_id": "q_root_1",
            "question": f"What problem/domain in the paper does module '{module_name}' belong to, and what role does it play?",
            "question_type": "domain",
            "toc_page_index": [],
            "why_this_matters": f"Ground the module '{module_name}' in the paper's actual problem setting.",
        },
        {
            "question_id": "q_root_2",
            "question": f"What are the key inputs and expected outputs of module '{module_name}'?",
            "question_type": "io",
            "toc_page_index": [],
            "why_this_matters": f"Define the interface contract for '{module_name}'.",
        },
        {
            "question_id": "q_root_3",
            "question": f"What key methods or algorithms are used by module '{module_name}'?",
            "question_type": "algorithm",
            "toc_page_index": [],
            "why_this_matters": f"Identify the core implementation logic of '{module_name}'.",
        },
        {
            "question_id": "q_root_4",
            "question": f"Does module '{module_name}' modify or adapt any classic algorithm, baseline, or standard method?",
            "question_type": "modification",
            "toc_page_index": [],
            "why_this_matters": f"Capture paper-specific novelty needed for faithful implementation.",
        },
        {
            "question_id": "q_root_5",
            "question": f"What references, equations, sections, or prior work should be consulted to faithfully implement module '{module_name}'?",
            "question_type": "reference",
            "toc_page_index": [],
            "why_this_matters": f"Anchor the implementation of '{module_name}' to authoritative sources.",
        },
        {
            "question_id": "q_root_6",
            "question": f"What important assumptions, constraints, or edge cases affect the implementation of module '{module_name}'?",
            "question_type": "constraint",
            "toc_page_index": [],
            "why_this_matters": f"Prevent incorrect or over-generalized implementation for '{module_name}'.",
        },
    ]


async def _plan_followup_questions(
    client: httpx.AsyncClient,
    module_info: dict[str, Any],
    root_question: str,
    parent_node: dict[str, Any],
    text_toc: str,
    depth: int,
    model: str | None = None
) -> tuple[list[dict[str, Any]], bool, str]:
    """Generate follow-up questions conditioned on current QA state."""
    module_name = str(module_info.get("module_name", "module")).strip() or "module"

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert researcher doing recursive implementation-oriented paper comprehension. "
                "Given the previous answer, propose deeper follow-up questions only if they help faithful implementation. "
                "Output strict JSON with shape: "
                "{\"followups\":["
                "{\"question_id\":\"q_root_1_d1_f1\","
                "\"parent_question_id\":\"q_root_1\","
                "\"question\":\"...\","
                "\"question_type\":\"analysis|algorithm|interface|constraint|reference|gap\","
                "\"toc_page_index\":[\"Heading\"],"
                "\"why_this_matters\":\"...\","
                "\"depth\":1}"
                "],"
                "\"should_continue\":true,"
                "\"stop_reason\":\"\"}"
            )
        },
        {
            "role": "user",
            "content": (
                f"Module: {module_name}\n\n"
                f"Root Question:\n{root_question}\n\n"
                f"Current Question:\n{parent_node['question']}\n\n"
                f"Previous Answer:\n{parent_node['answer']}\n\n"
                f"TOC:\n{text_toc}\n\n"
                "Generate 0 to 3 follow-up questions that target:\n"
                "- missing implementation details\n"
                "- unclear input/output contracts\n"
                "- underspecified algorithmic steps\n"
                "- assumptions or constraints not fully justified\n"
                "- exact sections/equations/prior work needed for faithful implementation\n\n"
                "Do not ask redundant follow-ups if the answer is already implementation-ready."
            )
        }
    ]

    raw = await _ollama_chat(client, messages, model)
    return _parse_followup_plan(raw, depth)


async def _summarize_module_qa_for_codegen(
    client: httpx.AsyncClient,
    module_info: dict[str, Any],
    architecture_plan: dict[str, Any],
    qa_records: list[dict[str, Any]],
    model: str | None = None
) -> str:
    """Summarize QA tree into a polished implementation brief for code generation."""
    module_name = str(module_info.get("module_name", "module")).strip() or "module"
    purpose = str(module_info.get("purpose", "")).strip()

    qa_text_parts: list[str] = []
    for rec in qa_records:
        qa_text_parts.append(
            f"[depth={rec['depth']}][type={rec['question_type']}][insufficient={rec['insufficiency_flag']}]\n"
            f"Q: {rec['question']}\n"
            f"A: {rec['filtered_answer']}\n"
            f"Why it matters: {rec.get('why_this_matters', '')}\n"
        )
    qa_text = "\n\n".join(qa_text_parts)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert implementation planner. "
                "Convert the multi-round module QA records into a polished implementation brief for code generation. "
                "The brief must explicitly cover:\n"
                "- what domain/problem the module belongs to\n"
                "- the module's role in the overall architecture\n"
                "- key inputs\n"
                "- key outputs\n"
                "- key methods/algorithms used\n"
                "- whether the paper modifies or adapts any classic algorithm\n"
                "- important assumptions/constraints/edge cases\n"
                "- specific sections/equations/references/prior work to preserve faithfulness\n"
                "- unresolved ambiguities that should remain TODOs rather than invented\n"
            )
        },
        {
            "role": "user",
            "content": (
                f"Module: {module_name}\n"
                f"Purpose: {purpose}\n\n"
                f"Architecture:\n{json.dumps(architecture_plan, indent=2)}\n\n"
                f"QA Records:\n{qa_text}\n\n"
                "Write a dense, implementation-oriented brief for a code generator."
            )
        }
    ]
    return await _ollama_chat(client, messages, model)


async def _module_progressive_comprehension_qa(
    client: httpx.AsyncClient,
    module_info: dict[str, Any],
    architecture_plan: dict[str, Any],
    collection_name: str,
    text_toc: str,
    paper_title: str,
    arxiv_id: str,
    output_dir: str | None = None,
    model: str | None = None,
    max_depth: int = 0,
    retrieval_top_k: int = 5,
    search_k: int = 25,
    max_insufficiency: int = 2,
) -> dict[str, Any]:
    """
    Module-oriented question-tree progressive comprehension QA.

    Returns:
        {
            "module_name": ...,
            "qa_records": [...],
            "total_records": ...,
            "qa_output_path": ...,
            "implementation_brief": ...,
            "max_depth_used": ...,
            "insufficiency_count": ...,
        }
    """
    module_name = str(module_info.get("module_name", "module")).strip() or "module"

    qa_records: list[dict[str, Any]] = []
    total_records = 0
    insufficiency_count = 0

    qa_output_path = None
    if output_dir:
        qa_dir = Path(output_dir)
        qa_dir.mkdir(parents=True, exist_ok=True)
        qa_output_path = qa_dir / f"{module_name}_qa.jsonl"

    root_plan = await _plan_module_root_questions(
        client=client,
        module_info=module_info,
        architecture_plan=architecture_plan,
        text_toc=text_toc,
        model=model,
    )

    for root_index, root_item in enumerate(root_plan, start=1):
        root_id = root_item.get("question_id") or f"q_root_{root_index}"
        root_question = root_item["question"]
        root_toc = root_item.get("toc_page_index", [])
        root_type = root_item.get("question_type", "analysis")

        hits = _retrieve_chunks(
            collection_name=collection_name,
            query=root_question,
            top_k=retrieval_top_k,
            search_k=search_k,
            filter_headings=root_toc,
        )
        if not hits:
            hits = _retrieve_chunks(
                collection_name=collection_name,
                query=root_question,
                top_k=retrieval_top_k,
                search_k=search_k,
            )

        insufficiency_flag = not bool(hits)
        if insufficiency_flag:
            insufficiency_count += 1

        print(f"[QA][{module_name}] Root question: {root_question} | toc={root_toc}")
        answer = await _rag_answer(client, root_question, hits, model)

        root_record = {
            "type": "module_qa",
            "paper_title": paper_title,
            "arxiv_id": arxiv_id,
            "collection_name": collection_name,
            "module_name": module_name,
            "question_id": root_id,
            "parent_question_id": None,
            "root_question_id": root_id,
            "depth": 0,
            "question_type": root_type,
            "question": root_question,
            "toc_page_index": root_toc,
            "filtered_answer": answer,
            "retrieval_top_k": retrieval_top_k,
            "why_this_matters": root_item.get("why_this_matters", ""),
            "insufficiency_flag": insufficiency_flag,
            "created_at": _utc_now_iso(),
        }
        qa_records.append(root_record)
        total_records += 1

        if qa_output_path:
            with qa_output_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(root_record, ensure_ascii=False) + "\n")

        current_frontier = [
            {
                "question_id": root_id,
                "root_question_id": root_id,
                "question": root_question,
                "answer": answer,
                "toc_page_index": root_toc,
                "question_type": root_type,
            }
        ]

        for depth in range(1, max_depth + 1):
            if insufficiency_count >= max_insufficiency:
                print(
                    f"[QA][{module_name}] Stop expansion due to insufficiency_count="
                    f"{insufficiency_count}"
                )
                break

            next_frontier: list[dict[str, Any]] = []

            for parent_node in current_frontier:
                followups, should_continue, stop_reason = await _plan_followup_questions(
                    client=client,
                    module_info=module_info,
                    root_question=root_question,
                    parent_node=parent_node,
                    text_toc=text_toc,
                    depth=depth,
                    model=model,
                )

                if not should_continue or not followups:
                    if stop_reason:
                        print(
                            f"[QA][{module_name}] No follow-up for parent "
                            f"{parent_node['question_id']} | stop_reason={stop_reason}"
                        )
                    continue

                for idx, followup in enumerate(followups, start=1):
                    question_id = followup.get("question_id") or f"{parent_node['question_id']}_d{depth}_f{idx}"
                    question = followup["question"]
                    toc_page_index = followup.get("toc_page_index", [])
                    question_type = followup.get("question_type", "analysis")

                    hits = _retrieve_chunks(
                        collection_name=collection_name,
                        query=question,
                        top_k=retrieval_top_k,
                        search_k=search_k,
                        filter_headings=toc_page_index,
                    )
                    if not hits:
                        hits = _retrieve_chunks(
                            collection_name=collection_name,
                            query=question,
                            top_k=retrieval_top_k,
                            search_k=search_k,
                        )

                    insufficiency_flag = not bool(hits)
                    if insufficiency_flag:
                        insufficiency_count += 1

                    print(
                        f"[QA][{module_name}] Follow-up depth={depth}: "
                        f"{question} | toc={toc_page_index}"
                    )
                    answer = await _rag_answer(client, question, hits, model)

                    record = {
                        "type": "module_qa",
                        "paper_title": paper_title,
                        "arxiv_id": arxiv_id,
                        "collection_name": collection_name,
                        "module_name": module_name,
                        "question_id": question_id,
                        "parent_question_id": parent_node["question_id"],
                        "root_question_id": root_id,
                        "depth": depth,
                        "question_type": question_type,
                        "question": question,
                        "toc_page_index": toc_page_index,
                        "filtered_answer": answer,
                        "retrieval_top_k": retrieval_top_k,
                        "why_this_matters": followup.get("why_this_matters", ""),
                        "insufficiency_flag": insufficiency_flag,
                        "created_at": _utc_now_iso(),
                    }
                    qa_records.append(record)
                    total_records += 1

                    if qa_output_path:
                        with qa_output_path.open("a", encoding="utf-8") as handle:
                            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

                    next_frontier.append(
                        {
                            "question_id": question_id,
                            "root_question_id": root_id,
                            "question": question,
                            "answer": answer,
                            "toc_page_index": toc_page_index,
                            "question_type": question_type,
                        }
                    )

            if not next_frontier:
                break

            current_frontier = next_frontier

    implementation_brief = await _summarize_module_qa_for_codegen(
        client=client,
        module_info=module_info,
        architecture_plan=architecture_plan,
        qa_records=qa_records,
        model=model,
    )

    return {
        "module_name": module_name,
        "qa_records": qa_records,
        "total_records": total_records,
        "qa_output_path": str(qa_output_path) if qa_output_path else "",
        "implementation_brief": implementation_brief,
        "max_depth_used": max_depth,
        "insufficiency_count": insufficiency_count,
    }


async def _generate_module_code(
    client: httpx.AsyncClient,
    module_info: dict[str, Any],
    architecture_plan: dict[str, Any],
    collection_name: str,
    text_toc: str,
    paper_title: str,
    arxiv_id: str,
    output_dir: str | None = None,
    model: str | None = None
) -> dict[str, Any]:
    """Generate code for a specific module after progressive module comprehension QA."""
    module_name = str(module_info.get("module_name", "module")).strip() or "module"
    purpose = str(module_info.get("purpose", "")).strip()
    complexity = str(module_info.get("complexity", "medium")).strip()
    language = str(architecture_plan.get("language", "python")).strip() or "python"

    # try:
    #     max_depth = max(1, int(os.getenv("MODULE_QA_MAX_DEPTH", "2")))
    # except Exception:
    #     max_depth = 2
    max_depth = 0

    qa_result = await _module_progressive_comprehension_qa(
        client=client,
        module_info=module_info,
        architecture_plan=architecture_plan,
        collection_name=collection_name,
        text_toc=text_toc,
        paper_title=paper_title,
        arxiv_id=arxiv_id,
        output_dir=output_dir or "",
        model=model,
        max_depth=max_depth,
        retrieval_top_k=5,
        search_k=25,
        max_insufficiency=2,
    )

    implementation_brief = qa_result["implementation_brief"]

    if complexity == "high":
        complexity_instruction = (
            "This is a complex module. Implement the full logic structure faithfully where specified. "
            "If the paper leaves details unresolved, preserve them explicitly as TODOs with precise notes. "
            "Do not invent algorithmic details unsupported by the QA brief."
        )
    elif complexity == "medium":
        complexity_instruction = (
            "Implement the main functionality faithfully. "
            "Use TODOs only for genuinely unresolved details."
        )
    else:
        complexity_instruction = (
            "Implement this module fully and cleanly when the QA brief provides enough support."
        )

    messages = [
        {
            "role": "system",
            "content": (
                f"You are an expert {language} developer and research engineer. "
                "Generate clean, well-documented, faithful implementation code. "
                "You must ground the implementation in the provided module comprehension brief. "
                "Use the same terminology as the paper. "
                "Preserve key interfaces, algorithms, assumptions, and constraints from the brief. "
                "If certain details remain unresolved in the brief, keep them as explicit TODOs rather than hallucinating. "
                "Output code in a markdown code block with language tag."
            )
        },
        {
            "role": "user",
            "content": (
                f"Generate code for module '{module_name}'.\n\n"
                f"Purpose: {purpose}\n"
                f"Complexity: {complexity}\n"
                f"Language: {language}\n\n"
                f"Overall architecture:\n{json.dumps(architecture_plan, indent=2)}\n\n"
                f"Module comprehension brief:\n{implementation_brief}\n\n"
                f"{complexity_instruction}\n\n"
                "The codegen must faithfully cover:\n"
                "- what problem/domain this module belongs to\n"
                "- key input\n"
                "- key output\n"
                "- key methods/algorithms used\n"
                "- any modifications to classic/traditional methods\n"
                "- any specific references or cues needed for faithful implementation\n\n"
                f"Generate complete runnable {language} code with appropriate imports, classes, functions, "
                "docstrings, and type hints."
            )
        }
    ]

    response = await _ollama_chat(client, messages, model)
    code_blocks = _extract_code_blocks(response)

    main_code = ""
    for block in code_blocks:
        if block["language"] in {language, "python", "typescript", "javascript", "java"}:
            main_code = block["code"]
            break

    if not main_code and code_blocks:
        main_code = code_blocks[0]["code"]

    if not main_code and language == "python":
        main_code = f'''"""
{module_name} module.

{purpose}
"""

# TODO: faithful implementation could not be fully synthesized from the current QA brief.

def main():
    """Main entry point for {module_name}."""
    print("TODO: Implement {module_name}")
    pass


if __name__ == "__main__":
    main()
'''

    return {
        "module_name": module_name,
        "filename": f"{module_name}.py" if language == "python" else f"{module_name}.{language}",
        "code": main_code,
        "purpose": purpose,
        "complexity": complexity,
        "qa_total_records": qa_result["total_records"],
        "qa_output_path": qa_result["qa_output_path"],
        "qa_max_depth_used": qa_result["max_depth_used"],
        "qa_insufficiency_count": qa_result["insufficiency_count"],
        "implementation_brief": implementation_brief,
    }


async def _generate_readme(
    client: httpx.AsyncClient,
    architecture_plan: dict[str, Any],
    modules: list[dict[str, Any]],
    paper_title: str,
    model: str | None = None
) -> str:
    """Generate README documentation."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a technical writer. Create a clear, concise README.md for a demo implementation. "
                "Include overview, architecture, setup instructions, usage, and notes about placeholders."
            )
        },
        {
            "role": "user",
            "content": (
                f"Generate a README.md for this demo implementation:\n\n"
                f"Paper: {paper_title}\n"
                f"Architecture:\n{json.dumps(architecture_plan, indent=2)}\n\n"
                "Modules:\n"
                + "\n".join(
                    [
                        (
                            f"- {m['module_name']}: {m['purpose']} "
                            f"(complexity={m['complexity']}, qa_records={m.get('qa_total_records', 0)})"
                        )
                        for m in modules
                    ]
                )
            )
        }
    ]

    response = await _ollama_chat(client, messages, model)

    code_blocks = _extract_code_blocks(response)
    for block in code_blocks:
        if block["language"] in {"markdown", "md", ""}:
            return block["code"]

    if "# " in response:
        return response

    return f"""# Demo Implementation: {paper_title}
## Overview

This is a demo implementation based on the research paper: {paper_title}

## Architecture
{architecture_plan.get('overview', '')}

## Modules
{''.join([f"- **{m['module_name']}**: {m['purpose']}" + chr(10) for m in modules])}

## Setup
```bash
# Install dependencies (if any)
pip install -r requirements.txt
```
"""
async def paper_to_demo_code_new(args: dict[str, Any]) -> dict[str, Any]:
    """
    Generate demo code implementation from a research paper using recursive QA.
    """
    payload = args or {}
    
    arxiv_id = str(payload.get("arxiv_id", "")).strip()
    paper_html = str(payload.get("paper_html", "")).strip()
    paper_md = str(payload.get("paper_md", "")).strip()
    paper_title = str(payload.get("paper_title", "")).strip() or "Untitled Paper"
    output_dir = str(payload.get("output_dir", "")).strip()
    model = str(payload.get("model", "")).strip() or None
    max_modules = int(payload.get("max_modules", 7))
    
    if not paper_md and not paper_html and arxiv_id:
        print(f"Fetching paper HTML for arXiv ID: {arxiv_id}")
        paper_html = await fetch_full_content(arxiv_id)
    
    if not paper_md and not paper_html:
        raise ValueError("One of paper_md, paper_html, or arxiv_id must be provided")

    if paper_md:
        print("Parsing and chunking paper markdown...")
        chunking_result = markdown_parsing_chunking_upsert(
            paper_md=paper_md,
            paper_title=paper_title,
            arxiv_id=arxiv_id
        )
    else:
        print("Parsing and chunking paper HTML...")
        chunking_result = html_parsing_chunking_upsert(
            html_content=paper_html,
            paper_title=paper_title,
            arxiv_id=arxiv_id,
            chunk_size=6000,
            chunk_overlap=0
        )
    
    collection_name = chunking_result["collection_name"]
    text_toc = chunking_result["text_toc"]
    print(f"Created collection: {collection_name}")
    print(f"Upserted {chunking_result['chunks_upserted']} chunks")
    
    overview_query = "What is the main contribution and methodology of this paper?"
    overview_chunks = _retrieve_chunks(collection_name, overview_query, top_k=3)
    
    overview_context = []
    for hit in overview_chunks:
        payload_data = hit.get("payload") or {}
        chunk_text = payload_data.get("chunk_text", "")
        overview_context.append(chunk_text)
    paper_context = "\n\n".join(overview_context)
    
    print("Generating architecture plan...")
    async with httpx.AsyncClient(timeout=600) as client:
        architecture_plan = await _generate_architecture_plan(
            client, paper_context, text_toc, model
        )
    
    print(f"Architecture plan: {architecture_plan.get('title', 'Demo')}")
    print(f"Modules: {len(architecture_plan.get('modules', []))}")
    
    modules_to_generate = architecture_plan.get("modules", [])[:max_modules]
    
    generated_modules = []
    async with httpx.AsyncClient(timeout=600) as client:
        for module_info in modules_to_generate:
            module_name = module_info.get("module_name", "module")
            print(f"Generating code for module: {module_name}")

            module_code = await _generate_module_code(
                client=client,
                module_info=module_info,
                architecture_plan=architecture_plan,
                collection_name=collection_name,
                text_toc=text_toc,
                paper_title=paper_title,
                arxiv_id=arxiv_id,
                output_dir=output_dir,
                model=model
            )
            generated_modules.append(module_code)
            print(f"  Generated {module_code['filename']} ({len(module_code['code'])} chars)")
            
        print("Generating README...")
        readme_content = await _generate_readme(
            client, architecture_plan, generated_modules, paper_title, model
        )

    saved_files = []
    if output_dir:
        import os
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        for mod in generated_modules:
            file_path = out_path / mod["filename"]
            file_path.write_text(mod["code"], encoding="utf-8")
            saved_files.append(str(file_path))
            
        readme_path = out_path / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")
        saved_files.append(str(readme_path))
        
        meta_path = out_path / "demo_metadata.json"
        metadata = {
            "arxiv_id": arxiv_id,
            "paper_title": paper_title,
            "generated_at": _utc_now_iso(),
            "architecture": architecture_plan,
        }
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        saved_files.append(str(meta_path))

    return {
        "arxiv_id": arxiv_id,
        "paper_title": paper_title,
        "output_dir": output_dir,
        "collection_name": collection_name,
        "chunks_upserted": chunking_result["chunks_upserted"],
        "architecture_plan": architecture_plan,
        "modules": generated_modules,
        "readme": readme_content,
        "saved_files": saved_files
    }
