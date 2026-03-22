#!/usr/bin/env python3
"""
Single Document Processor - Test one PDF with Vision OCR before batch processing

Rasterizes the PDF with PyMuPDF, extracts text via Apple Vision framework,
then sends to Claude for OCR correction and entity extraction. Displays the
raw OCR text, per-page confidence scores, Claude's corrected output, and cost.

macOS only — requires Apple Vision framework via pyobjc.
Run: uv pip install -e '.[vision]'
"""

import argparse
import os
import platform
import re
import sys
import tempfile
import yaml
from pathlib import Path

# macOS is required for the Vision framework
if platform.system() != "Darwin":
    print("❌ This script requires macOS (Apple Vision framework is macOS-only)")
    sys.exit(1)

try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ PyMuPDF required. Run: uv pip install -e '.[vision]'")
    sys.exit(1)

try:
    import Vision
    import Quartz
    from Foundation import NSURL
except ImportError:
    print("❌ pyobjc Vision/Quartz frameworks required. Run: uv pip install -e '.[vision]'")
    sys.exit(1)

try:
    from anthropic import Anthropic
except ImportError:
    print("❌ Missing anthropic package. Run: uv pip install -e .")
    sys.exit(1)


def parse_source_from_path(pdf_path: Path) -> str:
    """
    Parse archival source information from file path.

    Expected structure: Archive/Collection/Box/Folder/file.pdf
    Output format: "Folder, Box, Collection, Archive"
    """
    parts = pdf_path.parts
    if len(parts) < 5:
        return str(pdf_path.parent)

    folder = parts[-2]
    box = parts[-3]
    collection = parts[-4]
    archive = parts[-5]

    return f"{folder}, {box}, {collection}, {archive}"


def ocr_page_image(image_path: Path) -> tuple[str, float]:
    """
    Run Vision framework OCR on a single rasterized page image.

    Args:
        image_path: Path to a PNG image file

    Returns:
        Tuple of (extracted text, average confidence score 0.0–1.0)
    """
    url = NSURL.fileURLWithPath_(str(image_path.resolve()))
    source = Quartz.CGImageSourceCreateWithURL(url, None)
    if source is None:
        return "", 0.0

    cg_image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
    if cg_image is None:
        return "", 0.0

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, {})
    success, error = handler.performRequests_error_([request], None)

    if not success or error:
        return "", 0.0

    observations = request.results()
    if not observations:
        return "", 0.0

    lines = []
    confidences = []
    for obs in observations:
        candidates = obs.topCandidates_(1)
        if candidates:
            candidate = candidates[0]
            lines.append(candidate.string())
            confidences.append(float(candidate.confidence()))

    text = "\n".join(lines)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return text, avg_confidence


def ocr_pdf(pdf_path: Path, dpi: int = 200) -> tuple[str, float]:
    """
    Rasterize PDF pages and OCR each using Vision framework.

    Args:
        pdf_path: Path to PDF file
        dpi: Rasterization resolution (higher = better OCR, slower)

    Returns:
        Tuple of (full text with <!-- page N --> markers, avg confidence 0.0–1.0)
    """
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        doc = fitz.open(str(pdf_path))

        page_texts = []
        all_confidences = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=mat)
            img_path = tmp_path / f"page_{page_num + 1}.png"
            pix.save(str(img_path))

            text, confidence = ocr_page_image(img_path)
            page_texts.append((page_num + 1, text, confidence))
            all_confidences.append(confidence)

        doc.close()

    parts = []
    for page_num, text, _ in page_texts:
        parts.append(f"<!-- page {page_num} -->\n{text}")
    full_text = "\n\n".join(parts)

    avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
    return full_text, avg_confidence, page_texts


