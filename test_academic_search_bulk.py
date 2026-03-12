import asyncio
from apps.backend.app.tools.academic_search import academic_search, read_bulk_abstract


async def main():
    print("Testing academic_search + read_bulk_abstract pipeline...\n")

    cur_query = "Convert academic research papers into HTML content"
    cur_limit = 10
    
    # Step 1: Search for papers
    print("=" * 80)
    print("Step 1: Searching for papers with query '{}' and limit {}".format(cur_query, cur_limit))
    print("=" * 80)
    try:
        search_result = await academic_search({
            "query": cur_query,
            "limit": cur_limit,
            "from_year": 2024,
            "to_year": 2026,
        })
        
        papers = search_result.get("papers", [])
        print(f"Found {len(papers)} papers.")
        for i, paper in enumerate(papers, 1):
            print(f"  {i}. {paper['title']}")
            
        if not papers:
            print("No papers found. Exiting.")
            return

        # Step 2: Read bulk abstract
        print("\n" + "=" * 80)
        print("Step 2: Processing abstracts in bulk (bulk_num=10)")
        print("=" * 80)
        
        bulk_result = await read_bulk_abstract({
            "papers": papers,
            "bulk_num": 10,
        })
        
        print(f"Processed {bulk_result.get('papers_processed', 0)} papers into {bulk_result.get('chunks', 0)} chunks.\n")
        
        # Print Intermediate summary
        print("=" * 80)
        print("INTERMEDIATE SUMMARY (temp_answer)")
        print("=" * 80)
        print(bulk_result.get("temp_answer", "N/A"))
        print("\n")
        
        # Print Final summary
        print("=" * 80)
        print("FINAL ANSWER (final_answer)")
        print("=" * 80)
        print(bulk_result.get("final_answer", "N/A"))
        print("\n")
        
    except Exception as e:
        print(f"Error: {e}\n")
    

if __name__ == "__main__":
    asyncio.run(main())
