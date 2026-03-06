from typing import Any
import httpx
from ...config import settings


async def search_academic(args: dict[str, Any]) -> dict:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("Query is required")

    limit_raw = args.get("limit", 5)
    try:
        limit = int(limit_raw)
    except Exception:
        limit = 5
    limit = max(1, min(limit, 20))

    url = f"{settings.semantic_scholar_base}/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": str(limit),
        "fields": "title,authors,year,abstract,url,citationCount"
    }

    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(url, params=params, headers={"User-Agent": "AvaClaw/0.1"})
    if res.status_code >= 400:
        raise RuntimeError(f"Semantic Scholar error {res.status_code}: {res.text}")

    data = res.json()
    papers = []
    for paper in data.get("data", []) or []:
        papers.append(
            {
                "title": paper.get("title", ""),
                "authors": [a.get("name") for a in paper.get("authors", []) if a.get("name")],
                "year": paper.get("year"),
                "citationCount": paper.get("citationCount", 0),
                "abstract": paper.get("abstract", ""),
                "url": paper.get("url", "")
            }
        )

    return {"papers": papers}
