import fitz  # PyMuPDF
import ollama
import os
import sys

def pdf_to_markdown_qwen(pdf_path: str, output_md_path: str, start_page: int = 1, end_page: int = None, model_name: str = "qwen3-vl:32b"):
    """
    Convert a specific page range of a PDF to Markdown using a locally served Ollama model.
    
    Note regarding "direct PDF to Markdown": 
    Currently, the Ollama API natively requires image arrays (base64 or bytes) for vision-language models 
    and does not accept direct binary `.pdf` file uploads for vision tasks. 
    Thus, rasterizing the PDF pages into images is a mandatory step to feed the visual data to `qwen3-vl:32b` locally.
    
    :param pdf_path: Path to the input PDF file
    :param output_md_path: Path to save the extracted Markdown
    :param start_page: 1-based index of the first page to convert
    :param end_page: 1-based index of the last page to convert (inclusive)
    :param model_name: The name of the locally served Ollama model (e.g., 'qwen3-vl:32b')
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Open the document
    doc = fitz.open(pdf_path)
    
    # Calculate 0-based indices for PyMuPDF
    start_idx = max(0, start_page - 1)
    
    # If end_page is not provided or exceeds document length, read to the end
    if end_page is None:
        end_idx = len(doc)
    else:
        end_idx = min(len(doc), end_page)

    if start_idx >= len(doc):
        raise ValueError(f"start_page {start_page} is out of bounds for document with {len(doc)} pages.")

    print(f"Converting '{pdf_path}' pages {start_idx + 1} to {end_idx} using {model_name}...")

    md_parts = [
        f"# Extracted from {os.path.basename(pdf_path)}\n\n"
    ]

    for page_num in range(start_idx, end_idx):
        print(f"Processing page {page_num + 1}...")
        page = doc.load_page(page_num)
        
        # Render page to an image (Scale/DPI can be adjusted for better OCR readability)
        matrix = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=matrix)
        img_bytes = pix.tobytes("png")
        
        # Call local Ollama 'qwen3-vl:32b' model
        try:
            print(f"Sending page {page_num + 1} to Ollama model '{model_name}' for OCR and Markdown extraction...")
            response = ollama.chat(
                model=model_name,
                messages=[
                    {
                        'role': 'user',
                        'content': 'Extract all text, tables, and formatting from this document page and output it as clean Markdown. Do not wrap the response in markdown blocks like ```markdown, just return the raw markdown content.',
                        'images': [img_bytes]
                    }
                ]
            )
            
            content = response.get('message', {}).get('content', '')
            
            # Clean up if the model still outputs markdown code blocks
            if content.startswith("```markdown"):
                content = content[11:]
            elif content.startswith("```md"):
                content = content[5:]
            if content.endswith("```"):
                content = content[:-3]
                
            md_parts.append(f"<!-- Page {page_num + 1} -->\n")
            md_parts.append(content.strip() + "\n\n---\n\n")
            
        except Exception as e:
            print(f"Error processing page {page_num + 1}: {e}")
            md_parts.append(f"**Error extracting page {page_num + 1}: {e}**\n\n---\n\n")

    # Save to the specified output path
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write("".join(md_parts))
        
    print(f"Successfully saved Markdown to: {output_md_path}")

if __name__ == "__main__":
    # Example Usage:
    # (Ensure you have installed dependencies: pip install ollama pymupdf)
    
    if len(sys.argv) < 2:
        print("Usage: python test_glm_ocr.py <input_pdf_path>")
        sys.exit(1)
        
    sample_pdf = sys.argv[1]
    
    # Generate output Markdown filename as {pdf_filename}_qwen.md
    base_name = os.path.splitext(os.path.basename(sample_pdf))[0]
    output_md = f"{base_name}_qwen.md"
    
    # Create a dummy PDF just for testing if one isn't specified, or run against an existing one.
    if os.path.exists(sample_pdf):
        # Convert pages
        pdf_to_markdown_qwen(
            pdf_path=sample_pdf, 
            output_md_path=output_md, 
            start_page=1, 
            end_page=None, 
            model_name="qwen3-vl:32b"
        )
    else:
        print(f"Error: PDF file '{sample_pdf}' not found.")
