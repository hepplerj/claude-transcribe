# Historical Document Batch Processor

> ⚠️ Vibe-coded research tool — use at your own risk.

Batch-transcribe historical PDFs using Claude or Gemini, producing Obsidian-compatible markdown with structured YAML metadata and `[[wiki-link]]` entity references.

**50% cost savings via Claude Batch API** | **Privacy-first: your data never trains models**

---

## Features

- **Batch processing** — submit an entire directory at once; 50% Claude Batch API discount applied automatically
- **Vision OCR pipeline** — rasterize PDFs locally with PyMuPDF, OCR with Apple Vision, send only text to Claude; much cheaper input costs for typed documents (macOS only)
- **Accurate transcription** — preserves original spelling, punctuation, and formatting; marks illegible text as `[illegible]`; flags reconstructed passages as `[reconstructed: ...]`
- **Entity extraction** — identifies people, organizations, locations, and themes explicitly mentioned in the document body
- **Obsidian integration** — outputs markdown with YAML frontmatter and `[[wiki-link]]` entity references
- **Source tracking** — citation built from your directory hierarchy (`Folder, Box, Collection, Archive`)
- **Theme consolidation** — post-process to normalize inconsistent themes across a corpus
- **Multiple providers** — Claude (batch API, privacy-first), Gemini (free tier available), and local models via LlamaBarn

---

## Installation

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

```bash
# Install uv (if needed)
brew install uv
# or: curl -LsSf https://astral.sh/uv/install.sh | sh

# Automated setup (creates venv, installs deps, runs smoke tests)
bash setup.sh

# Or manually
uv venv
source .venv/bin/activate
uv pip install -e .
```

**Optional dependency groups:**

```bash
uv pip install -e ".[vision]"   # Vision OCR pipeline (macOS only: PyMuPDF + pyobjc)
uv pip install -e ".[gemini]"   # Gemini API processor
uv pip install -e ".[local]"    # Local LlamaBarn processor (PyMuPDF + openai)
```

### API Keys

The Makefile automatically loads a `.env` file if present — the recommended approach:

```bash
# Create .env (git-ignored)
echo 'ANTHROPIC_API_KEY=your-key-here' > .env
echo 'GEMINI_API_KEY=your-key-here' >> .env  # if using Gemini
```

Or export directly:

```bash
export ANTHROPIC_API_KEY='your-key-here'
```

---

## Quick Start

### Vision OCR pipeline (recommended for typed documents, macOS only)

The Vision pipeline extracts text locally using Apple's OCR, then sends only text to Claude — significantly cheaper than sending images for typed government correspondence, reports, and similar documents.

```bash
# Install Vision dependencies
make install-vision

# Test one document first — shows raw OCR text, confidence scores, and Claude's correction
make test-vision PDF=./sample.pdf

# Or inspect OCR quality without any API call
make test-vision PDF=./sample.pdf --skip-claude --ocr-out ocr_preview.txt

# Run a full batch
make process-vision IN=./pdfs OUT=./transcriptions
```

### Image-based pipeline (any document type, any OS)

```bash
# Test one document
make test-single PDF=./sample.pdf

# Process a batch
make process IN=./pdfs OUT=./transcriptions
```

### Consolidate themes (optional, both pipelines)

When documents are processed independently, Claude assigns themes without awareness of the rest of your corpus:

```
Document 1:   [[federal grazing policy]]
Document 50:  [[grazing regulations]]
Document 100: [[public lands grazing]]
```

Fix this after a batch completes:

```bash
# Analyze first — no file changes
make consolidate DIR=./transcriptions

# Review theme_analysis.md, then apply
make consolidate-apply DIR=./transcriptions
```

When `--apply` is used, original themes are preserved under `original_themes`, a `themes_consolidated: true` flag is added, and `.bak` backups are created before any writes.

---

## Usage Reference

### Make targets

