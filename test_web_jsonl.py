import json
import sys
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pathlib import Path

app = FastAPI()
jsonl_file_path = "apps/backend/app/tools/outputs/comprehension_comprehesion_paperreading_20260310_180224_1ac2f17a.jsonl"

def load_data():
    records = []
    path = Path(jsonl_file_path)
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
    return records

@app.get("/", response_class=HTMLResponse)
def read_root():
    records = load_data()
    if not records:
        return """
        <html>
            <body style="font-family: sans-serif; padding: 2rem;">
                <h2>No records found or file does not exist.</h2>
                <p>Checked path: {}</p>
            </body>
        </html>
        """.format(jsonl_file_path)
    
    first = records[0]
    
    # HTML and CSS using Tailwind CSS via CDN for a modern, clean UI
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>JSONL Preview: {first.get('paper_title', 'Document')}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .markdown-content p {{ margin-bottom: 1em; }}
            .markdown-content strong {{ font-weight: 600; color: #1f2937; }}
        </style>
    </head>
    <body class="bg-gray-50 text-gray-800 font-sans antialiased p-6 md:p-10">
        <div class="max-w-5xl mx-auto">
            
            <!-- Common Info Header -->
            <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-8">
                <h1 class="text-2xl font-bold text-blue-700 mb-4">Paper Information</h1>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                    <div>
                        <span class="font-semibold text-gray-500">Title:</span> 
                        <span class="ml-2 font-medium">{first.get('paper_title', 'N/A')}</span>
                    </div>
                    <div>
                        <span class="font-semibold text-gray-500">Arxiv ID:</span> 
                        <span class="ml-2 font-medium">{first.get('arxiv_id', 'N/A')}</span>
                    </div>
                    <div>
                        <span class="font-semibold text-gray-500">Collection:</span> 
                        <span class="ml-2 font-medium bg-blue-50 text-blue-700 px-2 py-1 rounded">{first.get('collection_name', 'N/A')}</span>
                    </div>
                    <div>
                        <span class="font-semibold text-gray-500">Type:</span> 
                        <span class="ml-2 font-medium bg-gray-100 text-gray-700 px-2 py-1 rounded">{first.get('type', 'N/A')}</span>
                    </div>
                </div>
            </div>

            <!-- Q&A List -->
            <div class="space-y-8">
    """

    for idx, record in enumerate(records, start=1):
        question = record.get('question', 'N/A')
        toc = record.get('toc_page_index', [])
        question_id = record.get('question_id', 'N/A')
        parent_id = record.get('parent_question_id')
        root_id = record.get('root_question_id', 'N/A')
        depth = record.get('depth', 0)
        q_type = record.get('question_type', 'N/A')
        why_matters = record.get('why_this_matters', 'N/A')
        
        toc_html = ""
        if toc:
            toc_list = "".join([f"<li class='truncate'>&bull; {t}</li>" for t in toc])
            toc_html = f"""
            <div class="mt-2 mb-4">
                <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">TOC References</p>
                <ul class="text-xs text-gray-400 space-y-1">
                    {toc_list}
                </ul>
            </div>
            """
            
        filtered_ans = record.get('filtered_answer', 'N/A').replace('\n', '<br>')
        
        # indent based on depth
        margin_left = depth * 16

        html_content += f"""
                <div class="bg-white rounded-lg shadow-md border border-gray-200 overflow-hidden" style="margin-left: {margin_left}px;">
                    <div class="bg-gray-50 p-5 border-b border-gray-200">
                        <div class="text-xs text-gray-500 mb-2 font-mono">
                            ID: {question_id} | Type: {q_type} | Depth: {depth}
                            {f' | Parent: {parent_id}' if parent_id else ''}
                        </div>
                        <h2 class="text-xl font-bold text-green-700 leading-snug">
                            <span class="text-green-900 border-r-2 border-green-300 pr-2 mr-2">Q{idx}</span>{question}
                        </h2>
                        {toc_html}
                    </div>
                    
                    <div class="p-6 space-y-4">
                        <div class="bg-blue-50 p-3 rounded text-sm text-blue-900 border border-blue-100">
                            <strong>Why this matters:</strong> {why_matters}
                        </div>
                        <div>
                            <h3 class="text-sm font-bold text-cyan-600 uppercase tracking-widest mb-2 border-b border-cyan-100 pb-1">Answer</h3>
                            <div class="text-sm text-gray-700 markdown-content leading-relaxed">
                                {filtered_ans}
                            </div>
                        </div>
                    </div>
                </div>
        """

    html_content += """
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_content

if __name__ == "__main__":
    if len(sys.argv) > 1:
        jsonl_file_path = sys.argv[1]
        
    print(f"Starting web UI...")
    print(f"Loading file: {jsonl_file_path}")
    print(f"Preview available at: http://127.0.0.1:8765")
    
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
