#!/usr/bin/env python3
"""
Local Document Processor - LlamaBarn + Qwen3 VL
Processes historical PDFs using a local vision-language model via LlamaBarn.

Key differences from batch_pdf_processor_claude.py:
  - No Batch API: documents are processed sequentially
  - PDFs are rendered to images (local models don't accept raw PDF bytes)
  - Uses OpenAI-compatible API via the `openai` SDK

Requirements: pip install PyMuPDF openai
LlamaBarn must be running with a vision model loaded (e.g. Qwen3-VL-2B).
"""

import argparse
import sys
import yaml
import base64
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ Missing PyMuPDF. Install with: pip install PyMuPDF")
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("❌ Missing openai package. Install with: pip install openai")
    sys.exit(1)


DEFAULT_BASE_URL = "http://localhost:2276/v1"
DEFAULT_DPI = 72  # Higher DPI = more visual tokens; 72 fits within Qwen3 VL's 16384 context


class LocalDocumentProcessor:
    """Process historical PDFs using a local vision-language model via LlamaBarn."""

    def __init__(self, base_url: str, model: str, dpi: int = DEFAULT_DPI):
        # max_retries=0: local model is slow; default SDK retries cause repeated proxy spam
        # timeout=600: 10 minutes per request; override with --timeout if needed
        self.client = OpenAI(base_url=base_url, api_key="not-needed", max_retries=0, timeout=600.0)
        self.model = model
        self.dpi = dpi

        self.system_prompt = """You are a precise historical document analyst. Your task is to:

1. Extract metadata and create a brief overview of the document
2. Transcribe the document EXACTLY as written, preserving spelling, punctuation, and formatting
3. Extract entities (people, organizations, locations, themes) that are EXPLICITLY mentioned IN THE LETTER CONTENT
4. Never invent, infer, or hallucinate information not present in the source
5. For multi-page documents, insert HTML comments to mark page breaks

CRITICAL RULES:
- Only include entities you can directly cite from the document BODY/CONTENT
- Do NOT extract people from letterhead, headers, footers, or organizational listings (board members, officers, etc.)
- Only extract people who are mentioned in the actual letter text or who are the author/recipient
- If uncertain about an entity, DO NOT include it
- Preserve original spellings and phrasings
- Mark unclear text as [illegible] rather than guessing
- Do not modernize or correct historical spelling/grammar
- For page breaks, insert: <!-- page 1 -->, <!-- page 2 -->, etc.
- The overview should be 2-3 sentences summarizing the document's content

LETTERHEAD HANDLING:
- Skip boilerplate letterhead content (addresses, phone numbers, officer lists, staff lists)
- Preserve dates, document titles, and sender/recipient information
- Do NOT transcribe organizational rosters, board member lists, or staff directories

Output format must be valid YAML that can be parsed programmatically."""

    def parse_source_from_path(self, pdf_path: Path) -> str:
        """Derive archival source citation from directory hierarchy.

        Expects: Archive/Collection/Box/Folder/file.pdf
        Returns: "Folder, Box, Collection, Archive"
        """
        parts = pdf_path.parts
        if len(parts) < 5:
            return str(pdf_path.parent)
        return f"{parts[-2]}, {parts[-3]}, {parts[-4]}, {parts[-5]}"

    def pdf_to_images(
        self, pdf_path: Path, max_pages: Optional[int] = None
    ) -> Tuple[List[str], int]:
        """Render PDF pages as base64-encoded PNG images.

        Args:
            pdf_path: Path to the PDF file
            max_pages: Cap on pages to render; None renders all

        Returns:
            (list of base64 PNG strings, total page count in document)
        """
        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)
        pages_to_render = total_pages if max_pages is None else min(total_pages, max_pages)

        images = []
        matrix = fitz.Matrix(self.dpi / 72, self.dpi / 72)

        for page_num in range(pages_to_render):
            pixmap = doc[page_num].get_pixmap(matrix=matrix)
            img_b64 = base64.standard_b64encode(pixmap.tobytes("png")).decode("utf-8")
            images.append(img_b64)

        doc.close()
        return images, total_pages

    def create_analysis_prompt(self, source: str, page_count: int) -> str:
        """Build the user prompt for document analysis."""
        page_note = (
            f"This document has {page_count} page(s) shown above as images. "
            "Insert <!-- page N --> markers where page breaks occur.\n\n"
            if page_count > 1
            else ""
        )

        return f"""{page_note}Analyze this historical document and provide:

1. METADATA: Structured information in YAML format
2. OVERVIEW: A brief 2-3 sentence summary of the document
3. TRANSCRIPTION: Exact text from the document

Output ONLY valid YAML in this exact structure:

```yaml
title: "Document title or first line if untitled"
creator: "[[Author Name]]"
publication: "Publication name if present, otherwise empty string"
source: "{source}"
date: "Date in YYYY-MM-DD format if present, otherwise empty string"
people:
  - "[[Person Name]]"
organization:
  - "[[Organization Name]]"
locations:
  - "[[Location Name]]"
themes:
  - "[[Theme]]"
overview: "Brief 2-3 sentence summary"
```

Then provide the transcription in markdown format.

CRITICAL:
- Only include entities EXPLICITLY present in the document BODY
- Use [[wiki-link]] format for all entities
- Preserve original text exactly — do not correct spelling or grammar
- Mark unclear text as [illegible]
"""

    def build_message_content(self, images: List[str], source: str) -> List[Dict]:
        """Build multimodal message content: page images followed by the text prompt."""
        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"},
            }
            for img_b64 in images
        ]
        content.append({
            "type": "text",
            "text": self.create_analysis_prompt(source, len(images)),
        })
        return content

    def parse_response(self, response_text: str) -> Tuple[Dict, str]:
        """Split model response into (metadata dict, transcription string)."""
        yaml_start = response_text.find("```yaml")
        yaml_end = response_text.find("```", yaml_start + 7)

        if yaml_start == -1 or yaml_end == -1:
            print("    ⚠ Warning: Could not find YAML block in response")
            return {}, response_text

        yaml_content = response_text[yaml_start + 7:yaml_end].strip()

        try:
            metadata = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            print(f"    ⚠ Warning: YAML parsing error: {e}")
            metadata = {}

        transcription = response_text[yaml_end + 3:].strip()
        return metadata or {}, transcription

    def create_obsidian_document(
        self,
        metadata: Dict,
        transcription: str,
        output_path: Path,
        pdf_filename: str,
    ) -> None:
        """Write an Obsidian-compatible markdown file."""
        doc_metadata = {
            'title': metadata.get('title', ''),
            'creator': metadata.get('creator', ''),
            'publication': metadata.get('publication', ''),
            'source': metadata.get('source', ''),
            'date': metadata.get('date', ''),
            'people': metadata.get('people', []) or [],
            'organization': metadata.get('organization', []) or [],
            'locations': metadata.get('locations', []) or [],
            'themes': metadata.get('themes', []) or [],
            'added': datetime.now().strftime('%B %d, %Y'),
        }

        overview = metadata.get('overview', '')

        frontmatter_lines = [
            '---',
            f'title: {doc_metadata["title"]}',
            f'creator: {doc_metadata["creator"]}' if doc_metadata["creator"] else 'creator:',
            f'publication: {doc_metadata["publication"]}' if doc_metadata["publication"] else 'publication:',
            f'source: {doc_metadata["source"]}',
            f'date: {doc_metadata["date"]}' if doc_metadata["date"] else 'date:',
            'people:',
        ]
        for person in doc_metadata['people']:
            frontmatter_lines.append(f'  - {person}')
        frontmatter_lines.append('organization:')
        for org in doc_metadata['organization']:
            frontmatter_lines.append(f'  - {org}')
        frontmatter_lines.append('locations:')
        for loc in doc_metadata['locations']:
            frontmatter_lines.append(f'  - {loc}')
        frontmatter_lines.append('themes:')
        for theme in doc_metadata['themes']:
            frontmatter_lines.append(f'  - {theme}')
        frontmatter_lines.extend([
            'tags:',
            '  - to-do',
            '  - source/primary',
            f'added: {doc_metadata["added"]}',
            '---\n',
        ])

        content_parts = [
            '\n'.join(frontmatter_lines),
            '## Overview\n',
            f'{overview}\n' if overview else '\n',
            '## Images\n',
            f'![[{pdf_filename}]]\n',
            '## Notes\n\n',
            '## Connections\n\n',
            '## Transcription\n',
            transcription,
        ]

        output_path.write_text('\n'.join(content_parts), encoding='utf-8')

    def check_connection(self) -> None:
        """Fail fast if LlamaBarn is not reachable."""
        try:
            self.client.models.list()
        except Exception as e:
            print(f"❌ Cannot connect to LlamaBarn at {self.client.base_url}")
            print(f"   Make sure LlamaBarn is running with a vision model loaded.")
            print(f"   Error: {e}")
            sys.exit(1)

    def process_document(
        self, pdf_path: Path, max_pages: Optional[int] = None
    ) -> Tuple[Dict, str]:
        """Render a PDF to images and process with the local model."""
        images, total_pages = self.pdf_to_images(pdf_path, max_pages)

        if max_pages and total_pages > max_pages:
            print(f"    ⚠ Rendering {max_pages} of {total_pages} pages (use --max-pages to adjust)")

        source = self.parse_source_from_path(pdf_path)
        content = self.build_message_content(images, source)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": content},
            ],
            max_tokens=4096,
            temperature=0.1,
        )

        return self.parse_response(response.choices[0].message.content)

    def process_directory(
        self,
        input_dir: Path,
        output_dir: Path,
        max_pages: Optional[int] = None,
    ) -> None:
        """Process all PDFs in a directory tree, one at a time."""
        pdf_files = list(input_dir.rglob("*.pdf"))
        if not pdf_files:
            print(f"No PDF files found in {input_dir}")
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        self.check_connection()

        print(f"Found {len(pdf_files)} PDF files")
        print(f"Model:  {self.model}")
        print(f"Output: {output_dir}")
        print(f"DPI:    {self.dpi}")
        if max_pages:
            print(f"Max pages per document: {max_pages}")
        print()

        succeeded = 0
        failed = 0

        for i, pdf_path in enumerate(pdf_files, 1):
            print(f"[{i}/{len(pdf_files)}] {pdf_path.name}")
            try:
                metadata, transcription = self.process_document(pdf_path, max_pages)
                output_path = output_dir / f"{pdf_path.stem}.md"
                self.create_obsidian_document(
                    metadata, transcription, output_path, pdf_path.name
                )
                print(f"  ✓ {output_path.name}")
                succeeded += 1
            except Exception as e:
                print(f"  ✗ {e}")
                failed += 1

        print(f"\n{'=' * 50}")
        print(f"Results: {succeeded} succeeded, {failed} failed")
        print(f"{'=' * 50}")


