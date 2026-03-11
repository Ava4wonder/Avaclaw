import json
import sys
from pathlib import Path

def print_colored(text, color_code):
    print(f"\033[{color_code}m{text}\033[0m")

def main():
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = r"apps/backend/app/tools/outputs/comprehension_comprehesion_paperreading_20260310_180224_1ac2f17a.jsonl"
    
    path = Path(file_path)
    if not path.exists():
        print(f"File not found: {file_path}")
        return

    records = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    if not records:
        print("No records found in the JSONL file.")
        return

    # Extract common fields from the first record
    first = records[0]
    print("=" * 80)
    print_colored("PAPER INFORMATION", "1;34")  # Bold Blue
    print("=" * 80)
    print(f"Title:           {first.get('paper_title', 'N/A')}")
    print(f"Arxiv ID:        {first.get('arxiv_id', 'N/A')}")
    print(f"Collection Name: {first.get('collection_name', 'N/A')}")
    print(f"Type:            {first.get('type', 'N/A')}")
    print("=" * 80)
    print()

    for idx, record in enumerate(records, start=1):
        question = record.get('question', 'N/A')
        toc = record.get('toc_page_index', [])
        
        print_colored(f"Q{idx}: {question}", "1;32")  # Bold Green
        
        if toc:
            # 90m is bright black (dark gray/light gray depending on terminal)
            print_colored("TOC References:", "90")
            for t in toc:
                print_colored(f"  - {t}", "90")
        
        print_colored("\nFiltered Answer:", "1;36")  # Bold Cyan
        print(record.get('filtered_answer', 'N/A'))
        
        print("-" * 80)
        print()

if __name__ == "__main__":
    main()
