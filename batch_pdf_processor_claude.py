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


class HistoricalDocumentProcessor:
    """Process historical PDFs using Claude's batch API"""
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        """
        Initialize the processor

        Args:
            api_key: Anthropic API key
            model: Claude model to use
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model

        # System prompt emphasizing accuracy and format
        self.system_prompt = """You are a precise historical document analyst. Your task is to:

1. Extract metadata and create a brief overview of the document
2. Transcribe the document EXACTLY as written, preserving spelling, punctuation, and formatting
3. Extract entities (people, organizations, locations, themes) that are EXPLICITLY mentioned
4. Never invent, infer, or hallucinate information not present in the source
5. For multi-page documents, insert HTML comments to mark page breaks

CRITICAL RULES:
- Only include entities you can directly cite from the document
- If uncertain about an entity, DO NOT include it
- Preserve original spellings and phrasings
- Mark unclear text as [illegible] rather than guessing
- Do not modernize or correct historical spelling/grammar
- Do not add interpretive commentary beyond the brief overview
- For page breaks, insert: <!-- page 1 -->, <!-- page 2 -->, etc.
- The overview should be 2-3 sentences summarizing the document's content

Output format must be valid YAML that can be parsed programmatically."""

    def create_analysis_prompt(self, file_path: str, source: str) -> str:
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
  - "[[Person Name]]"  # Use wiki-link format, only if explicitly mentioned
organization:
  - "[[Organization Name]]"  # Use wiki-link format, only if explicitly mentioned
locations:
  - "[[Location Name]]"  # Use wiki-link format, only if explicitly mentioned
themes:
  - "[[Theme]]"  # Major topics/themes, use wiki-link format
overview: "Brief 2-3 sentence summary of the document's content and significance"
```

Then provide the transcription in markdown format.

IMPORTANT FOR MULTI-PAGE DOCUMENTS:
- Insert <!-- page 1 --> at the start of the first page
- Insert <!-- page 2 --> at the start of the second page, etc.
- Place the comment on its own line before the page content

Remember:
- Only include entities EXPLICITLY present in the document
- Use [[wiki-link]] format for all entities
- Preserve original text exactly
- Mark unclear sections as [illegible]
- Add page break comments for multi-page documents
- The overview should be concise and factual, not interpretive
"""

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

    def prepare_batch_requests(self, pdf_files: List[Path]) -> List[Dict]:
        """
        Prepare batch API requests for multiple PDFs

        Args:
            pdf_files: List of PDF file paths

        Returns:
            List of request dictionaries for batch API
        """
        requests = []

        for pdf_path in pdf_files:
            print(f"  Encoding: {pdf_path.name}")

            # Encode PDF to base64
            pdf_base64 = self.encode_pdf(pdf_path)

            # Parse source information from path
            source = self.parse_source_from_path(pdf_path)

            # Create batch request
            request = {
                "custom_id": pdf_path.stem,  # Use filename as ID
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
                                    "text": self.create_analysis_prompt(str(pdf_path), source)
                                }
                            ]
                        }
                    ]
                }
            }

            requests.append(request)

        return requests

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
        # Extract YAML between code fences
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
        
        # Everything after YAML is transcription
        transcription = response_text[yaml_end + 3:].strip()
        
        return metadata, transcription

    def create_obsidian_document(
        self,
        metadata: Dict,
        transcription: str,
        output_path: Path,
        pdf_filename: str
    ) -> None:
        """
        Create Obsidian-compatible markdown document

        Args:
            metadata: Structured metadata dictionary
            transcription: Document transcription
            output_path: Where to save the file
            pdf_filename: Original PDF filename for embedding
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
            'tags': ['to-do', 'source/primary'],
            'added': datetime.now().strftime('%B %d, %Y')
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
            '  - source/primary',
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
        output_dir: Path
    ) -> None:
        """
        Process batch results and create markdown files
        
        Args:
            results: Batch API results
            output_dir: Output directory for markdown files
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
                    output_path = output_dir / f"{custom_id}.md"
                    pdf_filename = f"{custom_id}.pdf"
                    self.create_obsidian_document(metadata, transcription, output_path, pdf_filename)
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
  • ~$2.25 per 100 documents with Sonnet 4.5
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
        default='claude-sonnet-4-5-20250929',
        choices=[
            'claude-opus-4-5-20251101',
            'claude-sonnet-4-5-20250929', 
            'claude-haiku-4-5-20251001'
        ],
        help='Claude model to use (default: claude-sonnet-4-5-20250929)'
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
    
    # Estimate cost
    model_costs = {
        'claude-opus-4-5-20251101': ('$2.50', '$12.50'),
        'claude-sonnet-4-5-20250929': ('$1.50', '$7.50'),
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
    
    if args.model == 'claude-sonnet-4-5-20250929':
        estimated_cost = (input_mtok * 1.50) + (output_mtok * 7.50)
        print(f"\nEstimated cost: ~${estimated_cost:.2f}")
    
    print()
    
    # Initialize processor
    processor = HistoricalDocumentProcessor(api_key, args.model)
    
    # Prepare and submit batch
    print("Preparing batch requests...")
    requests = processor.prepare_batch_requests(pdf_files)
    
    print(f"\n✓ Prepared {len(requests)} requests")
    
    batch_id = processor.submit_batch_job(requests)
    
    # Wait for completion
    batch = processor.wait_for_batch_completion(batch_id, args.check_interval)
    
    # Get results
    print("\nRetrieving results...")
    results = processor.get_batch_results(batch_id)
    
    # Process results
    processor.process_batch_results(results, args.output)
    
    print(f"\n✓ Complete! Output saved to: {args.output}")
    print(f"\nBatch ID: {batch_id}")
    print(f"Results available until: {batch.expires_at}")


if __name__ == "__main__":
    main()
