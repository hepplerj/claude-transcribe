#!/usr/bin/env python3
"""
Pre-run cost estimator for a directory of PDFs.
No API key required — estimates based on document count and page count.

If PyMuPDF is installed (uv pip install -e ".[local]"), page counts are read
directly from each PDF. Otherwise, a configurable per-document page assumption
is used.

Usage:
  python estimate_batch_cost.py --input ./pdfs
  python estimate_batch_cost.py --input ./pdfs --tokens-per-page 2000
  python estimate_batch_cost.py --input ./pdfs --assume-pages 3
"""

import argparse
from pathlib import Path

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# Batch API pricing (50% off standard), per million tokens
MODEL_COSTS = {
    "claude-haiku-4-5-20251001": {"label": "Haiku 4.5",          "input": 0.50,  "output": 2.50},
    "claude-sonnet-4-6":         {"label": "Sonnet 4.6 (default)","input": 1.50,  "output": 7.50},
    "claude-opus-4-6":           {"label": "Opus 4.6",            "input": 7.50,  "output": 37.50},
}

# Defaults — conservative estimates for archival scans processed as PDF documents
DEFAULT_TOKENS_PER_PAGE = 1500   # input tokens per page
DEFAULT_OUTPUT_TOKENS_PER_DOC = 1500  # output tokens per document (transcription + metadata)
DEFAULT_ASSUME_PAGES = 4         # fallback pages/doc when PyMuPDF is unavailable


def count_pages(pdf_path: Path) -> int | None:
    """Return page count for a PDF, or None on any error."""
    try:
        with fitz.open(pdf_path) as doc:
            return len(doc)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Estimate Claude Batch API cost for a directory of PDFs (no API key required)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input ./pdfs
  %(prog)s --input ./archive --tokens-per-page 2000
  %(prog)s --input ./archive --assume-pages 6

Token estimation:
  With PyMuPDF installed, page counts are read from each PDF.
  Without PyMuPDF, --assume-pages is used (default: %(default_pages)s pages/doc).
  Actual costs depend on document complexity and scan quality.
        """ % {"default_pages": DEFAULT_ASSUME_PAGES},
    )
    parser.add_argument("-i", "--input", type=Path, required=True,
                        help="Directory containing PDF files (searched recursively)")
    parser.add_argument("--tokens-per-page", type=int, default=DEFAULT_TOKENS_PER_PAGE,
                        help=f"Estimated input tokens per page (default: {DEFAULT_TOKENS_PER_PAGE})")
    parser.add_argument("--output-tokens", type=int, default=DEFAULT_OUTPUT_TOKENS_PER_DOC,
                        help=f"Estimated output tokens per document (default: {DEFAULT_OUTPUT_TOKENS_PER_DOC})")
    parser.add_argument("--assume-pages", type=int, default=DEFAULT_ASSUME_PAGES,
                        help=f"Pages per document to assume when PyMuPDF is unavailable (default: {DEFAULT_ASSUME_PAGES})")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: directory not found: {args.input}")
        return

    pdf_files = sorted(args.input.rglob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {args.input}")
        return

    n_docs = len(pdf_files)
    print(f"\nScanning {n_docs} PDF{'s' if n_docs != 1 else ''} in {args.input} ...")

    # --- Page counting ---
    if PYMUPDF_AVAILABLE:
        page_counts = []
        failed = []
        for pdf_path in pdf_files:
            pages = count_pages(pdf_path)
            if pages is not None:
                page_counts.append(pages)
            else:
                failed.append(pdf_path.name)
                page_counts.append(None)

        counted = [p for p in page_counts if p is not None]
        if counted:
            avg_pages = sum(counted) / len(counted)
            # Fill in failed docs with average
            total_pages = sum(p if p is not None else avg_pages for p in page_counts)
            if failed:
                basis = (
                    f"{sum(counted)} pages counted across {len(counted)} docs; "
                    f"{len(failed)} unreadable — filled with avg ({avg_pages:.1f} pages/doc)"
                )
            else:
                basis = f"{int(total_pages)} total pages, {avg_pages:.1f} avg/doc"
        else:
            total_pages = n_docs * args.assume_pages
            basis = f"PyMuPDF present but all PDFs unreadable — using {args.assume_pages} pages/doc assumption"
    else:
        total_pages = n_docs * args.assume_pages
        basis = (
            f"{args.assume_pages} pages/doc assumed "
            f"(install PyMuPDF for actual counts: uv pip install -e \".[local]\")"
        )

    # --- Token estimates ---
    total_input_tokens = int(total_pages * args.tokens_per_page)
    total_output_tokens = n_docs * args.output_tokens

    # --- Output ---
    print(f"\n{'='*60}")
    print("BATCH COST ESTIMATE  (Batch API — 50% off standard rates)")
    print(f"{'='*60}")
    print(f"Documents:      {n_docs:,}")
    print(f"Page basis:     {basis}")
    print(f"Input tokens:   ~{total_input_tokens:,}  ({args.tokens_per_page} tokens/page)")
    print(f"Output tokens:  ~{total_output_tokens:,}  ({args.output_tokens} tokens/doc)")

    print(f"\n{'Model':<28} {'Input':>8} {'Output':>8} {'Total':>9} {'Per doc':>9}")
    print(f"{'-'*66}")
    for costs in MODEL_COSTS.values():
        input_cost  = (total_input_tokens  / 1_000_000) * costs["input"]
        output_cost = (total_output_tokens / 1_000_000) * costs["output"]
        total_cost  = input_cost + output_cost
        per_doc     = total_cost / n_docs
        print(
            f"{costs['label']:<28} "
            f"${input_cost:>6.2f}  "
            f"${output_cost:>6.2f}  "
            f"${total_cost:>7.2f}  "
            f"${per_doc:>7.4f}"
        )

    print(f"{'='*60}")
    print(
        f"\nThese are rough estimates. Actual costs vary with document"
        f"\ncomplexity, scan quality, and transcription length."
    )


if __name__ == "__main__":
    main()
