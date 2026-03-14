"""
Simplified paper-to-demo-code tool.
Given a paper HTML, generates a demo implementation with overall framework and modules.
Uses placeholders for complex parts that need further details.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

import httpx
import requests

from ..config import settings
from .academic_search import fetch_full_content, html_parsing_chunking_upsert


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


def _qdrant_search(collection_name: str, vector: list[float], limit: int = 5) -> list[dict[str, Any]]:
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
        "options": {"temperature": 0.3}
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
    
    # Try to extract from markdown code blocks first
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
    # Match markdown code blocks with optional language
    pattern = r"```(\w+)?\s*\n(.*?)\n```"
    matches = re.findall(pattern, text, re.DOTALL)
    
    blocks = []
    for lang, code in matches:
        blocks.append({
            "language": lang.strip() if lang else "text",
            "code": code.strip()
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
    """Normalize a planner item into the module retrieval shape."""
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
    """Parse strict JSON planner output into normalized plan items."""
    obj = _extract_json_from_text(raw)
    if isinstance(obj, dict) and isinstance(obj.get("plan"), list):
        plan_items = []
        for idx, item in enumerate(obj["plan"], start=1):
            normalized = _normalize_plan_item(item, f"q_root_{idx}")
            if normalized:
                plan_items.append(normalized)
        return plan_items
    return []


async def _plan_module_retrieval(
    client: httpx.AsyncClient,
    module_info: dict[str, Any],
    architecture_plan: dict[str, Any],
    text_toc: str,
    model: str | None = None
) -> dict[str, Any]:
    """Create a planner question and TOC filter for module-specific retrieval."""
    module_name = str(module_info.get("module_name", "module")).strip() or "module"
    purpose = str(module_info.get("purpose", "")).strip()
    complexity = str(module_info.get("complexity", "medium")).strip()

    planner_messages = [
        {
            "role": "system",
            "content": (
                "You are an expert computer science researcher and software architect. "
                "Generate one retrieval planning item for implementing a module from a paper. "
                "Output strict JSON with shape: {\"plan\": ["
                "{\"question_id\":\"q_root_1\",\"question\":\"...\",\"question_type\":\"implementation\","
                "\"toc_page_index\":[\"Heading\"],\"why_this_matters\":\"...\"}]}"
            )
        },
        {
            "role": "user",
            "content": (
                f"Generate one implementation-focused retrieval question for the module '{module_name}'.\n\n"
                f"Purpose: {purpose}\n"
                f"Complexity: {complexity}\n\n"
                f"Overall architecture:\n{json.dumps(architecture_plan, indent=2)}\n\n"
                f"TOC:\n{text_toc}\n\n"
                "The question should target the paper sections most useful for faithful code generation. "
                "toc_page_index must match relevant TOC headings."
            )
        }
    ]
    planner_raw = await _ollama_chat(client, planner_messages, model)
    plan_items = _parse_root_plan(planner_raw)

    if plan_items:
        return plan_items[0]

    fallback_question = (
        f"What implementation details, algorithms, inputs, outputs, and constraints are described for the "
        f"'{module_name}' module used for {purpose or module_name}?"
    )
    return {
        "question_id": "q_root_1",
        "question": fallback_question,
        "question_type": "implementation",
        "toc_page_index": [],
        "why_this_matters": f"Ground the {module_name} module in the paper's described method.",
    }


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
                f"Based on this paper, design a demo implementation architecture:\n\n"
                f"Paper context:\n{paper_context}\n\n"
                f"Table of Contents:\n{toc}\n\n"
                f"Create a modular architecture with clear separation of concerns. "
                f"Identify all key modules needed to demonstrate the core concepts faithfully to the paper and use the same terminology as much as possible. "
            )
        }
    ]
    
    response = await _ollama_chat(client, messages, model)
    plan = _extract_json_from_text(response)
    
    if not plan or not isinstance(plan, dict):
        # Fallback plan
        return {
            "title": "Demo Implementation",
            "overview": "Demo implementation of the paper's concepts",
            "modules": [
                {"module_name": "main", "purpose": "Entry point and orchestration", "complexity": "low"},
                {"module_name": "core", "purpose": "Core algorithms and logic", "complexity": "high"},
                {"module_name": "utils", "purpose": "Helper functions and utilities", "complexity": "low"}
            ],
            "dependencies": [],
            "language": "python",
            "framework_suggestions": []
        }
    
    return plan


async def _generate_module_code(
    client: httpx.AsyncClient,
    module_info: dict[str, Any],
    architecture_plan: dict[str, Any],
    collection_name: str,
    text_toc: str,
    model: str | None = None
) -> dict[str, Any]:
    """Generate code for a specific module."""
    module_name = module_info.get("module_name", "module")
    purpose = module_info.get("purpose", "")
    complexity = module_info.get("complexity", "medium")
    language = architecture_plan.get("language", "python")

    retrieval_plan = await _plan_module_retrieval(
        client,
        module_info,
        architecture_plan,
        text_toc,
        model
    )
    planned_question = retrieval_plan.get("question") or (
        f"{purpose or module_name} implementation details algorithm"
    )
    toc_page_index = retrieval_plan.get("toc_page_index", [])
    filtered_hits = _retrieve_chunks(
        collection_name,
        planned_question,
        top_k=5,
        search_k=25,
        filter_headings=toc_page_index
    )
    if not filtered_hits:
        filtered_hits = _retrieve_chunks(
            collection_name,
            planned_question,
            top_k=5
        )

    # Build context from filtered hits
    context_parts = []
    for hit in filtered_hits[:5]:
        payload = hit.get("payload") or {}
        chunk_text = payload.get("chunk_text", "")
        headings_info = payload.get("headings_info", "")
        context_parts.append(f"[{headings_info}] {chunk_text}")
    context = "\n".join(context_parts)
    
    # Adjust instructions based on complexity
    if complexity == "high":
        complexity_instruction = (
            "This is a complex module. Implement the core logic structure with detailed "
            "placeholders and TODO comments for parts requiring further specification. "
            "Include comprehensive docstrings and type hints."
        )
    elif complexity == "medium":
        complexity_instruction = (
            "This is a medium-complexity module. Implement the main functionality with "
            "some placeholders for details that need refinement."
        )
    else:
        complexity_instruction = (
            "This is a simple module. Implement it fully with clean, working code."
        )
    
    messages = [
        {
            "role": "system",
            "content": (
                f"You are an expert {language} developer. Generate clean, well-documented code "
                f"for a demo implementation. Use appropriate design patterns and best practices. "
                f"For parts which have unspecified details, use placeholders with TODO comments explaining what needs to be implemented. "
                f"For all specified algorithms or methods, provide a faithful implementation according to the following provided paper context. Do not omit any technical details that are present in the paper. Use the same terminology as the paper. "
                f"Output the code in a markdown code block with language tag."
            )
        },
        {
            "role": "user",
            "content": (
                f"Generate code for the '{module_name}' module.\n\n"
                f"Purpose: {purpose}\n"
                f"Complexity: {complexity}\n"
                f"Language: {language}\n\n"
                f"{complexity_instruction}\n\n"
                f"Planner question: {planned_question}\n"
                f"Planner toc_page_index: {json.dumps(toc_page_index)}\n"
                f"Why this matters: {retrieval_plan.get('why_this_matters', '')}\n\n"
                f"Paper context:\n{context}\n\n"
                f"Overall architecture:\n{json.dumps(architecture_plan, indent=2)}\n\n"
                f"Generate complete, runnable {language} code with appropriate imports, "
                f"classes, functions, and documentation."
            )
        }
    ]
    
    response = await _ollama_chat(client, messages, model)
    code_blocks = _extract_code_blocks(response)
    
    # Find the main code block
    main_code = ""
    for block in code_blocks:
        if block["language"] in {language, "python", "typescript", "javascript", "java"}:
            main_code = block["code"]
            break
    
    if not main_code and code_blocks:
        main_code = code_blocks[0]["code"]
    
    if not main_code:
        # Fallback code
        if language == "python":
            main_code = f'''"""
{module_name} module.

