#!/usr/bin/env python3
"""
Batch PDF Processor for Historical Documents - Claude API Version
Uses Claude Batch API to transcribe and analyze historical PDFs
Outputs Obsidian-compatible markdown with structured metadata
50% cost savings with batch processing
"""

import argparse
import json
import yaml
import base64
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import time
from anthropic import Anthropic


DOC_TYPES = {
    "letter",
    "newspaper",
    "report",
    "memorandum",
    "telegram",
    "pamphlet",
    "circular",
    "resolution",
}


class HistoricalDocumentProcessor:
    """Process historical PDFs using Claude's batch API"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        """
        Initialize the processor

        Args:
            api_key: Anthropic API key
            model: Claude model to use
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model

        self.system_prompt = """You are a precise historical document analyst specializing in primary source transcription. Your work supports archival research and must meet rigorous standards for accuracy and consistency.

## Core Principles

- Transcribe text EXACTLY as written: preserve original spelling, punctuation, capitalization, and line breaks
- Mark illegible text as [illegible] — never guess or reconstruct
- Do not modernize, correct, or silently alter historical spelling or grammar
- Do not add interpretive commentary beyond the requested overview
- Never invent, infer, or hallucinate information not present in the source

## Entity Extraction Rules

Extract only entities EXPLICITLY named in the document body/content:
- People: only those mentioned in the actual text, or the identified author/recipient — NOT from letterhead rosters, officer lists, staff directories, or organizational headers
- Organizations, locations, themes: only if explicitly named in the body
- When uncertain whether an entity appears in body vs. header, omit it
- Format all entities as Obsidian wiki-links: [[Entity Name]]

## Document-Type Handling

Apply the following rules based on document type:
- Letters: skip boilerplate letterhead (addresses, phone numbers, officer/staff lists); preserve date, sender organization, recipient information; begin transcription after letterhead
- Newspaper articles: skip mastheads, column headers, page numbers, and advertisement copy; preserve dateline, headline, byline, and article body
- Reports/memoranda: skip cover page boilerplate and organizational headers; preserve document title, date, authoring office, and body text
- For any type: if a section is clearly non-content boilerplate, omit it and note the omission as [letterhead omitted], [masthead omitted], etc.

## Multi-Page Documents

Insert page break markers on their own line before each page:
<!-- page 1 -->
<!-- page 2 -->
etc.

## Output Structure

Your response must follow this exact structure:

1. A YAML frontmatter block (between --- delimiters) containing all metadata fields
2. A blank line
3. A ## Transcription header
4. The full transcription in plain markdown beneath it

Do not wrap the entire response in a code block. The YAML frontmatter block itself should be valid, parseable YAML."""

    def create_analysis_prompt(self, file_path: str, source: str, doc_type: str = "document") -> str:
        """Create the prompt for document analysis"""
        return f"""Analyze this historical {doc_type} and produce the following output.

---
title: ""
creator: ""
publication: ""
source: "{source}"
date: ""
doc_type: "{doc_type}"
people: []
organization: []
locations: []
themes: []
tags:
  - to-do
  - source/primary/{doc_type}
overview: ""
---

## Transcription

[transcription here]

Field notes:
- title: document title, or opening line if untitled
- creator: author/sender as [[wiki-link]] if identifiable, otherwise empty string
- publication: publication name for newspaper articles, otherwise empty string
- date: YYYY-MM-DD if present, partial date (YYYY-MM or YYYY) if only partially legible, otherwise empty string
- people/organization/locations/themes: each as a list of [[wiki-links]], only from document body
- overview: 2–3 factual sentences on content and significance; no interpretation

Return the completed frontmatter block and transcription, following the structure above exactly."""

    def parse_source_from_path(self, pdf_path: Path) -> str:
        """
        Parse archival source information from file path

        Expected structure: Archive/Collection/Box/Folder/file.pdf
        Output format: "Folder X, Box Y, Collection, Archive"

        Args:
            pdf_path: Path to PDF file

        Returns:
            Formatted source string
        """
        parts = pdf_path.parts

        # Need at least 5 parts: root, archive, collection, box, folder, file
        if len(parts) < 5:
            # Fallback if structure doesn't match expected format
            return str(pdf_path.parent)

        # Extract components (working backwards from file)
        folder = parts[-2]      # Parent directory (Folder X)
        box = parts[-3]         # Grandparent (Box Y)
        collection = parts[-4]  # Great-grandparent (Collection)
        archive = parts[-5]     # Great-great-grandparent (Archive)

        # Format: "Folder, Box, Collection, Archive"
        return f"{folder}, {box}, {collection}, {archive}"

    def encode_pdf(self, pdf_path: Path) -> str:
        """
        Encode PDF to base64 for API submission

        Args:
            pdf_path: Path to PDF file

        Returns:
            Base64 encoded PDF string
        """
        with open(pdf_path, 'rb') as f:
            return base64.standard_b64encode(f.read()).decode('utf-8')

    def prepare_batch_requests(
        self, pdf_files: List[Path], input_root: Path
    ) -> tuple[List[Dict], Dict[str, str]]:
        """
        Prepare batch API requests for multiple PDFs

        Args:
            pdf_files: List of PDF file paths
            input_root: Root input directory (used to build unique relative custom_ids)

        Returns:
            Tuple of (request list for batch API, custom_id -> doc_type mapping)
        """
        requests = []
        doc_type_map: Dict[str, str] = {}

        for pdf_path in pdf_files:
            print(f"  Encoding: {pdf_path.name}")

            # Build collision-free custom_id from relative path
            custom_id = (
                str(pdf_path.relative_to(input_root))
                .replace('/', '_')
                .replace('\\', '_')
                .replace('.pdf', '')
            )

            # Encode PDF to base64
            pdf_base64 = self.encode_pdf(pdf_path)

            # Parse source information from path
            source = self.parse_source_from_path(pdf_path)

            doc_type = "document"
            doc_type_map[custom_id] = doc_type

            # Create batch request
            request = {
                "custom_id": custom_id,
                "params": {
                    "model": self.model,
                    "max_tokens": 8192,
                    "temperature": 0.1,  # Low temperature for factual accuracy
                    "system": self.system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "application/pdf",
                                        "data": pdf_base64
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": self.create_analysis_prompt(
                                        str(pdf_path), source, doc_type
                                    )
                                }
                            ]
                        }
                    ]
                }
            }

            requests.append(request)

        return requests, doc_type_map

    def submit_batch_job(self, requests: List[Dict]) -> str:
        """
        Submit batch job to Claude API

        Args:
            requests: List of prepared requests

        Returns:
            Batch job ID
        """
        print(f"\nSubmitting batch of {len(requests)} documents...")

        # Create batch
        message_batch = self.client.messages.batches.create(
            requests=requests
        )

        print(f"✓ Batch submitted: {message_batch.id}")
        print(f"  Status: {message_batch.processing_status}")

        return message_batch.id

    def wait_for_batch_completion(
        self,
        batch_id: str,
        check_interval: int = 60
    ) -> Dict:
        """
        Wait for batch job to complete

        Args:
            batch_id: Batch job identifier
            check_interval: Seconds between status checks

        Returns:
            Completed batch object
        """
        print(f"\nWaiting for batch completion...")
        print(f"Checking every {check_interval} seconds\n")

        while True:
            # Get batch status
            message_batch = self.client.messages.batches.retrieve(batch_id)

            status = message_batch.processing_status

            # Calculate progress
            counts = message_batch.request_counts
            succeeded = counts.succeeded
            errored = counts.errored
            canceled = counts.canceled
            expired = counts.expired
            processing = counts.processing

            total = succeeded + errored + canceled + expired + processing

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Status: {status}")
            print(f"  ✓ Succeeded: {succeeded}/{total}")
            if errored > 0:
                print(f"  ✗ Errored: {errored}/{total}")
            if processing > 0:
                print(f"  ⋯ Processing: {processing}/{total}")
            print()

            # Check if complete
            if status == "ended":
                print("✓ Batch processing complete!")
                return message_batch

            # Wait before next check
            time.sleep(check_interval)

    def get_batch_results(self, batch_id: str) -> List[Dict]:
        """
        Retrieve batch results

        Args:
            batch_id: Batch job identifier

        Returns:
            List of result dictionaries
        """
        results = []

        # Iterate through results
        for result in self.client.messages.batches.results(batch_id):
            results.append(result.model_dump())

        return results

    def parse_claude_response(self, response_text: str) -> tuple[Dict, str]:
        """
        Parse Claude's response into metadata and transcription

        Args:
            response_text: Raw response from Claude

        Returns:
            Tuple of (metadata_dict, transcription_text)
        """
        # Split on --- frontmatter delimiters
        parts = response_text.split('---')
        if len(parts) < 3:
            print("    ⚠ Warning: Could not find YAML frontmatter in response")
            return {}, response_text

        yaml_content = parts[1].strip()
        remainder = '---'.join(parts[2:]).strip()

        try:
            metadata = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            print(f"    ⚠ Warning: YAML parsing error: {e}")
            metadata = {}

        # Split off transcription
        transcription_marker = '## Transcription'
        if transcription_marker in remainder:
            transcription = remainder.split(transcription_marker, 1)[1].strip()
        else:
            transcription = remainder

        return metadata, transcription

    def create_obsidian_document(
        self,
        metadata: Dict,
        transcription: str,
        output_path: Path,
        pdf_filename: str,
        doc_type: str = "document"
    ) -> None:
        """
        Create Obsidian-compatible markdown document

        Args:
            metadata: Structured metadata dictionary
            transcription: Document transcription
            output_path: Where to save the file
            pdf_filename: Original PDF filename for embedding
            doc_type: Document type for tag (e.g. 'letter', 'report')
        """
        # Ensure required fields exist
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
            'tags': ['to-do', f'source/primary/{doc_type}'],
            'added': datetime.now().strftime('%Y-%m-%d')
        }

        # Get overview from metadata
        overview = metadata.get('overview', '')

        # Build YAML frontmatter manually to control formatting
        frontmatter_lines = [
            '---',
            f'title: {doc_metadata["title"]}',
            f'creator: {doc_metadata["creator"]}' if doc_metadata["creator"] else 'creator:',
            f'publication: {doc_metadata["publication"]}' if doc_metadata["publication"] else 'publication:',
            f'source: {doc_metadata["source"]}',
            f'date: {doc_metadata["date"]}' if doc_metadata["date"] else 'date:',
            'people:'
        ]

        # Add people list
        if doc_metadata['people']:
            for person in doc_metadata['people']:
                frontmatter_lines.append(f'  - {person}')

        frontmatter_lines.append('organization:')
        # Add organization list
        if doc_metadata['organization']:
            for org in doc_metadata['organization']:
                frontmatter_lines.append(f'  - {org}')

        frontmatter_lines.append('locations:')
        # Add locations list
        if doc_metadata['locations']:
            for loc in doc_metadata['locations']:
                frontmatter_lines.append(f'  - {loc}')

        frontmatter_lines.append('themes:')
        # Add themes list
        if doc_metadata['themes']:
            for theme in doc_metadata['themes']:
                frontmatter_lines.append(f'  - {theme}')

        # Add tags
        frontmatter_lines.extend([
            'tags:',
            '  - to-do',
            f'  - source/primary/{doc_type}',
            f'added: {doc_metadata["added"]}',
            '---\n'
        ])

        # Build document sections
        content_parts = [
            '\n'.join(frontmatter_lines),
            '## Overview\n',
            f'{overview}\n' if overview else '\n',
            '## Images\n',
            f'![[{pdf_filename}]]\n',
            '## Notes\n\n',
            '## Connections\n\n',
            '## Transcription\n',
            transcription
        ]

        output_path.write_text('\n'.join(content_parts), encoding='utf-8')

    def process_batch_results(
        self,
        results: List[Dict],
        output_dir: Path,
        doc_type_map: Dict[str, str]
    ) -> None:
        """
        Process batch results and create markdown files

        Args:
            results: Batch API results
            output_dir: Output directory for markdown files
            doc_type_map: Mapping of custom_id to doc_type
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nProcessing results...")

        succeeded = 0
        failed = 0

        for result in results:
            custom_id = result.get('custom_id', 'unknown')

            # Check result type
            if result['result']['type'] == 'succeeded':
                # Extract response text
                message = result['result']['message']
                content = message['content']

                if not content:
                    print(f"  ✗ {custom_id}: No content")
                    failed += 1
                    continue

                # Get text from content blocks
                response_text = ''
                for block in content:
                    if block['type'] == 'text':
                        response_text += block['text']

                # Parse and create document
                try:
                    metadata, transcription = self.parse_claude_response(response_text)
                    doc_type = doc_type_map.get(custom_id, 'document')
                    output_path = output_dir / f"{custom_id}.md"
                    pdf_filename = f"{custom_id}.pdf"
                    self.create_obsidian_document(
                        metadata, transcription, output_path, pdf_filename, doc_type
                    )
                    print(f"  ✓ {custom_id}.md")
                    succeeded += 1
                except Exception as e:
                    print(f"  ✗ {custom_id}: {e}")
                    failed += 1

            elif result['result']['type'] == 'errored':
                error = result['result']['error']
                print(f"  ✗ {custom_id}: {error['type']} - {error['message']}")
                failed += 1

            else:
                print(f"  ✗ {custom_id}: {result['result']['type']}")
                failed += 1

        print(f"\n{'='*50}")
        print(f"Results: {succeeded} succeeded, {failed} failed")
        print(f"{'='*50}")


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description="Batch process historical PDFs using Claude API (50% cost savings)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input ./pdfs --output ./transcriptions
  %(prog)s -i ./sources -o ./notes --api-key $ANTHROPIC_API_KEY
  %(prog)s -i ./archive -o ./processed --model claude-haiku-4-5-20251001

Privacy & Cost:
  • Data NOT used for training (commercial API)
  • 7-day retention period
  • 50%% cost savings with batch processing
        """
    )

    parser.add_argument(
        '-i', '--input',
        type=Path,
        required=True,
        help='Input directory containing PDF files'
    )

    parser.add_argument(
        '-o', '--output',
        type=Path,
        required=True,
        help='Output directory for markdown files'
    )

    parser.add_argument(
        '--api-key',
        type=str,
        help='Anthropic API key (or set ANTHROPIC_API_KEY environment variable)'
    )

    parser.add_argument(
        '--model',
        type=str,
        default='claude-sonnet-4-6',
        choices=[
            'claude-opus-4-6',
            'claude-sonnet-4-6',
            'claude-haiku-4-5-20251001'
        ],
        help='Claude model to use (default: claude-sonnet-4-6)'
    )

    parser.add_argument(
        '--check-interval',
        type=int,
        default=60,
        help='Seconds between batch status checks (default: 60)'
    )

    args = parser.parse_args()

    # Get API key
    import os
    api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        parser.error("API key required via --api-key or ANTHROPIC_API_KEY environment variable")

    # Validate input directory
    if not args.input.exists():
        parser.error(f"Input directory does not exist: {args.input}")

    # Find PDF files recursively
    pdf_files = list(args.input.rglob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {args.input}")
        return

    # Display info
    print("=" * 60)
    print("Historical Document Batch Processor - Claude API")
    print("=" * 60)
    print(f"\nFound {len(pdf_files)} PDF files")
    print(f"Model: {args.model}")
    print(f"Output: {args.output}")

    # Estimate cost (batch pricing: 50% off standard rates)
    model_costs = {
        'claude-opus-4-6':        ('$7.50', '$37.50'),
        'claude-sonnet-4-6':      ('$1.50', '$7.50'),
        'claude-haiku-4-5-20251001': ('$0.50', '$2.50')
    }

    input_cost, output_cost = model_costs.get(args.model, ('$?', '$?'))
    print(f"\nBatch pricing (50% off):")
    print(f"  Input:  {input_cost}/MTok")
    print(f"  Output: {output_cost}/MTok")

    # Rough estimate
    avg_input_tokens = 5000
    avg_output_tokens = 2000
    total_input = avg_input_tokens * len(pdf_files)
    total_output = avg_output_tokens * len(pdf_files)

    input_mtok = total_input / 1_000_000
    output_mtok = total_output / 1_000_000

    if args.model == 'claude-sonnet-4-6':
        estimated_cost = (input_mtok * 1.50) + (output_mtok * 7.50)
        print(f"\nEstimated cost: ~${estimated_cost:.2f}")

    print()

    # Initialize processor
    processor = HistoricalDocumentProcessor(api_key, args.model)

    # Prepare and submit batch
    print("Preparing batch requests...")
    requests, doc_type_map = processor.prepare_batch_requests(pdf_files, args.input)

    print(f"\n✓ Prepared {len(requests)} requests")

    batch_id = processor.submit_batch_job(requests)

    # Wait for completion
    batch = processor.wait_for_batch_completion(batch_id, args.check_interval)

    # Get results
    print("\nRetrieving results...")
    results = processor.get_batch_results(batch_id)

    # Process results
    processor.process_batch_results(results, args.output, doc_type_map)

    print(f"\n✓ Complete! Output saved to: {args.output}")
    print(f"\nBatch ID: {batch_id}")
    print(f"Results available until: {batch.expires_at}")


if __name__ == "__main__":
    main()
