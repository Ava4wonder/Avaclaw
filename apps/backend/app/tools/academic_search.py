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
    limit = max(1, min(limit, 20))

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

        papers.append(
            {
                "title": paper.get("title", ""),
                "authors": authors,
                "year": paper.get("publication_year"),
                "citationCount": paper.get("cited_by_count", 0),
                "abstract": abstract,
                "url": pdf_url or landing_page_url or paper.get("id", "")
            }
        )

    return {"papers": papers}