{purpose}
"""

# TODO: Implement {module_name} functionality
# Placeholder implementation

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
        "planner_question": planned_question,
        "toc_page_index": toc_page_index
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
                f"Modules:\n"
                + "\n".join([f"- {m['module_name']}: {m['purpose']}" for m in modules])
            )
        }
    ]
    
    response = await _ollama_chat(client, messages, model)
    
    # Extract markdown if wrapped in code block
    code_blocks = _extract_code_blocks(response)
    for block in code_blocks:
        if block["language"] in {"markdown", "md", ""}:
            return block["code"]
    
    # If no code block, return as-is
    if "# " in response:
        return response
    
    # Fallback README
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

## Usage
```bash
# Run the main module
python main.py
```

## Notes
This is a demo implementation with some placeholders for complex components.
All modules need to be implemented with actual logic based on the paper's methodology.
Modules marked as "high" complexity may contain TODO comments indicating areas
that need further specification and implementation.

## Implementation Status
- Framework: ✓ Complete
- Core modules: ⚠️ Partial (with placeholders)
- Complex algorithms: ⚠️ Requires further details

"""


async def paper_to_demo_code(args: dict[str, Any]) -> dict[str, Any]:
    """
    Generate demo code implementation from a research paper.
    
    Args:
        args: Dictionary with keys:
            - arxiv_id: ArXiv ID of the paper
            - paper_html: HTML content of the paper (optional if arxiv_id provided)
            - paper_title: Title of the paper
            - output_dir: Directory to save generated code (optional)
            - model: LLM model to use (optional)
            - max_modules: Maximum number of modules to generate (default: 7)
    
    Returns:
        Dictionary with generated code and metadata
    """
    payload = args or {}
    
    # Get paper HTML content
    arxiv_id = str(payload.get("arxiv_id", "")).strip()
    paper_html = str(payload.get("paper_html", "")).strip()
    paper_title = str(payload.get("paper_title", "")).strip() or "Untitled Paper"
    output_dir = str(payload.get("output_dir", "")).strip()
    model = str(payload.get("model", "")).strip() or None
    max_modules = int(payload.get("max_modules", 7))
    
    if not paper_html and arxiv_id:
        print(f"Fetching paper HTML for arXiv ID: {arxiv_id}")
        paper_html = await fetch_full_content(arxiv_id)
    
    if not paper_html:
        raise ValueError("Either paper_html or arxiv_id must be provided")
    
    # Parse and chunk the HTML
    print("Parsing and chunking paper HTML...")
    chunking_result = html_parsing_chunking_upsert(
        html_content=paper_html,
        paper_title=paper_title,
        arxiv_id=arxiv_id,
        chunk_size=1200,
        chunk_overlap=200
    )
    
    collection_name = chunking_result["collection_name"]
    text_toc = chunking_result["text_toc"]
    print(f"Created collection: {collection_name}")
    print(f"Upserted {chunking_result['chunks_upserted']} chunks")
    
    # Get paper overview context
    overview_query = "What is the main contribution and methodology of this paper?"
    overview_chunks = _retrieve_chunks(collection_name, overview_query, top_k=3)
    
    overview_context = []
    for hit in overview_chunks:
        payload_data = hit.get("payload") or {}
        chunk_text = payload_data.get("chunk_text", "")
        overview_context.append(chunk_text)
    paper_context = "\n\n".join(overview_context)
    
    # Generate architecture plan
    print("Generating architecture plan...")
    async with httpx.AsyncClient(timeout=600) as client:
        architecture_plan = await _generate_architecture_plan(
            client, paper_context, text_toc, model
        )
    
    print(f"Architecture plan: {architecture_plan.get('title', 'Demo')}")
    print(f"Modules: {len(architecture_plan.get('modules', []))}")
    
    # Limit modules
    modules_to_generate = architecture_plan.get("modules", [])[:max_modules]
    
    # Generate code for each module
    generated_modules = []
    async with httpx.AsyncClient(timeout=600) as client:
        for module_info in modules_to_generate:
            module_name = module_info.get("module_name", "module")
            print(f"Generating code for module: {module_name}")

            # Generate module code
            module_code = await _generate_module_code(
                client,
                module_info,
                architecture_plan,
                collection_name,
                text_toc,
                model
            )
            generated_modules.append(module_code)
            print(f"  Generated {module_code['filename']} ({len(module_code['code'])} chars)")
        
        # Generate README
        print("Generating README...")
        readme_content = await _generate_readme(
            client, architecture_plan, generated_modules, paper_title, model
        )
    
    # Save to disk if output_dir specified
    saved_files = []
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save README
        readme_path = output_path / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")
        saved_files.append(str(readme_path))
        print(f"Saved: {readme_path}")
        
        # Save module files
        for module in generated_modules:
            module_path = output_path / module["filename"]
            module_path.write_text(module["code"], encoding="utf-8")
            saved_files.append(str(module_path))
            print(f"Saved: {module_path}")
        
        # Save metadata
        metadata = {
            "paper_title": paper_title,
            "arxiv_id": arxiv_id,
            "collection_name": collection_name,
            "architecture_plan": architecture_plan,
            "generated_at": _utc_now_iso(),
            "modules": [
                {
                    "filename": m["filename"],
                    "purpose": m["purpose"],
                    "complexity": m["complexity"]
                }
                for m in generated_modules
            ]
        }
        metadata_path = output_path / "demo_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        saved_files.append(str(metadata_path))
        print(f"Saved: {metadata_path}")
    
    # Return result
    result = {
        "paper_title": paper_title,
        "arxiv_id": arxiv_id,
        "collection_name": collection_name,
        "text_toc": text_toc,
        "chunks_upserted": chunking_result["chunks_upserted"],
        "architecture_plan": architecture_plan,
        "modules": generated_modules,
        "readme": readme_content,
        "output_dir": output_dir,
        "saved_files": saved_files,
        "status": "success"
    }
    
    return result
