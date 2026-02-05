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


def process_single_document(pdf_path: Path, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
    """
    Process a single PDF and display results

    Args:
        pdf_path: Path to PDF file
        api_key: Anthropic API key
        model: Model to use
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

    # Create prompts
    system_prompt = """You are a precise historical document analyst. Your task is to:

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

    user_prompt = f"""Analyze this historical document and provide:

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
    
    # Show usage stats
    print("\n" + "=" * 70)
    print("💰 TOKEN USAGE:")
    print("=" * 70)
    print(f"   Input tokens:  {message.usage.input_tokens:,}")
    print(f"   Output tokens: {message.usage.output_tokens:,}")
    
    # Calculate cost (batch pricing - 50% off)
    costs = {
        'claude-opus-4-5-20251101': (2.50, 12.50),
        'claude-sonnet-4-5-20250929': (1.50, 7.50),
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
        default='claude-sonnet-4-5-20250929',
        choices=[
            'claude-opus-4-5-20251101',
            'claude-sonnet-4-5-20250929',
            'claude-haiku-4-5-20251001'
        ],
        help='Claude model to use (default: claude-sonnet-4-5-20250929)'
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
        process_single_document(args.pdf_file, api_key, args.model)
        
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
