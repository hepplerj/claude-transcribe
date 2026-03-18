#!/usr/bin/env python3
"""
Batch PDF Processor for Historical Documents - Google Gemini API Version
Sequentially processes PDFs using the Gemini API with rate limiting for the free tier.
Outputs Obsidian-compatible markdown with structured metadata.

Free tier (Gemini 2.0 Flash): 15 RPM, 1,500 RPD, 1M TPM
Paid tier pricing (approximate): $0.075/MTok input, $0.30/MTok output
"""

import argparse
import yaml
import time
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("❌ Missing google-genai package")
    print("Run: uv pip install 'google-genai>=1.0.0'")
    sys.exit(1)


SYSTEM_PROMPT = """You are a precise historical document analyst. Your task is to:

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
- Do not add interpretive commentary beyond the brief overview
- For page breaks, insert: <!-- page 1 -->, <!-- page 2 -->, etc.
- The overview should be 2-3 sentences summarizing the document's content

LETTERHEAD HANDLING:
- Skip boilerplate letterhead content (addresses, phone numbers, officer lists, staff lists)
- Preserve dates, document titles, and sender/recipient information
- Do NOT transcribe organizational rosters, board member lists, or staff directories from letterhead

Output format must be valid YAML that can be parsed programmatically."""


def create_analysis_prompt(source: str) -> str:
    """Create the prompt for document analysis"""
    return f"""Analyze this historical document and provide:

1. METADATA: Structured information in YAML format
2. OVERVIEW: A brief 2-3 sentence summary of the document
3. TRANSCRIPTION: Exact text from the document

Output ONLY valid YAML in this exact structure:

```yaml
title: "Document title or first line if untitled"
creator: "[[Author Name]]"  # Use wiki-link format if author identified, otherwise empty string
publication: "Publication name if present, otherwise empty string"
source: "{source}"
date: "Date in YYYY-MM-DD format if present, otherwise empty string"
people:
  - "[[Person Name]]"  # ONLY people mentioned in the letter body or author/recipient - NOT from letterhead lists
organization:
  - "[[Organization Name]]"  # Use wiki-link format, only if explicitly mentioned
locations:
  - "[[Location Name]]"  # Use wiki-link format, only if explicitly mentioned
themes:
  - "[[Theme]]"  # Major topics/themes, use wiki-link format
overview: "Brief 2-3 sentence summary of the document's content and significance"
```

Then provide the transcription in markdown format.

CRITICAL - PEOPLE EXTRACTION:
- ONLY extract people who are mentioned in the actual letter text/content
- DO NOT extract people from letterhead, headers, staff lists, officer lists, or board member rosters
- Include the author/sender and recipient if identifiable
- Ignore organizational directories and contact lists in letterhead

LETTERHEAD TRANSCRIPTION:
- Skip boilerplate letterhead (addresses, phone numbers, staff lists, officer rosters)
- Keep: Date, sender organization, recipient information
- Start main transcription after letterhead section

IMPORTANT FOR MULTI-PAGE DOCUMENTS:
- Insert <!-- page 1 --> at the start of the first page
- Insert <!-- page 2 --> at the start of the second page, etc.
- Place the comment on its own line before the page content

Remember:
- Only include entities EXPLICITLY present in the document BODY
- Use [[wiki-link]] format for all entities
- Preserve original text exactly
- Mark unclear sections as [illegible]
- Add page break comments for multi-page documents
- The overview should be concise and factual, not interpretive
"""


def parse_source_from_path(pdf_path: Path) -> str:
    """
    Parse archival source information from file path.

    Expected structure: Archive/Collection/Box/Folder/file.pdf
    Output format: "Folder X, Box Y, Collection, Archive"
    """
    parts = pdf_path.parts

    if len(parts) < 5:
        return str(pdf_path.parent)

    folder = parts[-2]
    box = parts[-3]
    collection = parts[-4]
    archive = parts[-5]

    return f"{folder}, {box}, {collection}, {archive}"


def parse_gemini_response(response_text: str) -> Tuple[Dict, str]:
    """
    Parse Gemini's response into metadata dict and transcription text.

    Returns:
        Tuple of (metadata_dict, transcription_text)
    """
    yaml_start = response_text.find("```yaml")
    yaml_end = response_text.find("```", yaml_start + 7)

    if yaml_start == -1 or yaml_end == -1:
        print("    ⚠ Warning: Could not find YAML in response")
        return {}, response_text

    yaml_content = response_text[yaml_start + 7:yaml_end].strip()

    try:
        metadata = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        print(f"    ⚠ Warning: YAML parsing error: {e}")
        metadata = {}

    transcription = response_text[yaml_end + 3:].strip()

    return metadata, transcription