def list_models(base_url: str) -> None:
    """Print models available in LlamaBarn and exit."""
    client = OpenAI(base_url=base_url, api_key="not-needed")
    try:
        models = client.models.list()
        if not models.data:
            print("No models found. Load a model in LlamaBarn first.")
            return
        print("Available models:")
        for m in models.data:
            print(f"  {m.id}")
    except Exception as e:
        print(f"❌ Could not connect to {base_url}: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Process historical PDFs with a local vision model via LlamaBarn",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  %(prog)s --list-models
  %(prog)s -i ./pdfs -o ./transcriptions --model Qwen3-VL-2B
  %(prog)s -i ./sources -o ./notes --model Qwen3-VL-2B --max-pages 5 --dpi 200

Notes:
  - Use --list-models to find the exact model name as LlamaBarn reports it
  - Increase --dpi (try 200) for handwritten or degraded documents
  - Use --max-pages to limit memory use on large documents
  - Processing is sequential; no batch discount applies
  - Default LlamaBarn URL: {DEFAULT_BASE_URL}
        """,
    )

    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List models available in LlamaBarn and exit",
    )
    parser.add_argument(
        "-i", "--input",
        type=Path,
        help="Input directory containing PDF files",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output directory for markdown files",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Model name as shown in LlamaBarn (use --list-models to see options)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=DEFAULT_BASE_URL,
        help=f"LlamaBarn API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"DPI for rendering PDF pages to images (default: {DEFAULT_DPI}). Higher DPI = more visual tokens; stay at 72 unless quality is poor.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max pages per document to process (default: all). Reduce if hitting VRAM limits.",
    )

    args = parser.parse_args()

    if args.list_models:
        list_models(args.base_url)
        return

    if not args.input or not args.output or not args.model:
        parser.error("--input, --output, and --model are required")

    if not args.input.exists():
        parser.error(f"Input directory does not exist: {args.input}")

    print("=" * 60)
    print("Local Document Processor - LlamaBarn")
    print("=" * 60)
    print()

    processor = LocalDocumentProcessor(
        base_url=args.base_url,
        model=args.model,
        dpi=args.dpi,
    )

    processor.process_directory(
        input_dir=args.input,
        output_dir=args.output,
        max_pages=args.max_pages,
    )


if __name__ == "__main__":
    main()
