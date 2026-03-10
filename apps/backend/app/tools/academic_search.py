from typing import Any

import httpx

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
        "sort": "relevance_score:desc",
        "per-page": str(limit),
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

import requests
async def _ollama_chat(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    model: str | None
) -> str:
    payload = {
        "model": settings.ollama_model,
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