def create_obsidian_document(
    metadata: Dict,
    transcription: str,
    output_path: Path,
    pdf_filename: str,
) -> None:
    """
    Create Obsidian-compatible markdown document.

    Args:
        metadata: Structured metadata dictionary
        transcription: Document transcription
        output_path: Where to save the file
        pdf_filename: Original PDF filename for embedding
    """
    doc_metadata = {
        'title': metadata.get('title', ''),
        'creator': metadata.get('creator', ''),
        'publication': metadata.get('publication', ''),
        'source': metadata.get('source', ''),
        'date': metadata.get('date', ''),
        'people': metadata.get('people', []),
        'organization': metadata.get('organization', []),
        'locations': metadata.get('locations', []),
        'themes': metadata.get('themes', []),
        'tags': ['to-do', 'source/primary'],
        'added': datetime.now().strftime('%B %d, %Y'),
    }

    overview = metadata.get('overview', '')

    # Build YAML frontmatter manually — yaml.dump mis-quotes [[wiki-links]]
    frontmatter_lines = [
        '---',
        f'title: {doc_metadata["title"]}',
        f'creator: {doc_metadata["creator"]}' if doc_metadata["creator"] else 'creator:',
        f'publication: {doc_metadata["publication"]}' if doc_metadata["publication"] else 'publication:',
        f'source: {doc_metadata["source"]}',
        f'date: {doc_metadata["date"]}' if doc_metadata["date"] else 'date:',
        'people:',
    ]

    if doc_metadata['people']:
        for person in doc_metadata['people']:
            frontmatter_lines.append(f'  - {person}')

    frontmatter_lines.append('organization:')
    if doc_metadata['organization']:
        for org in doc_metadata['organization']:
            frontmatter_lines.append(f'  - {org}')

    frontmatter_lines.append('locations:')
    if doc_metadata['locations']:
        for loc in doc_metadata['locations']:
            frontmatter_lines.append(f'  - {loc}')

    frontmatter_lines.append('themes:')
    if doc_metadata['themes']:
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


def upload_pdf(client: genai.Client, pdf_path: Path) -> object:
    """
    Upload a PDF to the Gemini Files API and wait for it to become active.

    Args:
        client: Gemini API client
        pdf_path: Path to PDF file

    Returns:
        Uploaded file object (active)
    """
    with open(pdf_path, 'rb') as f:
        uploaded = client.files.upload(
            file=f,
            config=types.UploadFileConfig(
                mime_type="application/pdf",
                display_name=pdf_path.stem,
            ),
        )

    # Wait for file to be active (usually near-instant for PDFs)
    max_wait = 30
    waited = 0
    while uploaded.state.name == "PROCESSING" and waited < max_wait:
        time.sleep(2)
        waited += 2
        uploaded = client.files.get(name=uploaded.name)

    if uploaded.state.name != "ACTIVE":
        client.files.delete(name=uploaded.name)
        raise RuntimeError(f"File upload failed with state: {uploaded.state.name}")

    return uploaded


