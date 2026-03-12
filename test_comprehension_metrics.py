import asyncio
import json
import os
from typing import Any

from apps.backend.app.tools.academic_search import academic_search, Comprehension_of_papers_withnoticablemetrics


REQUIRED_FIELDS = [
    "type",
    "paper_title",
    "arxiv_id",
    "collection_name",
    "question_id",
    "parent_question_id",
    "root_question_id",
    "depth",
    "question_type",
    "question",
    "toc_page_index",
    "filtered_answer",
    "retrieval_top_k"
]


def _load_jsonl(path: str) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    if not os.path.exists(path):
        errors.append(f"JSONL not found: {path}")
        return records, errors
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception as exc:
                errors.append(f"Line {lineno}: invalid JSON ({exc})")
                continue
            if isinstance(obj, dict):
                records.append(obj)
            else:
                errors.append(f"Line {lineno}: JSON is not an object")
    return records, errors


def _validate_record_schema(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"Missing field: {field}")
    if record.get("type") != "paper_qa":
        errors.append("type must be 'paper_qa'")
    if not isinstance(record.get("question_id"), str):
        errors.append("question_id must be a string")
    if not isinstance(record.get("root_question_id"), str):
        errors.append("root_question_id must be a string")
    if not isinstance(record.get("depth"), int):
        errors.append("depth must be an int")
    if not isinstance(record.get("question"), str):
        errors.append("question must be a string")
    if not isinstance(record.get("question_type"), str):
        errors.append("question_type must be a string")
    if not isinstance(record.get("filtered_answer"), str):
        errors.append("filtered_answer must be a string")
    toc = record.get("toc_page_index")
    if not isinstance(toc, list) or any(not isinstance(item, str) for item in toc):
        errors.append("toc_page_index must be a list of strings")
    if not isinstance(record.get("retrieval_top_k"), int):
        errors.append("retrieval_top_k must be an int")
    return errors


def _validate_depth_behavior(records: list[dict[str, Any]], max_depth: int) -> list[str]:
    errors: list[str] = []
    by_id = {rec.get("question_id"): rec for rec in records if isinstance(rec.get("question_id"), str)}

    for rec in records:
        question_id = rec.get("question_id")
        depth = rec.get("depth")
        parent_id = rec.get("parent_question_id")
        root_id = rec.get("root_question_id")

        if isinstance(depth, int) and depth > max_depth:
            errors.append(f"{question_id}: depth {depth} exceeds max_depth {max_depth}")

        if depth == 0:
            if parent_id is not None:
                errors.append(f"{question_id}: root depth has non-null parent_question_id")
            if question_id != root_id:
                errors.append(f"{question_id}: root_question_id must equal question_id")
        else:
            if parent_id is None:
                errors.append(f"{question_id}: non-root depth missing parent_question_id")
            parent = by_id.get(parent_id)
            if parent is None:
                errors.append(f"{question_id}: parent_question_id {parent_id} not found")
            else:
                parent_depth = parent.get("depth")
                parent_root = parent.get("root_question_id")
                if isinstance(parent_depth, int) and isinstance(depth, int):
                    if parent_depth != depth - 1:
                        errors.append(
                            f"{question_id}: depth {depth} not parent depth+1 ({parent_depth})"
                        )
                if parent_root != root_id:
                    errors.append(f"{question_id}: root_question_id mismatch vs parent")
    return errors


def _verify_jsonl_schema_and_depth(path: str) -> bool:
    max_depth_raw = os.getenv("COMPREHENSION_MAX_DEPTH", "1")
    try:
        max_depth = max(1, int(max_depth_raw))
    except Exception:
        max_depth = 1

    records, load_errors = _load_jsonl(path)
    if load_errors:
        print("\nJSONL load errors:")
        for err in load_errors:
            print(f"  - {err}")
        return False
    if not records:
        print("\nJSONL has no records to validate.")
        return False

    schema_errors: list[str] = []
    for rec in records:
        schema_errors.extend(_validate_record_schema(rec))

    depth_errors = _validate_depth_behavior(records, max_depth)

    if schema_errors or depth_errors:
        print("\nJSONL validation errors:")
        for err in schema_errors + depth_errors:
            print(f"  - {err}")
        return False

    print(f"\nJSONL schema + depth validation passed ({len(records)} records, max_depth={max_depth}).")
    return True

async def main():
    print("Testing academic_search + Comprehension_of_papers_withnoticablemetrics pipeline...\n")
    
    # Step 1: Search for papers
    print("=" * 80)
    print("Step 1: Searching for papers to test comprehension filter")
    print("=" * 80)
    try:
        search_result = await academic_search({
            "query": "refine HTL progressively with AI agents for chip design",
            "limit": 5,
            "from_year": 2024,
            "to_year": 2026,
        })
        
        papers = search_result.get("papers", [])
        print(f"Found {len(papers)} papers.")
        for i, paper in enumerate(papers, 1):
            print(f"  ==== {i}. {paper['title']}, {paper['url']} ====")
            print(f"  {paper['abstract']}...")  # Print a preview of the abstract
            
        if not papers:
            print("No papers found. Exiting.")
            return

        # Step 2: Comprehension testing
        print("\n" + "=" * 80)
        print("Step 2: Processing papers with Comprehension tool")
        print("=" * 80)
        
        comprehension_response = await Comprehension_of_papers_withnoticablemetrics({
            "papers": papers,
        })
        
        comprehension_result = comprehension_response.get("results", [])
        
        print(f"\nResults for {len(comprehension_result)} processed papers:\n")
        print(f"\nTotal papers processed: {comprehension_response.get('papers_processed')}")
        passed = 0
        for i, res in enumerate(comprehension_result, 1):
            title = res.get('title', 'Unknown Title')
            print(f"  {i}. {title}")
            print(f"     Passed Filter: {res.get('passed_filter')}")
            
            if res.get('error'):
                print(f"     Error: {res.get('error')}")
                
            if res.get('passed_filter'):
                passed += 1
                if 'answer' in res:
                    ans = res.get('answer', 'N/A')
                    ans_preview = (ans[:150] + '...') if len(ans) > 150 else ans
                    print(f"     QA Answer: {ans_preview}")
            print()
            
        print(f"\nTotal papers that passed the filter: {passed} out of {len(comprehension_result)}")

        # Step 3: Validate JSONL schema + depth behavior
        print("\n" + "=" * 80)
        print("Step 3: Validating JSONL schema + depth behavior")
        print("=" * 80)

        validated_any = False
        for res in comprehension_result:
            output_path = res.get("output_path")
            if not output_path:
                continue
            validated_any = True
            print(f"\nValidating JSONL: {output_path}")
            _verify_jsonl_schema_and_depth(output_path)

        if not validated_any:
            print("\nNo JSONL output_path found in results; skipping validation.")
        
    except Exception as e:
        print(f"Error: {e}\n")
    

if __name__ == "__main__":
    asyncio.run(main())
