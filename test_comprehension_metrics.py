import asyncio
from apps.backend.app.tools.academic_search import academic_search, Comprehension_of_papers_withnoticablemetrics

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
        
    except Exception as e:
        print(f"Error: {e}\n")
    

if __name__ == "__main__":
    asyncio.run(main())