class GeminiDocumentProcessor:
    """Process historical PDFs using Google Gemini API"""

    # Approximate paid-tier pricing per million tokens (as of 2025)
    MODEL_COSTS = {
        "gemini-2.5-flash": (0.075, 0.30),
        "gemini-2.5-flash-lite": (0.0375, 0.15),
        "gemini-2.0-flash": (0.075, 0.30),
        "gemini-2.0-flash-lite": (0.0375, 0.15),
        "gemini-2.5-pro": (1.25, 5.00),
    }

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model

    def process_pdf(self, pdf_path: Path) -> Tuple[str, int, int]:
        """
        Analyze a single PDF with Gemini.

        Returns:
            Tuple of (response_text, input_tokens, output_tokens)
        """
        source = parse_source_from_path(pdf_path)
        prompt = create_analysis_prompt(source)

        uploaded = upload_pdf(self.client, pdf_path)

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_uri(
                        file_uri=uploaded.uri,
                        mime_type="application/pdf",
                    ),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.1,
                    max_output_tokens=8192,
                ),
            )
        finally:
            try:
                self.client.files.delete(name=uploaded.name)
            except Exception:
                pass

        response_text = response.text
        usage = response.usage_metadata
        input_tokens = getattr(usage, 'prompt_token_count', 0) or 0
        output_tokens = getattr(usage, 'candidates_token_count', 0) or 0

        return response_text, input_tokens, output_tokens

    def process_all(
        self,
        pdf_files: List[Path],
        output_dir: Path,
        delay: float = 5.0,
    ) -> None:
        """
        Process all PDFs sequentially with rate-limit delay.

        Args:
            pdf_files: List of PDF paths to process
            output_dir: Directory for output .md files
            delay: Seconds to wait between requests (free tier: 15 RPM max)
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        total = len(pdf_files)
        succeeded = 0
        failed = 0
        total_input_tokens = 0
        total_output_tokens = 0

        print(f"\nProcessing {total} documents...")
        if delay > 0:
            effective_rpm = 60 / delay
            print(f"Rate limit: {delay}s delay between requests (~{effective_rpm:.0f} RPM)\n")

        for i, pdf_path in enumerate(pdf_files, 1):
            output_path = output_dir / f"{pdf_path.stem}.md"
            if output_path.exists():
                print(f"[{i}/{total}] {pdf_path.name}  (skipped — already exists)")
                continue

            print(f"[{i}/{total}] {pdf_path.name}")

            try:
                response_text, input_tokens, output_tokens = self.process_pdf(pdf_path)
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens

                metadata, transcription = parse_gemini_response(response_text)
                create_obsidian_document(metadata, transcription, output_path, pdf_path.name)

                print(
                    f"  ✓ {pdf_path.stem}.md  "
                    f"({input_tokens:,} in / {output_tokens:,} out tokens)"
                )
                succeeded += 1

            except Exception as e:
                print(f"  ✗ Error: {e}")
                failed += 1

            # Rate limit delay (skip after last file)
            if i < total and delay > 0:
                time.sleep(delay)

        # Summary
        print(f"\n{'=' * 50}")
        print(f"Results: {succeeded} succeeded, {failed} failed")
        print(f"Tokens:  {total_input_tokens:,} input / {total_output_tokens:,} output")

        if self.model_name in self.MODEL_COSTS:
            in_rate, out_rate = self.MODEL_COSTS[self.model_name]
            est_cost = (
                (total_input_tokens / 1_000_000) * in_rate
                + (total_output_tokens / 1_000_000) * out_rate
            )
            print(f"Paid tier cost estimate: ~${est_cost:.4f}")
            print("(Free tier: $0 up to 1,500 RPD / 1M TPM for Flash models)")

        print(f"{'=' * 50}")


def main():
    parser = argparse.ArgumentParser(
        description="Process historical PDFs using Google Gemini API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input ./pdfs --output ./transcriptions
  %(prog)s -i ./sources -o ./notes --api-key $GEMINI_API_KEY
  %(prog)s -i ./archive -o ./processed --model gemini-2.5-pro
  %(prog)s -i ./archive -o ./processed --delay 0  # no rate limiting (paid tier)

Free Tier Limits (Gemini 2.0 Flash):
  • 15 requests per minute (RPM)
  • 1,500 requests per day (RPD)
  • 1,000,000 tokens per minute (TPM)
  • Default delay of 5s keeps usage ~12 RPM (safe for free tier)

API key: https://aistudio.google.com/apikey  (use AI Studio key, not Cloud Console)
        """,
    )

    parser.add_argument('-i', '--input', type=Path, required=True,
                        help='Input directory containing PDF files')
    parser.add_argument('-o', '--output', type=Path, required=True,
                        help='Output directory for markdown files')
    parser.add_argument('--api-key', type=str,
                        help='Gemini API key (or set GEMINI_API_KEY env var)')
    parser.add_argument(
        '--model',
        type=str,
        default='gemini-2.5-flash',
        choices=[
            'gemini-2.5-flash',
            'gemini-2.5-flash-lite',
            'gemini-2.0-flash',
            'gemini-2.0-flash-lite',
            'gemini-2.5-pro',
            'gemini-3-flash-preview',
            'gemini-3.1-flash-lite-preview',
            'gemini-3.1-pro-preview',
            'gemini-3-pro-preview',
        ],
        help='Gemini model to use (default: gemini-2.5-flash)',
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=5.0,
        help='Seconds between requests for rate limiting (default: 5.0; use 0 to disable)',
    )

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        parser.error("API key required via --api-key or GEMINI_API_KEY environment variable")

    if not args.input.exists():
        parser.error(f"Input directory does not exist: {args.input}")

    pdf_files = list(args.input.rglob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {args.input}")
        return

    print("=" * 60)
    print("Historical Document Processor - Google Gemini API")
    print("=" * 60)
    print(f"\nFound {len(pdf_files)} PDF files")
    print(f"Model:  {args.model}")
    print(f"Output: {args.output}")

    if args.delay > 0:
        rpm = 60 / args.delay
        eta_min = (len(pdf_files) * args.delay) / 60
        print(f"Delay:  {args.delay}s between requests (~{rpm:.0f} RPM)")
        print(f"Est. time: ~{eta_min:.1f} minutes")
    else:
        print("Delay:  none (ensure you are on a paid plan or within burst limits)")

    costs = GeminiDocumentProcessor.MODEL_COSTS
    if args.model in costs:
        in_rate, out_rate = costs[args.model]
        avg_in, avg_out = 5000, 2000
        est = (
            (avg_in * len(pdf_files) / 1_000_000) * in_rate
            + (avg_out * len(pdf_files) / 1_000_000) * out_rate
        )
        print(f"\nPaid tier estimate (rough): ~${est:.2f}")
        print("Free tier: $0 (within daily limits)")

    print()

    processor = GeminiDocumentProcessor(api_key, args.model)
    processor.process_all(pdf_files, args.output, args.delay)

    print(f"\n✓ Complete! Output saved to: {args.output}")


if __name__ == "__main__":
    main()
