import asyncio
import json
from apps.backend.app.tools.paper_to_code import paper_to_code
from apps.backend.app.tools.academic_search import academic_search

import httpx
from apps.backend.app.config import settings


async def main():
    print("Testing paper_to_code function...\n")
    
    # Step 1: Search for papers
    print("=" * 80)
    print("Step 1: Searching for papers")
    print("=" * 80)
    try:
        search_result = await academic_search({
            "query": "refine HTL progressively with AI agents for chip design",
            "limit": 0,
            "from_year": 2024,
            "to_year": 2026,
        })
        
        papers = search_result.get("papers", [])
        print(f"Found {len(papers)} papers.")
        for i, paper in enumerate(papers, 1):
            print(f"  {i}. {paper['title']}")
            print(f"     URL: {paper['url']}")
            print(f"     Abstract preview: {paper['abstract'][:200]}...")
            
        if not papers:
            print("No papers found. Exiting.")
            return
        
        # Step 2: Test paper_to_code with specific arxiv_id
        arxiv_id = "2508.14053"  # MAHL paper for testing
        
        print("\n" + "=" * 80)
        print(f"Step 2: Generating code from paper with arXiv ID '{arxiv_id}'")
        print("=" * 80)
        
        try:
            result = await paper_to_code({
                "arxiv_id": arxiv_id,
                "paper_title": "Progressive Paper to Code Implementation",
                "repo_root": "./output_code",
                "max_iterations": 3,
                "questions_per_iteration": 4,
                "max_questions": 24,
                "top_k_paper": 6,
                "top_k_code": 10,
                "write_artifacts": True,
                "output_dir": "./code_output",
                "save_output_path": "./code_output/paper_to_code_result.json",
                "run_executable_validation": False,
            })
            
            print(f"\n✓ Successfully generated code from paper!")
            print(f"\nPaper Information:")
            print(f"  Title: {result['paper_title']}")
            print(f"  Source: {result['source']}")
            
            print(f"\nCollection Information:")
            collection = result['collection']
            print(f"  Collection ID: {collection['collection_id']}")
            print(f"  TOC Chunk ID: {collection['toc_chunk_id']}")
            print(f"  Overview: {collection['overview'][:200] if collection.get('overview') else 'N/A'}...")
            print(f"  Number of chunks: {len(collection['chunks'])}")
            
            print(f"\nCodebase Collection:")
            codebase = result['codebase_collection']
            print(f"  Collection ID: {codebase['collection_id']}")
            print(f"  Repo Root: {codebase['repo_root']}")
            print(f"  Number of modules: {len(codebase['modules'])}")
            print(f"  Number of build targets: {len(codebase['build_targets'])}")
            
            print(f"\nPlan Bundle:")
            plan_bundle = result['plan_bundle']
            print(f"  Number of goals: {len(plan_bundle['goals'])}")
            print(f"  Number of plan items: {len(plan_bundle['plan'])}")
            if plan_bundle['goals']:
                print(f"  First goal: {plan_bundle['goals'][0]}")
            
            print(f"\nDesign Answers:")
            print(f"  Total design answers: {len(result['design_answers'])}")
            for i, answer in enumerate(result['design_answers'][:3], 1):
                print(f"  {i}. Question: {answer.get('question', 'N/A')[:100]}...")
                print(f"     Status: {answer.get('status', 'N/A')}")
                print(f"     Confidence: {answer.get('confidence', 'N/A')}")
            
            print(f"\nCode Artifacts:")
            print(f"  Total artifacts: {len(result['code_artifacts'])}")
            for i, artifact in enumerate(result['code_artifacts'][:5], 1):
                print(f"  {i}. {artifact.get('filepath', 'N/A')}")
                print(f"     Language: {artifact.get('language', 'N/A')}")
                print(f"     Status: {artifact.get('status', 'N/A')}")
                print(f"     Code length: {len(artifact.get('code', ''))} chars")
            
            print(f"\nEvaluations:")
            print(f"  Total evaluations: {len(result['evaluations'])}")
            for i, evaluation in enumerate(result['evaluations'][:3], 1):
                print(f"  {i}. Artifact: {evaluation.get('artifact_id', 'N/A')}")
                print(f"     Executable: {evaluation.get('is_executable', 'N/A')}")
                print(f"     Has tests: {evaluation.get('has_tests', 'N/A')}")
            
            print(f"\nRefinement History:")
            print(f"  Total refinement iterations: {len(result['refinement_history'])}")
            
            print(f"\nTraceability Graph:")
            traceability = result.get('traceability_graph', {})
            print(f"  Nodes: {len(traceability.get('nodes', []))}")
            print(f"  Edges: {len(traceability.get('edges', []))}")
            
            print(f"\nDashboard:")
            dashboard = result.get('dashboard', {})
            print(f"  Metrics: {list(dashboard.keys())}")
            
            print(f"\nStatus Summary:")
            status_summary = result.get('status_summary', {})
            print(f"  {json.dumps(status_summary, indent=2)}")
            
            if result.get('saved_output_path'):
                print(f"\n✓ Results saved to: {result['saved_output_path']}")
            
            print(f"\n{'=' * 80}")
            print("Architecture Blueprint:")
            print("=" * 80)
            blueprint = result.get('architecture_blueprint', {})
            print(json.dumps(blueprint, indent=2)[:1000])
            print("...\n")
            
        except Exception as e:
            print(f"✗ Error generating code: {e}")
            import traceback
            traceback.print_exc()
    
    except Exception as e:
        print(f"Error: {e}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
