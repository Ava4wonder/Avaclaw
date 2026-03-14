import asyncio
import json
import os
from apps.backend.app.tools.paper_to_demo_code import paper_to_demo_code
from apps.backend.app.tools.paper_to_code import paper_to_code
from apps.backend.app.tools.academic_search import _llm_filter, academic_search


import httpx
import requests

from apps.backend.app.config import settings


async def main():
    print("Testing paper_to_demo_code function...\n")
    # Step 1: Search for papers
    print("=" * 80)
    print("Step 1: Searching for papers to test comprehension filter")
    print("=" * 80)
    try:
        # search_result = await academic_search({
        #     "query": "refine HTL progressively with AI agents for chip design",
        #     "limit": 0,
        #     "from_year": 2024,
        #     "to_year": 2026,
        # })
        
        # papers = search_result.get("papers", [])
        # print(f"Found {len(papers)} papers.")
        # for i, paper in enumerate(papers, 1):
        #     print(f"  ==== {i}. {paper['title']}, {paper['url']} ====")
        #     print(f"  {paper['abstract']}...")  # Print a preview of the abstract
            
        # if not papers:
        #     print("No papers found. Exiting.")
        #     return
        
        async with httpx.AsyncClient(timeout=60) as client:
            # for paper in papers:
                # abstract = str(paper.get("abstract", "")).strip()
                # passed = await _llm_filter(client, abstract, settings.ollama_model)
                # paper_result = {
                #     "title": paper.get("title", ""),
                #     "arxiv_id": paper.get("arxiv_id", ""),
                #     "passed_filter": passed
                # }
                # if not passed:
                #     results.append(paper_result)
                #     continue

                # arxiv_id = str(paper.get("arxiv_id", "")).strip()
                # if not arxiv_id:
                #     paper_result["error"] = "Missing arxiv_id"
                #     results.append(paper_result)
                #     continue

                # arxiv_id = "2508.14053"  # "MAHL" for testing
                paper_html = open(os.path.join(os.path.dirname(__file__), "alphaevolve.html"), encoding="utf-8").read()

                try:
                    # Test case: Generate demo code for a paper
                    print("=" * 80)
                    # print(f"Test: Generating demo code for paper with arXiv ID '{arxiv_id}'")
                    print("=" * 80)
                    
                    try:
                        result = await paper_to_demo_code({
                            # "arxiv_id": arxiv_id,  # Use the actual arXiv ID\
                            "paper_html": paper_html,
                            "paper_title": "Demo Paper Implementation",
                            "output_dir": "./demo_output",
                            "max_modules": 25
                        })
                        
                        print(f"\n✓ Successfully generated demo code!")
                        print(f"  Paper: {result['paper_title']}")
                        print(f"  ArXiv ID: {result['arxiv_id']}")
                        print(f"  Collection: {result['collection_name']}")
                        print(f"  Chunks upserted: {result['chunks_upserted']}")
                        print(f"  Output directory: {result['output_dir']}")
                        print(f"\nArchitecture Plan:")
                        print(f"  Title: {result['architecture_plan'].get('title', 'N/A')}")
                        print(f"  Overview: {result['architecture_plan'].get('overview', 'N/A')[:100]}...")
                        print(f"  Language: {result['architecture_plan'].get('language', 'N/A')}")
                        print(f"\nModules generated:")
                        for i, module in enumerate(result['modules'], 1):
                            print(f"  {i}. {module['filename']}")
                            print(f"     Purpose: {module['purpose']}")
                            print(f"     Complexity: {module['complexity']}")
                            print(f"     Code length: {len(module['code'])} chars")
                        
                        print(f"\nSaved files:")
                        for filepath in result['saved_files']:
                            print(f"  - {filepath}")
                        
                        print(f"\n{'=' * 80}")
                        print("Sample README:")
                        print("=" * 80)
                        print(result['readme'][:500])
                        print("...\n")
                        
                    except Exception as e:
                        print(f"✗ Error: {e}")
                        import traceback
                        traceback.print_exc()

                except Exception as e:
                    print(f"✗ Error processing paper '{paper.get('title', 'N/A')}': {e}")
                    import traceback
                    traceback.print_exc()
    
    except Exception as e:
        print(f"Error: {e}\n")
    

if __name__ == "__main__":
    asyncio.run(main())
