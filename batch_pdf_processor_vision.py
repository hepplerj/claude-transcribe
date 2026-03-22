#!/usr/bin/env python3
"""
Batch PDF Processor for Historical Documents - Apple Vision OCR + Claude API

Extracts text locally using Apple's Vision framework, then sends only the text
to Claude for OCR correction and entity extraction. Much cheaper than the
image-based pipeline because input tokens are text, not images.

macOS only — requires Apple Vision framework via pyobjc.
Run: uv pip install -e '.[vision]'
"""

import argparse
import json
import os
import platform
import re
import sys
import tempfile
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

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


def ocr_page_image(image_path: Path) -> Tuple[str, float]:
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


class VisionOCRProcessor:
    """Process historical PDFs using Apple Vision OCR + Claude's batch API"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        confidence_threshold: float = 0.5,
        dpi: int = 200,
    ):
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.confidence_threshold = confidence_threshold
        self.dpi = dpi
        self.low_confidence_docs: List[Tuple[str, float]] = []

        # Keep in sync with test_single_vision.py
        self.system_prompt = """You are a precise historical document analyst specializing in correcting OCR-extracted text from archival documents. The text you receive was extracted by Apple's Vision framework from photographs of historical document pages. Your task is to correct OCR errors, extract structured metadata, and produce a clean transcription.

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

    def create_correction_prompt(self, ocr_text: str, source: str, doc_type: str = "document") -> str:
        """Create the prompt for OCR correction and entity extraction"""
        # Keep in sync with test_single_vision.py
        return f"""The following text was extracted by OCR from a historical {doc_type}. Correct OCR errors, extract metadata, and produce a clean transcription.

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
{ocr_text}
</ocr_text>

Return the completed frontmatter block and corrected transcription, following the structure above exactly."""

    def parse_source_from_path(self, pdf_path: Path) -> str:
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

    def ocr_pdf(self, pdf_path: Path) -> Tuple[str, float]:
        """
        Rasterize PDF pages and OCR each using Vision framework.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Tuple of (full text with <!-- page N --> markers, avg confidence 0.0–1.0)
        """
        scale = self.dpi / 72.0
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
                page_texts.append((page_num + 1, text))
                all_confidences.append(confidence)

            doc.close()

        parts = []
        for page_num, text in page_texts:
            parts.append(f"<!-- page {page_num} -->\n{text}")
        full_text = "\n\n".join(parts)

        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
        return full_text, avg_confidence

    def prepare_batch_requests(
        self, pdf_files: List[Path], input_root: Path
    ) -> Tuple[List[Dict], Dict[str, str]]:
        """
        OCR each PDF locally, then prepare text-based batch API requests.

        Args:
            pdf_files: List of PDF file paths
            input_root: Root input directory for building collision-free custom_ids

        Returns:
            Tuple of (request list for batch API, custom_id -> doc_type mapping)
        """
        requests = []
        doc_type_map: Dict[str, str] = {}

        for pdf_path in pdf_files:
            print(f"  OCR: {pdf_path.name}", end="", flush=True)

            custom_id = (
                str(pdf_path.relative_to(input_root))
                .replace("/", "_")
                .replace("\\", "_")
                .replace(".pdf", "")
            )

            source = self.parse_source_from_path(pdf_path)
            doc_type = "document"
            doc_type_map[custom_id] = doc_type

            ocr_text, avg_confidence = self.ocr_pdf(pdf_path)

            confidence_str = f"{avg_confidence:.2f}"
            if avg_confidence < self.confidence_threshold:
                print(f" ⚠ confidence={confidence_str} (below threshold {self.confidence_threshold})")
                self.low_confidence_docs.append((pdf_path.name, avg_confidence))
            else:
                print(f" ✓ confidence={confidence_str}")

            if not ocr_text.strip():
                print(f"    ⚠ Warning: No text extracted from {pdf_path.name}")

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
                                    "type": "text",
                                    "text": self.create_correction_prompt(
                                        ocr_text, source, doc_type
                                    ),
                                }
                            ],
                        }
                    ],
                },
            }

            requests.append(request)

        return requests, doc_type_map

    def submit_batch_job(self, requests: List[Dict]) -> str:
        """Submit batch job to Claude API"""
        print(f"\nSubmitting batch of {len(requests)} documents...")

        message_batch = self.client.messages.batches.create(requests=requests)

        print(f"✓ Batch submitted: {message_batch.id}")
        print(f"  Status: {message_batch.processing_status}")

        return message_batch.id

    def wait_for_batch_completion(self, batch_id: str, check_interval: int = 60) -> Dict:
        """Poll until batch job completes"""
        print(f"\nWaiting for batch completion...")
        print(f"Checking every {check_interval} seconds\n")

        while True:
            message_batch = self.client.messages.batches.retrieve(batch_id)
            status = message_batch.processing_status

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

            if status == "ended":
                print("✓ Batch processing complete!")
                return message_batch

            time.sleep(check_interval)

    def get_batch_results(self, batch_id: str) -> List[Dict]:
        """Retrieve batch results"""
        results = []
        for result in self.client.messages.batches.results(batch_id):
            results.append(result.model_dump())
        return results

    def parse_claude_response(self, response_text: str) -> Tuple[Dict, str]:
        """
        Parse Claude's response into metadata dict and transcription string.

        Handles two formats:
        - Standard: ---\\nYAML\\n---\\n## Transcription\\n...
        - Code-fenced: ```yaml\\nYAML\\n```\\n## Transcription\\n...
        """
        text = response_text.strip()

        # Strip ```yaml ... ``` code fence if Claude used one despite instructions
        if text.startswith("```"):
            text = re.sub(r'^```(?:yaml)?\n?', '', text)
            text = re.sub(r'\n?```\s*\n', '\n', text, count=1)

        # Try standard --- frontmatter delimiters
        parts = text.split("---")
        if len(parts) >= 3:
            yaml_content = parts[1].strip()
            remainder = "---".join(parts[2:]).strip()
        else:
            # Fallback: split on ## Transcription directly (no --- delimiters present)
            transcription_marker = "## Transcription"
            if transcription_marker in text:
                yaml_content, remainder = text.split(transcription_marker, 1)
                yaml_content = yaml_content.strip()
                remainder = remainder.strip()
            else:
                print("    ⚠ Warning: Could not find YAML frontmatter in response")
                return {}, text

        try:
            metadata = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            print(f"    ⚠ Warning: YAML parsing error: {e}")
            metadata = {}

        transcription_marker = "## Transcription"
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
        doc_type: str = "document",
    ) -> None:
        """
        Write an Obsidian-compatible markdown file with YAML frontmatter.

        Frontmatter is built manually (not yaml.dump) to preserve [[wiki-link]]
        formatting that pyyaml would incorrectly quote.
        """
        doc_metadata = {
            "title": metadata.get("title", ""),
            "creator": metadata.get("creator", ""),
            "publication": metadata.get("publication", ""),
            "source": metadata.get("source", ""),
            "date": metadata.get("date", ""),
            "people": metadata.get("people", []),
            "organization": metadata.get("organization", []),
            "locations": metadata.get("locations", []),
            "themes": metadata.get("themes", []),
            "added": datetime.now().strftime("%Y-%m-%d"),
        }

        overview = metadata.get("overview", "")

        frontmatter_lines = [
            "---",
            f'title: {doc_metadata["title"]}',
            f'creator: {doc_metadata["creator"]}' if doc_metadata["creator"] else "creator:",
            f'publication: {doc_metadata["publication"]}' if doc_metadata["publication"] else "publication:",
            f'source: {doc_metadata["source"]}',
            f'date: {doc_metadata["date"]}' if doc_metadata["date"] else "date:",
            "people:",
        ]

        if doc_metadata["people"]:
            for person in doc_metadata["people"]:
                frontmatter_lines.append(f"  - {person}")

        frontmatter_lines.append("organization:")
        if doc_metadata["organization"]:
            for org in doc_metadata["organization"]:
                frontmatter_lines.append(f"  - {org}")

        frontmatter_lines.append("locations:")
        if doc_metadata["locations"]:
            for loc in doc_metadata["locations"]:
                frontmatter_lines.append(f"  - {loc}")

        frontmatter_lines.append("themes:")
        if doc_metadata["themes"]:
            for theme in doc_metadata["themes"]:
                frontmatter_lines.append(f"  - {theme}")

        frontmatter_lines.extend([
            "tags:",
            "  - to-do",
            f"  - source/primary/{doc_type}",
            f'added: {doc_metadata["added"]}',
            "---\n",
        ])

        content_parts = [
            "\n".join(frontmatter_lines),
            "## Overview\n",
            f"{overview}\n" if overview else "\n",
            "## Images\n",
            f"![[{pdf_filename}]]\n",
            "## Notes\n\n",
            "## Connections\n\n",
            "## Transcription\n",
            transcription,
        ]

        output_path.write_text("\n".join(content_parts), encoding="utf-8")

    def process_batch_results(
        self,
        results: List[Dict],
        output_dir: Path,
        doc_type_map: Dict[str, str],
    ) -> None:
        """Process batch results and write markdown files"""
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nProcessing results...")

        succeeded = 0
        failed = 0

        for result in results:
            custom_id = result.get("custom_id", "unknown")

            if result["result"]["type"] == "succeeded":
                message = result["result"]["message"]
                content = message["content"]

                if not content:
                    print(f"  ✗ {custom_id}: No content")
                    failed += 1
                    continue

                response_text = ""
                for block in content:
                    if block["type"] == "text":
                        response_text += block["text"]

                try:
                    metadata, transcription = self.parse_claude_response(response_text)
                    doc_type = doc_type_map.get(custom_id, "document")
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

            elif result["result"]["type"] == "errored":
                error = result["result"]["error"]
                print(f"  ✗ {custom_id}: {error['type']} - {error['message']}")
                failed += 1
            else:
                print(f"  ✗ {custom_id}: {result['result']['type']}")
                failed += 1

        print(f"\n{'=' * 50}")
        print(f"Results: {succeeded} succeeded, {failed} failed")
        print(f"{'=' * 50}")

    def write_ocr_documents(
        self,
        pdf_files: List[Path],
        input_root: Path,
        output_dir: Path,
    ) -> None:
        """
        OCR all PDFs and write markdown files using raw OCR text — no Claude call.

        Produces minimal output: source citation in frontmatter, OCR text as the
        transcription, all other metadata fields left blank. Useful when Vision
        confidence is high enough that correction isn't needed, or as a fast first
        pass before selectively running Claude on problem documents.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nRunning OCR and writing documents (Claude correction skipped)...")

        succeeded = 0
        failed = 0

        for pdf_path in pdf_files:
            print(f"  OCR: {pdf_path.name}", end="", flush=True)

            custom_id = (
                str(pdf_path.relative_to(input_root))
                .replace("/", "_")
                .replace("\\", "_")
                .replace(".pdf", "")
            )

            source = self.parse_source_from_path(pdf_path)

            try:
                ocr_text, avg_confidence = self.ocr_pdf(pdf_path)

                confidence_str = f"{avg_confidence:.2f}"
                if avg_confidence < self.confidence_threshold:
                    print(f" ⚠ confidence={confidence_str}")
                    self.low_confidence_docs.append((pdf_path.name, avg_confidence))
                else:
                    print(f" ✓ confidence={confidence_str}")

                # Write minimal markdown with raw OCR text
                output_path = output_dir / f"{custom_id}.md"
                self.create_obsidian_document(
                    metadata={"source": source},
                    transcription=ocr_text,
                    output_path=output_path,
                    pdf_filename=f"{custom_id}.pdf",
                    doc_type="document",
                )
                succeeded += 1

            except Exception as e:
                print(f" ✗ {e}")
                failed += 1

        print(f"\n{'=' * 50}")
        print(f"Results: {succeeded} succeeded, {failed} failed")
        print(f"{'=' * 50}")

    def print_low_confidence_report(self) -> None:
        """Print a summary of documents flagged for low OCR confidence"""
        if not self.low_confidence_docs:
            return

        print(f"\n{'=' * 60}")
        print(f"LOW CONFIDENCE DOCUMENTS ({len(self.low_confidence_docs)} flagged)")
        print("These may benefit from reprocessing with the image-based pipeline:")
        print("  make process IN=<input_dir> OUT=<output_dir>")
        print(f"{'=' * 60}")
        for filename, confidence in sorted(self.low_confidence_docs, key=lambda x: x[1]):
            print(f"  {filename}  (avg confidence: {confidence:.2f})")


def main():
    parser = argparse.ArgumentParser(
        description="Batch process historical PDFs: Vision OCR locally, Claude corrects text (50% cost savings)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input ./pdfs --output ./transcriptions
  %(prog)s -i ./archive -o ./notes --model claude-haiku-4-5-20251001
  %(prog)s -i ./pdfs -o ./out --dpi 300 --confidence-threshold 0.6

macOS only — requires Apple Vision framework.
Install dependencies: uv pip install -e '.[vision]'
        """,
    )

    parser.add_argument(
        "-i", "--input", type=Path, required=True, help="Input directory containing PDF files"
    )
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="Output directory for markdown files"
    )
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
        "--check-interval",
        type=int,
        default=60,
        help="Seconds between batch status checks (default: 60)",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.5,
        help="Flag documents with avg OCR confidence below this value (default: 0.5)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="DPI for PDF rasterization (default: 200; use 300 for degraded or handwritten docs)",
    )
    parser.add_argument(
        "--skip-claude",
        action="store_true",
        help="Skip Claude correction; write raw OCR text directly to output files (no API key needed)",
    )

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.skip_claude:
        parser.error("API key required via --api-key or ANTHROPIC_API_KEY environment variable")

    if not args.input.exists():
        parser.error(f"Input directory does not exist: {args.input}")

    pdf_files = list(args.input.rglob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {args.input}")
        return

    print("=" * 60)
    print("Historical Document Batch Processor - Vision OCR + Claude")
    print("=" * 60)
    print(f"\nFound {len(pdf_files)} PDF files")
    print(f"Model:                {args.model}")
    print(f"Rasterization DPI:    {args.dpi}")
    print(f"Confidence threshold: {args.confidence_threshold}")
    print(f"Output:               {args.output}")

    model_costs = {
        "claude-opus-4-6":           ("$7.50", "$37.50"),
        "claude-sonnet-4-6":         ("$1.50", "$7.50"),
        "claude-haiku-4-5-20251001": ("$0.50", "$2.50"),
    }
    input_cost, output_cost = model_costs.get(args.model, ("$?", "$?"))
    print(f"\nBatch pricing (50% off, text input):")
    print(f"  Input:  {input_cost}/MTok")
    print(f"  Output: {output_cost}/MTok")
    print()

    processor = VisionOCRProcessor(api_key, args.model, args.confidence_threshold, args.dpi)

    if args.skip_claude:
        processor.write_ocr_documents(pdf_files, args.input, args.output)
        print(f"\n✓ Complete! Output saved to: {args.output}")
        processor.print_low_confidence_report()
        return

    print("Running OCR and preparing batch requests...")
    requests, doc_type_map = processor.prepare_batch_requests(pdf_files, args.input)

    print(f"\n✓ Prepared {len(requests)} requests")

    # Cost estimate based on actual OCR text size (more accurate than the image-based estimate)
    total_chars = sum(
        len(req["params"]["messages"][0]["content"][0]["text"]) for req in requests
    )
    approx_input_tokens = total_chars // 4
    approx_output_tokens = 2000 * len(requests)
    input_mtok = approx_input_tokens / 1_000_000
    output_mtok = approx_output_tokens / 1_000_000

    model_rates = {
        "claude-opus-4-6":           (7.50, 37.50),
        "claude-sonnet-4-6":         (1.50, 7.50),
        "claude-haiku-4-5-20251001": (0.50, 2.50),
    }
    if args.model in model_rates:
        in_rate, out_rate = model_rates[args.model]
        estimated_cost = (input_mtok * in_rate) + (output_mtok * out_rate)
        print(f"Estimated batch cost: ~${estimated_cost:.2f}")
        print(f"  (~{approx_input_tokens:,} input tokens from OCR text)\n")

    batch_id = processor.submit_batch_job(requests)
    batch = processor.wait_for_batch_completion(batch_id, args.check_interval)

    print("\nRetrieving results...")
    results = processor.get_batch_results(batch_id)

    processor.process_batch_results(results, args.output, doc_type_map)

    print(f"\n✓ Complete! Output saved to: {args.output}")
    print(f"\nBatch ID: {batch_id}")
    print(f"Results available until: {batch.expires_at}")

    processor.print_low_confidence_report()


if __name__ == "__main__":
    main()
