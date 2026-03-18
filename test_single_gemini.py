#!/usr/bin/env python3
"""
Single Document Processor - Test one PDF before batch processing
Google Gemini API Version

Useful for testing prompts, checking output format, and verifying results
before running the full batch processor.
"""

import argparse
import os
import sys
import time
from pathlib import Path
import yaml

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


def process_single_document(pdf_path: Path, api_key: str, model: str = "gemini-2.5-flash"):
    """
    Process a single PDF and display results.

    Args:
        pdf_path: Path to PDF file
        api_key: Gemini API key
        model: Gemini model to use
    """
    print(f"📄 Processing: {pdf_path.name}\n")

    source = parse_source_from_path(pdf_path)
    print(f"📍 Source: {source}\n")

    client = genai.Client(api_key=api_key)

    prompt = f"""Analyze this historical document and provide:

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

    # Upload PDF via Files API
    print("📎 Uploading PDF to Gemini Files API...")
    with open(pdf_path, 'rb') as f:
        uploaded = client.files.upload(
            file=f,
            config=types.UploadFileConfig(
                mime_type="application/pdf",
                display_name=pdf_path.stem,
            ),
        )
    print(f"   File name: {uploaded.name}")

    # Wait for file to be active
    max_wait = 30
    waited = 0
    while uploaded.state.name == "PROCESSING" and waited < max_wait:
        print("   Waiting for file processing...")
        time.sleep(2)
        waited += 2
        uploaded = client.files.get(name=uploaded.name)

    if uploaded.state.name != "ACTIVE":
        client.files.delete(name=uploaded.name)
        print(f"❌ File upload failed: {uploaded.state.name}")
        sys.exit(1)

    print("   File ready\n")

    try:
        print("🤖 Analyzing document with Gemini...")
        response = client.models.generate_content(
            model=model,
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
            client.files.delete(name=uploaded.name)
            print("   Cleaned up uploaded file")
        except Exception:
            pass

    response_text = response.text
    usage = response.usage_metadata

    # Display raw response
    print("\n" + "=" * 70)
    print("📋 RAW RESPONSE:")
    print("=" * 70)
    print(response_text)
    print("\n" + "=" * 70)

    # Parse YAML
    yaml_start = response_text.find("```yaml")
    yaml_end = response_text.find("```", yaml_start + 7)

    if yaml_start != -1 and yaml_end != -1:
        yaml_content = response_text[yaml_start + 7:yaml_end].strip()

        print("\n" + "=" * 70)
        print("🏷️  EXTRACTED METADATA:")
        print("=" * 70)

        try:
            metadata = yaml.safe_load(yaml_content)
            print(yaml.dump(metadata, allow_unicode=True, sort_keys=False))

            if 'overview' in metadata:
                print("\n📄 OVERVIEW:")
                print(f"   {metadata['overview']}")

            print("\n📊 ENTITY STATISTICS:")
            print(f"   People:       {len(metadata.get('people', []))}")
            print(f"   Organization: {len(metadata.get('organization', []))}")
            print(f"   Locations:    {len(metadata.get('locations', []))}")
            print(f"   Themes:       {len(metadata.get('themes', []))}")

        except yaml.YAMLError as e:
            print(f"❌ YAML parsing error: {e}")
            print("\nRaw YAML:")
            print(yaml_content)

        # Transcription preview
        transcription = response_text[yaml_end + 3:].strip()
        print("\n" + "=" * 70)
        print("📝 TRANSCRIPTION PREVIEW (first 500 chars):")
        print("=" * 70)
        print(transcription[:500])
        if len(transcription) > 500:
            print(f"\n... ({len(transcription) - 500} more characters)")

    else:
        print("\n⚠️  Could not find YAML in response")
        print("This might indicate a formatting issue with the model's output")

    # Token usage and cost
    input_tokens = getattr(usage, 'prompt_token_count', 0) or 0
    output_tokens = getattr(usage, 'candidates_token_count', 0) or 0

    print("\n" + "=" * 70)
    print("💰 TOKEN USAGE:")
    print("=" * 70)
    print(f"   Input tokens:  {input_tokens:,}")
    print(f"   Output tokens: {output_tokens:,}")
    print(f"   Total tokens:  {input_tokens + output_tokens:,}")

    costs = {
        "gemini-2.5-flash": (0.075, 0.30),
        "gemini-2.5-flash-lite": (0.0375, 0.15),
        "gemini-2.0-flash": (0.075, 0.30),
        "gemini-2.0-flash-lite": (0.0375, 0.15),
        "gemini-2.5-pro": (1.25, 5.00),
    }

    if model in costs:
        in_rate, out_rate = costs[model]
        est_cost = (input_tokens / 1_000_000 * in_rate) + (output_tokens / 1_000_000 * out_rate)
        print(f"\n   Paid tier cost: ~${est_cost:.5f}")
        print("   (Free tier: $0 within daily limits)")

    print("\n✓ Done\n")


def main():
    parser = argparse.ArgumentParser(
        description="Test single PDF processing with Google Gemini API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s document.pdf
  %(prog)s path/to/document.pdf --model gemini-1.5-flash
  %(prog)s test.pdf --api-key YOUR_KEY

API key: https://aistudio.google.com/apikey  (use AI Studio key, not Cloud Console)
Free tier: 15 RPM, 1,500 RPD with gemini-2.0-flash
        """,
    )

    parser.add_argument('pdf_file', type=Path, help='PDF file to process')
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

    args = parser.parse_args()

    if not args.pdf_file.exists():
        print(f"❌ File not found: {args.pdf_file}")
        sys.exit(1)

    if args.pdf_file.suffix.lower() != '.pdf':
        print(f"❌ Not a PDF file: {args.pdf_file}")
        sys.exit(1)

    api_key = args.api_key or os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        print("❌ API key required")
        print("Set GEMINI_API_KEY or use --api-key parameter")
        print("Get a free key at: https://aistudio.google.com/apikey")
        sys.exit(1)

    try:
        process_single_document(args.pdf_file, api_key, args.model)

        print("💡 TIP: If the output looks good, run the batch processor:")
        print(
            f"   python batch_pdf_processor_gemini.py "
            f"--input {args.pdf_file.parent} --output ./transcriptions"
        )

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
