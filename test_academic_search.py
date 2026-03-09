import asyncio
import sys
from apps.backend.app.tools.academic_search import academic_search


async def main():
    print("Testing academic_search function...\n")
    
    # Test case 1: Basic search
    print("=" * 60)
    print("Test 1: Searching for 'Progressive Comprehensive Retrieval in agentic search' with limit 30")
    print("=" * 60)
    try:
        result = await academic_search({
            "query": "Progressive Comprehensive Retrieval in agentic search",
            "limit": 30,
            "from_year": 2024,
            "to_year": 2026,
        })
        print(f"Found {len(result['papers'])} papers:\n")
        for i, paper in enumerate(result['papers'], 1):
            print(f"{i}. {paper['title']}")
            print(f"   Authors: {', '.join(paper['authors'][:3])}{'...' if len(paper['authors']) > 3 else ''}")
            print(f"   Year: {paper['year']}")
            print(f"   Citations: {paper['citationCount']}")
            print(f"   URL: {paper['url']}")
            print(f"   Abstract: {paper['abstract'][:150]}..." if paper['abstract'] else "   Abstract: N/A")
            print()
    except Exception as e:
        print(f"Error: {e}\n")
    


if __name__ == "__main__":
    asyncio.run(main())