```bash
make help                                               # list all targets

# Vision OCR pipeline (macOS only)
make install-vision                                     # install PyMuPDF + pyobjc
make test-vision PDF=./sample.pdf                       # test one document
make process-vision IN=./pdfs OUT=./transcriptions      # full batch with Claude correction

# Image-based pipeline (Claude)
make process IN=./pdfs OUT=./transcriptions             # Sonnet (default)
make process-haiku IN=./pdfs OUT=./transcriptions       # fastest/cheapest
make process-opus IN=./pdfs OUT=./transcriptions        # most accurate
make test-single PDF=./sample.pdf                       # test one document

# Theme consolidation
make consolidate DIR=./transcriptions                   # analyze themes only
make consolidate-apply DIR=./transcriptions             # analyze + rewrite

# Gemini
make process-gemini IN=./pdfs OUT=./transcriptions      # Gemini Flash (free tier)
make process-gemini-pro IN=./pdfs OUT=./transcriptions  # Gemini 1.5 Pro
make test-gemini PDF=./sample.pdf

# Local model (LlamaBarn)
make process-local MODEL=Qwen3-VL-2B IN=./pdfs OUT=./transcriptions

# Cost utilities
make estimate IN=./pdfs                                 # estimate cost before running
make cost-check BATCH=msgbatch_xxx                      # report on a completed batch
```

### Direct script usage

```bash
# Vision OCR — batch
python batch_pdf_processor_vision.py \
  --input ./pdfs \
  --output ./transcriptions \
  --model claude-sonnet-4-6 \
  --dpi 200 \
  --confidence-threshold 0.5

# Vision OCR — batch, skip Claude entirely
python batch_pdf_processor_vision.py \
  --input ./pdfs \
  --output ./transcriptions \
  --skip-claude

# Vision OCR — single doc test
python test_single_vision.py path/to/document.pdf --doc-type letter
python test_single_vision.py path/to/document.pdf --skip-claude --ocr-out ocr.txt

# Image-based — batch
python batch_pdf_processor_claude.py \
  --input ./pdfs \
  --output ./transcriptions \
  --model claude-sonnet-4-6 \
  --check-interval 60

python test_single_claude.py path/to/document.pdf --doc-type letter

python consolidate_themes.py \
  --input ./transcriptions \
  --report theme_analysis.md \
  --apply
```

### CLI arguments — Vision OCR batch processor

| Flag | Default | Description |
|------|---------|-------------|
| `-i, --input` | required | Directory containing PDF files |
| `-o, --output` | required | Output directory for markdown files |
| `--model` | `claude-sonnet-4-6` | Claude model for correction pass |
| `--dpi` | `200` | PDF rasterization DPI (use 300 for degraded docs) |
| `--confidence-threshold` | `0.5` | Flag docs with avg OCR confidence below this value |
| `--skip-claude` | off | Write raw OCR text directly; skip Claude entirely |
| `--check-interval` | `60` | Seconds between batch status checks |
| `--api-key` | `$ANTHROPIC_API_KEY` | Override env variable |

### CLI arguments — image-based batch processor

| Flag | Default | Description |
|------|---------|-------------|
| `-i, --input` | required | Directory containing PDF files |
| `-o, --output` | required | Output directory for markdown files |
| `--model` | `claude-sonnet-4-6` | Model to use (see below) |
| `--check-interval` | `60` | Seconds between batch status checks |
| `--api-key` | `$ANTHROPIC_API_KEY` | Override env variable |

---

## Model Selection

### Claude models

| Model | Input/Output (batch) | Best for |
|-------|---------------------|----------|
| `claude-haiku-4-5-20251001` | $0.50 / $2.50 per MTok | Clean typed documents, high volume |
| `claude-sonnet-4-6` ← default | $1.50 / $7.50 per MTok | General use, mixed quality |
| `claude-opus-4-6` | $7.50 / $37.50 per MTok | Handwritten, degraded, complex layouts |

**Typical cost per 100 documents — image-based pipeline (10 pages avg):**

| Model | ~Cost |
|-------|-------|
| Haiku | ~$1.50 |
| Sonnet | ~$2.25 |
| Opus | ~$16 |

**Typical cost per 100 documents — Vision OCR pipeline (typed, 2 pages avg):**

| Model | ~Cost |
|-------|-------|
| Haiku | ~$0.05 |
| Sonnet | ~$0.50 |

Vision pipeline input costs are dramatically lower because only text tokens are sent — not images. The correction pass on clean OCR text typically uses ~1,700 input tokens per document vs. ~5,000+ for image-based processing.

Batch API pricing is 50% off standard rates. New Anthropic accounts include $5 in free credits.

### Gemini models

Free tier (Gemini 2.0 Flash): 15 RPM, 1,500 RPD. Paid tier available via `--model gemini-1.5-pro`.

---

## Output Format

Each PDF produces a `.md` file:

