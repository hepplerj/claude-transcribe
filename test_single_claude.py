#!/usr/bin/env python3
"""
Single Document Processor - Test one PDF before batch processing
Useful for testing prompts, checking output format, and verifying results
Claude API Version
"""

import argparse
import os
import sys
from pathlib import Path
import yaml
import base64

try:
    from anthropic import Anthropic
except ImportError:
    print("❌ Missing anthropic package")
    print("Run: pip install -r requirements_claude.txt")
    sys.exit(1)


def parse_source_from_path(pdf_path: Path) -> str:
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


def process_single_document(
    pdf_path: Path, api_key: str, model: str = "claude-sonnet-4-6", doc_type: str = "document"
):
    """
    Process a single PDF and display results

    Args:
        pdf_path: Path to PDF file
        api_key: Anthropic API key
        model: Model to use
        doc_type: Document type (letter, report, newspaper, etc.)
    """

    print(f"📄 Processing: {pdf_path.name}\n")

    # Parse source information
    source = parse_source_from_path(pdf_path)
    print(f"📍 Source: {source}\n")

    # Initialize client
    client = Anthropic(api_key=api_key)

    # Encode PDF
    print("📎 Encoding PDF...")
    with open(pdf_path, 'rb') as f:
        pdf_base64 = base64.standard_b64encode(f.read()).decode('utf-8')
    print(f"   Size: {len(pdf_base64)} characters (base64)\n")

    # Create prompts (keep in sync with batch_pdf_processor_claude.py)
    system_prompt = """You are a precise historical document analyst specializing in primary source transcription. Your work supports archival research and must meet rigorous standards for accuracy and consistency.

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

    user_prompt = f"""Analyze this historical {doc_type} and produce the following output.

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

    # Generate response
    print("🤖 Analyzing document with Claude...")

    message = client.messages.create(
        model=model,
        max_tokens=8192,
        temperature=0.1,
        system=system_prompt,
        messages=[
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
                        "text": user_prompt
                    }
                ]
            }
        ]
    )

    # Get response text
    response_text = message.content[0].text

    # Display results
    print("\n" + "=" * 70)
    print("📋 RAW RESPONSE:")
    print("=" * 70)
    print(response_text)
    print("\n" + "=" * 70)

    # Parse YAML from --- frontmatter delimiters
    parts = response_text.split('---')
    if len(parts) >= 3:
        yaml_content = parts[1].strip()
        remainder = '---'.join(parts[2:]).strip()

        print("\n" + "=" * 70)
        print("🏷️  EXTRACTED METADATA:")
        print("=" * 70)

        try:
            metadata = yaml.safe_load(yaml_content)
            print(yaml.dump(metadata, allow_unicode=True, sort_keys=False))

            # Show overview if present
            if 'overview' in metadata:
                print("\n📄 OVERVIEW:")
                print(f"   {metadata['overview']}")

            # Show entity counts
            print("\n📊 ENTITY STATISTICS:")
            print(f"   People: {len(metadata.get('people', []))}")
            print(f"   Organization: {len(metadata.get('organization', []))}")
            print(f"   Locations: {len(metadata.get('locations', []))}")
            print(f"   Themes: {len(metadata.get('themes', []))}")

        except yaml.YAMLError as e:
            print(f"❌ YAML parsing error: {e}")
            print("\nRaw YAML:")
            print(yaml_content)

        # Show transcription preview
        transcription_marker = '## Transcription'
        if transcription_marker in remainder:
            transcription = remainder.split(transcription_marker, 1)[1].strip()
        else:
            transcription = remainder

        print("\n" + "=" * 70)
        print("📝 TRANSCRIPTION PREVIEW (first 500 chars):")
        print("=" * 70)
        print(transcription[:500])
        if len(transcription) > 500:
            print(f"\n... ({len(transcription) - 500} more characters)")

    else:
        print("\n⚠️  Could not find YAML frontmatter in response")
        print("This might indicate a formatting issue with the model's output")

    # Show usage stats
    print("\n" + "=" * 70)
    print("💰 TOKEN USAGE:")
    print("=" * 70)
    print(f"   Input tokens:  {message.usage.input_tokens:,}")
    print(f"   Output tokens: {message.usage.output_tokens:,}")

    # Calculate cost (batch pricing - 50% off)
    costs = {
        'claude-opus-4-6':           (7.50, 37.50),
        'claude-sonnet-4-6':         (1.50, 7.50),
        'claude-haiku-4-5-20251001': (0.50, 2.50)
    }

    if model in costs:
        input_cost_per_mtok, output_cost_per_mtok = costs[model]
        input_cost = (message.usage.input_tokens / 1_000_000) * input_cost_per_mtok
        output_cost = (message.usage.output_tokens / 1_000_000) * output_cost_per_mtok
        total_cost = input_cost + output_cost

        print(f"\n   Batch cost estimate (50% off):")
        print(f"   Input:  ${input_cost:.4f}")
        print(f"   Output: ${output_cost:.4f}")
        print(f"   Total:  ${total_cost:.4f}")

    print("\n✓ Done\n")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Test single PDF processing before batch - Claude API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s document.pdf
  %(prog)s path/to/document.pdf --model claude-haiku-4-5-20251001
  %(prog)s test.pdf --api-key YOUR_KEY
  %(prog)s letter.pdf --doc-type letter

Privacy & Cost:
  • Data NOT used for training
  • 7-day retention period
  • Test uses standard pricing (batch gets 50%% off)
        """
    )

    parser.add_argument(
        'pdf_file',
        type=Path,
        help='PDF file to process'
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
        '--doc-type',
        type=str,
        default='document',
        help='Document type hint (letter, report, newspaper, memorandum, telegram, etc.)'
    )

    args = parser.parse_args()

    # Validate PDF exists
    if not args.pdf_file.exists():
        print(f"❌ File not found: {args.pdf_file}")
        sys.exit(1)

    if not args.pdf_file.suffix.lower() == '.pdf':
        print(f"❌ Not a PDF file: {args.pdf_file}")
        sys.exit(1)

    # Get API key
    api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ API key required")
        print("Set ANTHROPIC_API_KEY or use --api-key parameter")
        sys.exit(1)

    # Process
    try:
        process_single_document(args.pdf_file, api_key, args.model, args.doc_type)

        print("💡 TIP: If the output looks good, you can run the batch processor:")
        print(f"   python batch_pdf_processor_claude.py --input {args.pdf_file.parent} --output ./transcriptions")
        print("\n   Batch processing gives you 50% cost savings!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
