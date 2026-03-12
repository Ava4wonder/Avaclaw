# Paper to Demo Code Tool

## Overview

The `paper_to_demo_code` tool generates a simplified demo implementation from a research paper. Unlike the full `paper_to_code` tool which builds a complete production codebase, this tool focuses on creating a demonstrative framework with clear module structure and placeholders for complex components.

## Features

- **Automatic Architecture Planning**: Analyzes the paper and designs a modular architecture
- **Module Generation**: Creates 3-7 key modules demonstrating core concepts
- **Intelligent Placeholders**: Uses placeholders for complex parts that need further details
- **Multiple Complexity Levels**: Generates different code based on module complexity
- **Documentation**: Automatically generates README with setup and usage instructions

## Usage

### Basic Usage

```python
from apps.backend.app.tools.paper_to_demo_code import paper_to_demo_code

result = await paper_to_demo_code({
    "arxiv_id": "2310.12931",
    "paper_title": "My Paper Title",
    "output_dir": "./demo_output"
})
```

### Parameters

- **arxiv_id** (string, optional): ArXiv ID to fetch paper HTML
- **paper_html** (string, optional): Direct HTML content (if arxiv_id not provided)
- **paper_title** (string, required): Title of the paper
- **output_dir** (string, optional): Directory to save generated files
- **model** (string, optional): LLM model to use for code generation
- **max_modules** (integer, optional): Maximum modules to generate (default: 7)

### Output Structure

The tool generates:

```
output_dir/
├── README.md              # Project documentation
├── main.py               # Main entry point
├── core.py               # Core algorithms
├── utils.py              # Helper utilities
├── [other_modules].py    # Additional modules
└── demo_metadata.json    # Metadata about generation
```

### Return Value

```python
{
    "paper_title": "...",
    "arxiv_id": "...",
    "collection_name": "...",
    "text_toc": "...",
    "chunks_upserted": 123,
    "architecture_plan": {
        "title": "...",
        "overview": "...",
        "modules": [...],
        "dependencies": [...],
        "language": "python"
    },
    "modules": [
        {
            "module_name": "main",
            "filename": "main.py",
            "code": "...",
            "purpose": "...",
            "complexity": "low"
        },
        ...
    ],
    "readme": "...",
    "output_dir": "./demo_output",
    "saved_files": ["..."],
    "status": "success"
}
```

## Implementation Details

### Architecture Planning

The tool uses RAG (Retrieval-Augmented Generation) to:
1. Retrieve relevant paper sections from vector store
2. Analyze paper structure and methodology
3. Design a modular architecture with 3-7 modules
4. Identify dependencies between modules

### Module Complexity

Modules are classified by complexity:
- **Low**: Fully implemented, simple helper functions
- **Medium**: Main functionality with some placeholders
- **High**: Core logic structure with detailed placeholders and TODOs

### Reused Components

The tool reuses from `academic_search.py`:
- `fetch_full_content()`: Fetches arXiv paper HTML
- `html_parsing_chunking_upsert()`: Parses and chunks paper into vector store

## Example Output

For a machine learning paper, the tool might generate:

```python
# main.py - Entry point
def main():
    print("Running demo...")
    model = Model()
    data = load_data()
    train(model, data)
    evaluate(model, data)

# core.py - Core algorithms
class Model:
    def __init__(self):
        # TODO: Initialize model architecture
        # Based on paper section 3.2
        pass
    
    def forward(self, x):
        # TODO: Implement forward pass
        # Placeholder using simple linear transformation
        return x

# utils.py - Helper functions
def load_data():
    """Load demo dataset."""
    return generate_dummy_data()
```

## Testing

Run the test file:

```bash
python test_paper_to_demo_code.py
```

## Skill Registration

The tool is registered as a skill in:
- `apps/backend/app/skills/paper_to_demo_code/skill.yaml`
- `apps/backend/app/tools/__init__.py`

This allows it to be used by agents and through the API.

## Comparison with paper_to_code

| Feature | paper_to_demo_code | paper_to_code |
|---------|-------------------|---------------|
| Purpose | Demo/prototype | Production code |
| Completeness | Framework + placeholders | Fully implemented |
| Complexity | Simplified | Full featured |
| Time | Minutes | Hours |
| Use Case | Quick POC, learning | Real deployment |

## Notes

- Generated code includes TODO comments for complex parts
- High-complexity modules indicate areas needing expert implementation
- The tool prioritizes code structure over complete functionality
- Best for understanding paper concepts and creating starting points