```markdown
---
title: Letter from Harold Ickes to Bernard DeVoto
creator: [[Harold Ickes]]
publication:
source: Folder 12, Box 3, DeVoto Papers, American Heritage Center
date: 1946-04-10
doc_type: letter
people:
  - [[Harold Ickes]]
  - [[Bernard DeVoto]]
organization:
  - [[Department of the Interior]]
locations:
  - [[Washington DC]]
themes:
  - [[federal grazing policy]]
  - [[public lands]]
tags:
  - to-do
  - source/primary/letter
added: 2025-02-05
---

## Overview

Brief 2–3 sentence summary.

## Images

![[letter-ickes-devoto-1946.pdf]]

## Notes


## Connections


## Transcription

[Exact text from the document...]
```

### Source path parsing

The `source` field is derived from the PDF's directory hierarchy. Organize your PDFs as:

```
Archive / Collection / Box / Folder / file.pdf
```

The script builds the citation in reverse: `"Folder, Box, Collection, Archive"`.

### Obsidian templates

The `templates/` directory contains two note templates for Obsidian's core Templates plugin:

- **`archival_template.md`** — general archival documents (`creator`, `publication` fields)
- **`correspondence_template.md`** — letters and correspondence (`author`, `recipient` fields)

Copy `templates/` into your vault and point the Templates plugin to it.

---

## Common Workflows

### Vision OCR for a typed document collection

```bash
make install-vision

# Test quality on one document first
make test-vision PDF="Archive/Collection/Box/Folder/sample.pdf" --doc-type letter

# If OCR quality looks good (confidence ≥ 0.9), run the batch
make process-vision IN="Archive/Collection" OUT=./transcriptions

# Low-confidence docs are listed at the end — reprocess those with image-based:
make process IN="Archive/Collection" OUT=./transcriptions
# (then manually move the reprocessed files, or just let them overwrite)
```

### Processing a research corpus by category

```bash
make process-vision IN=sources/congressional-hearings OUT=transcriptions/congressional-hearings
make process-vision IN=sources/agency-reports OUT=transcriptions/agency-reports
# Use image-based for handwritten or degraded material:
make process-opus IN=sources/handwritten OUT=transcriptions/handwritten

# Consolidate themes across the whole corpus
python consolidate_themes.py --input transcriptions --report theme_taxonomy.md --apply
```

### OCR-only pass before deciding on Claude

```bash
# Dump all OCR text to Obsidian notes — no API cost
make process-vision IN=./pdfs OUT=./transcriptions --skip-claude

# Review quality in Obsidian, then run Claude on the full batch
make process-vision IN=./pdfs OUT=./transcriptions
```

### Comparing Claude vs Gemini output

```bash
make process IN=./pdfs OUT=./transcriptions_claude
make process-gemini IN=./pdfs OUT=./transcriptions_gemini

python compare_transcriptions.py ./transcriptions_claude ./transcriptions_gemini
```

---

## Privacy & Data Handling

| | Claude API | Gemini Free | Gemini Paid |
|---|---|---|---|
| Trains on your data | ❌ Never | ✅ Yes | ❌ (opt-out default) |
| Data retention | 7 days | 55 days | 55 days |
| Batch discount | 50% | None | None |
| Human review | Safety only | Yes | Limited |

Claude's commercial API never uses your documents for model training and automatically deletes them after 7 days. The Vision OCR pipeline sends only extracted text to the API — the original PDF images never leave your machine.

---

## Troubleshooting

**"No PDF files found"** — check that your input directory contains `.pdf` files (case-sensitive on Linux/macOS)

**"API key required"** — confirm `.env` has `ANTHROPIC_API_KEY=...` or run `echo $ANTHROPIC_API_KEY`; use `--api-key` flag to override

**"This script requires macOS"** — `batch_pdf_processor_vision.py` and `test_single_vision.py` require Apple Vision framework; use the image-based pipeline on other platforms

**Low OCR confidence** — try increasing `--dpi 300` for degraded or small-print documents; for handwritten material, use the image-based pipeline with `claude-opus-4-6` instead

**YAML parsing warning** — Claude occasionally formats frontmatter incorrectly; the script logs the warning and saves what it can

**Poor transcription quality** — try `claude-opus-4-6` for handwritten or degraded documents; test a single document first

**Batch taking longer than expected** — most complete in under an hour; maximum is 24 hours; check status in the [Anthropic Console](https://console.anthropic.com/) using the batch ID printed at submission

**Consolidation merged themes that should be separate** — restore from backups and adjust manually:
```bash
for f in transcriptions/*.md.bak; do mv "$f" "${f%.bak}"; done
```

**`uv: command not found`**
```bash
export PATH="$HOME/.cargo/bin:$PATH"
# or reinstall: curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## License

MIT — feel free to modify for your research needs.