def process_single_document(
    pdf_path: Path,
    api_key: str | None,
    model: str = "claude-sonnet-4-6",
    doc_type: str = "document",
    dpi: int = 200,
    confidence_threshold: float = 0.5,
    skip_claude: bool = False,
    ocr_out: Path | None = None,
):
    """
    OCR a single PDF with Vision, optionally send to Claude for correction.

    With --skip-claude, stops after the OCR phase and optionally saves the
    raw text to --ocr-out. Useful when Vision confidence is high enough that
    correction isn't needed.
    """
    print(f"Processing: {pdf_path.name}\n")

    source = parse_source_from_path(pdf_path)
    print(f"Source: {source}\n")

    # --- OCR phase ---
    print(f"Running Vision OCR at {dpi} DPI...")
    full_text, avg_confidence, page_texts = ocr_pdf(pdf_path, dpi)

    print(f"\nOCR Results:")
    for page_num, text, confidence in page_texts:
        flag = " ⚠ LOW" if confidence < confidence_threshold else ""
        print(f"  Page {page_num}: confidence={confidence:.2f}{flag}, chars={len(text):,}")

    overall_flag = " ⚠ LOW" if avg_confidence < confidence_threshold else ""
    print(f"  Overall avg: {avg_confidence:.2f}{overall_flag}")

    print("\n" + "=" * 70)
    print("RAW OCR TEXT:")
    print("=" * 70)
    print(full_text)

    if not full_text.strip():
        print("\n⚠ Warning: No text extracted from PDF.")

    if ocr_out:
        ocr_out.write_text(full_text, encoding="utf-8")
        print(f"\nOCR text saved to: {ocr_out}")

    if skip_claude:
        if avg_confidence < confidence_threshold:
            print(
                f"\n⚠ LOW CONFIDENCE: avg OCR confidence {avg_confidence:.2f} is below "
                f"threshold {confidence_threshold}"
            )
            print("  Consider reprocessing with the image-based pipeline:")
            print(f"  python test_single_claude.py {pdf_path}")
        print("\n✓ Done (Claude correction skipped)\n")
        return

    # --- Claude correction phase ---

    # Keep in sync with batch_pdf_processor_vision.py
    system_prompt = """You are a precise historical document analyst specializing in correcting OCR-extracted text from archival documents. The text you receive was extracted by Apple's Vision framework from photographs of historical document pages. Your task is to correct OCR errors, extract structured metadata, and produce a clean transcription.

## OCR Correction Rules

Fix only demonstrable OCR character substitutions — do not silently alter actual historical content:
- Common substitutions to watch for: 'rn' misread as 'm', '1'/'l'/'I' confusion, '0'/'O' confusion, 'cl' → 'd', 'ri' → 'n', 'vv' → 'w'
- Letter-spaced text: collapse runs where OCR inserted spaces between letters, e.g. "P r e s i d e n t" → "President"
- Broken words: rejoin words split across lines by erroneous mid-word spaces or hyphens
- When correction is certain (obvious substitution, context confirms it): correct silently
- When reconstruction relies on inference or contextual guessing: mark as [reconstructed: your reconstruction here]
- When text is truly unrecoverable: mark as [illegible]

## Preservation Rules

- Preserve original spelling, punctuation, capitalization, and grammar — do not modernize
- Preserve historical abbreviations, contractions, and period conventions
- Do not add interpretive commentary beyond the requested overview
- Never invent content not present in the source

## Paratext Handling

Separate paratext from document body and note omissions:
- Letters: skip letterhead boilerplate (addresses, phone numbers, officer/staff lists); preserve date, sender org, recipient; begin transcription after letterhead
- Newspaper articles: skip mastheads, column headers, page numbers, advertisement copy; preserve dateline, headline, byline, and article body
- Reports/memoranda: skip cover page boilerplate and organizational headers; preserve document title, date, authoring office, and body
- Stamps, fax headers, marginal notes: note their presence but exclude from transcription body
- When omitting a section, note it inline: [letterhead omitted], [masthead omitted], etc.

## Entity Extraction Rules

Extract only entities EXPLICITLY named in the document body/content:
- People: only from the actual text body, or identified author/recipient — NOT from letterhead rosters, officer lists, staff directories, or organizational headers
- Organizations, locations, themes: only if explicitly named in the body
- When uncertain whether an entity appears in body vs. header, omit it
- Format all entities as Obsidian wiki-links: [[Entity Name]]

## Multi-Page Documents

The OCR text includes page markers (<!-- page N -->). Preserve these in your transcription output.

## Output Structure

Your response must follow this exact structure:

1. A YAML frontmatter block (between --- delimiters) containing all metadata fields
2. A blank line
3. A ## Transcription header
4. The corrected transcription in plain markdown beneath it

Do not wrap the response or the YAML in a code fence (no ```yaml). Output the --- delimiters as plain text. The YAML frontmatter block must be valid, parseable YAML."""

    user_prompt = f"""The following text was extracted by OCR from a historical {doc_type}. Correct OCR errors, extract metadata, and produce a clean transcription.

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

[corrected transcription here]

Field notes:
- title: document title, or opening line if untitled
- creator: author/sender as [[wiki-link]] if identifiable, otherwise empty string
- publication: publication name for newspaper articles, otherwise empty string
- date: YYYY-MM-DD if present, partial date (YYYY-MM or YYYY) if only partially legible, otherwise empty string
- people/organization/locations/themes: each as a list of [[wiki-links]], only from document body
- overview: 2–3 factual sentences on content and significance; no interpretation

<ocr_text>
{full_text}
</ocr_text>

Return the completed frontmatter block and corrected transcription, following the structure above exactly."""

    print("\n" + "=" * 70)
    print("Sending to Claude for OCR correction...")

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=8192,
        temperature=0.1,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    response_text = message.content[0].text

    print("\n" + "=" * 70)
    print("RAW RESPONSE:")
    print("=" * 70)
    print(response_text)

    # Parse and display metadata — handles both --- and ```yaml code-fenced formats
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:yaml)?\n?', '', text)
        text = re.sub(r'\n?```\s*\n', '\n', text, count=1)

    parts = text.split("---")
    if len(parts) >= 3:
        yaml_content = parts[1].strip()
        remainder = "---".join(parts[2:]).strip()
    else:
        transcription_marker = "## Transcription"
        if transcription_marker in text:
            yaml_content, remainder = text.split(transcription_marker, 1)
            yaml_content = yaml_content.strip()
            remainder = transcription_marker + remainder
        else:
            yaml_content = ""
            remainder = text

    if yaml_content:
        print("\n" + "=" * 70)
        print("EXTRACTED METADATA:")
        print("=" * 70)

        try:
            metadata = yaml.safe_load(yaml_content)
            print(yaml.dump(metadata, allow_unicode=True, sort_keys=False))

            if "overview" in metadata:
                print("\nOVERVIEW:")
                print(f"  {metadata['overview']}")

            print("\nENTITY STATISTICS:")
            print(f"  People:       {len(metadata.get('people', []))}")
            print(f"  Organization: {len(metadata.get('organization', []))}")
            print(f"  Locations:    {len(metadata.get('locations', []))}")
            print(f"  Themes:       {len(metadata.get('themes', []))}")

        except yaml.YAMLError as e:
            print(f"❌ YAML parsing error: {e}")
            print("\nRaw YAML:")
            print(yaml_content)
    else:
        print("\n⚠ Could not find YAML frontmatter in response")

    transcription_marker = "## Transcription"
    if transcription_marker in remainder:
        transcription = remainder.split(transcription_marker, 1)[1].strip()
    else:
        transcription = remainder

    print("\n" + "=" * 70)
    print("TRANSCRIPTION PREVIEW (first 500 chars):")
    print("=" * 70)
    print(transcription[:500])
    if len(transcription) > 500:
        print(f"\n... ({len(transcription) - 500} more characters)")

    # Token usage and cost
    print("\n" + "=" * 70)
    print("TOKEN USAGE:")
    print("=" * 70)
    print(f"  Input tokens:  {message.usage.input_tokens:,}")
    print(f"  Output tokens: {message.usage.output_tokens:,}")

    costs = {
        "claude-opus-4-6":           (7.50, 37.50),
        "claude-sonnet-4-6":         (1.50, 7.50),
        "claude-haiku-4-5-20251001": (0.50, 2.50),
    }
    if model in costs:
        in_rate, out_rate = costs[model]
        in_cost = (message.usage.input_tokens / 1_000_000) * in_rate
        out_cost = (message.usage.output_tokens / 1_000_000) * out_rate
        total = in_cost + out_cost
        print(f"\n  Standard cost estimate:")
        print(f"  Input:  ${in_cost:.4f}")
        print(f"  Output: ${out_cost:.4f}")
        print(f"  Total:  ${total:.4f}")
        print(f"  (Batch would be: ~${total * 0.5:.4f})")

    if avg_confidence < confidence_threshold:
        print(
            f"\n⚠ LOW CONFIDENCE: avg OCR confidence {avg_confidence:.2f} is below "
            f"threshold {confidence_threshold}"
        )
        print("  Consider reprocessing with the image-based pipeline:")
        print(f"  python test_single_claude.py {pdf_path}")

    print("\n✓ Done\n")


def main():
    parser = argparse.ArgumentParser(
        description="Test single PDF: Vision OCR + Claude correction (before batch processing)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s document.pdf
  %(prog)s path/to/letter.pdf --doc-type letter
  %(prog)s scan.pdf --dpi 300 --confidence-threshold 0.6

macOS only — requires Apple Vision framework.
Install dependencies: uv pip install -e '.[vision]'
        """,
    )

    parser.add_argument("pdf_file", type=Path, help="PDF file to process")
    parser.add_argument(
        "--api-key",
        type=str,
        help="Anthropic API key (or set ANTHROPIC_API_KEY environment variable)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-6",
        choices=["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        help="Claude model to use (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--doc-type",
        type=str,
        default="document",
        help="Document type hint (letter, report, newspaper, memorandum, etc.)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="DPI for PDF rasterization (default: 200; use 300 for degraded or handwritten docs)",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.5,
        help="Warn if avg OCR confidence falls below this value (default: 0.5)",
    )
    parser.add_argument(
        "--skip-claude",
        action="store_true",
        help="Skip the Claude correction step; display and optionally save raw OCR text only",
    )
    parser.add_argument(
        "--ocr-out",
        type=Path,
        metavar="FILE",
        help="Save raw OCR text to this file (before any Claude correction)",
    )

    args = parser.parse_args()

    if not args.pdf_file.exists():
        print(f"❌ File not found: {args.pdf_file}")
        sys.exit(1)

    if args.pdf_file.suffix.lower() != ".pdf":
        print(f"❌ Not a PDF file: {args.pdf_file}")
        sys.exit(1)

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.skip_claude:
        print("❌ API key required. Set ANTHROPIC_API_KEY or use --api-key")
        print("   (or use --skip-claude to run OCR only, no API key needed)")
        sys.exit(1)

    try:
        process_single_document(
            args.pdf_file,
            api_key,
            args.model,
            args.doc_type,
            args.dpi,
            args.confidence_threshold,
            skip_claude=args.skip_claude,
            ocr_out=args.ocr_out,
        )
        if not args.skip_claude:
            print("💡 TIP: If the output looks good, run the batch processor:")
            print(
                f"   python batch_pdf_processor_vision.py "
                f"--input {args.pdf_file.parent} --output ./transcriptions"
            )
            print("\n   Batch processing gives 50% cost savings!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
