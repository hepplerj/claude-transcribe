# AGENTS.md

> For feature specifications, business rules, and domain models, see [SPEC.md](./SPEC.md).

---

## Table of Contents

- [Project Overview](#project-overview)
- [Tech Stack](#tech-stack)
- [Project Initialization](#project-initialization)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Development Workflow](#development-workflow)
- [Best Practices & Key Conventions](#best-practices--key-conventions)
- [Notes for AI Agents](#notes-for-ai-agents)

---

## Project Overview

A command-line tool for academic researchers to batch-transcribe historical PDFs using the Claude or Gemini APIs. PDFs are processed into Obsidian-compatible markdown files with YAML frontmatter and `[[wiki-link]]` entity references. Three processing pipelines are available:

- **Image-based (Claude):** PDF encoded as base64, sent directly to Claude's vision model
- **Vision OCR (macOS):** PDF rasterized locally via PyMuPDF, OCR'd via Apple Vision framework, text sent to Claude for correction — significantly cheaper input costs
- **Gemini / Local:** Alternative providers

Entry points:
- `batch_pdf_processor_claude.py` — main batch processor (Anthropic Batch API, 50% discount, image-based)
- `test_single_claude.py` — single-document tester (non-batch, for prompt validation)
- `batch_pdf_processor_vision.py` — batch processor using Apple Vision OCR + Claude text API (macOS only)
- `test_single_vision.py` — single-document tester for Vision OCR pipeline (macOS only)
- `batch_pdf_processor_gemini.py` — Gemini batch processor (sequential, free-tier rate limiting)
- `test_single_gemini.py` — single-document tester for Gemini
- `compare_transcriptions.py` — A/B comparison tool across two output directories
- `consolidate_themes.py` — post-processing theme normalization across a processed corpus
- `batch_pdf_processor_local.py` — local model processor via LlamaBarn (no API key, sequential)

---

## Tech Stack

- **Runtime:** Python 3.12+
- **Package manager:** `uv` (recommended) or `pip`
- **Core dependencies:** `anthropic>=0.40.0`, `pyyaml>=6.0`
- **Vision OCR dependencies** (`uv pip install -e ".[vision]"`): `PyMuPDF>=1.24.0`, `pyobjc-framework-Vision>=10.0`, `pyobjc-framework-Quartz>=10.0` — macOS only
- **Gemini dependencies** (`uv pip install -e ".[gemini]"`): `google-genai>=1.0.0`
- **Local model dependencies** (`uv pip install -e ".[local]"`): `openai>=1.0.0`, `PyMuPDF>=1.24.0`
- **Dev dependencies:** `pytest>=7.0`, `ruff>=0.1.0`
- **Build backend:** `hatchling`
- **Linter/formatter:** `ruff` (line length 100, target py312, rules E/F/I/N/W)

No database, no frontend framework — purely file-based I/O.

---

## Project Initialization

```bash
# Install uv (if not already installed)
brew install uv

# Install core dependencies into local venv
uv pip install -e .

# Or use the setup script (creates venv, installs deps, runs smoke tests)
bash setup.sh

# Set API key — either export or put in .env (loaded automatically by Makefile)
export ANTHROPIC_API_KEY='your-api-key-here'
# or: echo 'ANTHROPIC_API_KEY=your-key' > .env
```

---

## Project Structure

```
claude-transcribe/
├── batch_pdf_processor_claude.py  # Main batch processor (Anthropic Batch API, image-based)
├── test_single_claude.py          # Single document tester (Anthropic API, image-based)
├── batch_pdf_processor_vision.py  # Batch processor (Vision OCR + Claude text API, macOS only)
├── test_single_vision.py          # Single document tester (Vision OCR pipeline, macOS only)
├── batch_pdf_processor_gemini.py  # Batch processor (Gemini API, sequential)
├── test_single_gemini.py          # Single document tester (Gemini API)
├── compare_transcriptions.py      # A/B comparison across two output directories
├── consolidate_themes.py          # Theme normalization post-processor
├── batch_pdf_processor_local.py   # Local model processor (LlamaBarn/OpenAI-compatible)
├── estimate_batch_cost.py         # Pre-run cost estimator (no API key needed)
├── check_batch_cost.py            # Post-run cost/token/timing report for a completed batch ID
├── pyproject.toml                 # Dependencies, ruff config, entry points
├── Makefile                       # Convenience commands (auto-loads .env)
├── setup.sh                       # Full environment setup script
├── .env                           # API keys — git-ignored, loaded by Makefile
├── templates/                     # Obsidian note templates
│   ├── archival_template.md       # General archival docs (creator, publication fields)
│   └── correspondence_template.md # Letters (author, recipient fields)
└── American Heritage Center/      # Example input PDF directory structure (git-ignored)
```

---

## Architecture

### System Architecture Diagram

```
Input PDFs (filesystem)
        │
        ├─── Image-based pipeline ──────────────────────────────────────
        │    HistoricalDocumentProcessor
        │      ├── encode_pdf()              → base64 strings
        │      ├── prepare_batch_requests()  → Anthropic Batch API request list
        │      ├── submit_batch_job()        → batch_id
        │      ├── wait_for_batch_completion() → polls until status == "ended"
        │      ├── get_batch_results()       → list of result dicts
        │      ├── parse_claude_response()   → (metadata dict, transcription string)
        │      └── create_obsidian_document() → writes .md files to output dir
        │
        └─── Vision OCR pipeline (macOS only) ──────────────────────────
             VisionOCRProcessor
               ├── ocr_pdf()                → OCR text + avg confidence per doc
               │     ├── fitz.open()        → rasterize pages to PNG at configurable DPI
               │     └── ocr_page_image()   → Apple Vision VNRecognizeTextRequest
               ├── prepare_batch_requests() → text-based Batch API request list
               │   OR write_ocr_documents() → skip Claude, write raw OCR to .md files
               ├── submit_batch_job()       → batch_id
               ├── wait_for_batch_completion() → polls until status == "ended"
               ├── get_batch_results()      → list of result dicts
               ├── parse_claude_response()  → (metadata dict, transcription string)
               └── create_obsidian_document() → writes .md files to output dir

Output Markdown Files (filesystem)
        │
        ▼
ThemeConsolidator (optional post-processing)
  ├── collect_all_themes()   → {theme: [files]}
  ├── consolidate_with_claude() → canonical theme groups
  └── apply_consolidation()  → rewrites .md frontmatter in place
```

### Key Data Flow (Anthropic image-based batch)

1. **PDF → base64** via `encode_pdf()`
2. **Path → source citation** via `parse_source_from_path()` — expects `Archive/Collection/Box/Folder/file.pdf` hierarchy; builds `"Folder, Box, Collection, Archive"` string
3. **Batch submission** — `client.messages.batches.create(requests=[...])`
4. **Response parsing** — Claude returns a `---` YAML frontmatter block followed by a `## Transcription` header; `parse_claude_response()` strips any accidental code fences, splits on `---` delimiters, extracts transcription after the header marker
5. **Output writing** — `create_obsidian_document()` builds YAML frontmatter manually (not via `yaml.dump`) to control field ordering and wiki-link formatting

### Key Data Flow (Vision OCR batch)

1. **PDF → PNG images** via PyMuPDF (`fitz`): each page rendered at configurable DPI (default 200)
2. **PNG → text + confidence** via Apple Vision `VNRecognizeTextRequest` (accurate recognition level, language correction enabled); per-observation confidence scores averaged across all pages
3. **Low-confidence flagging** — docs below `--confidence-threshold` (default 0.5) are logged at run end for manual review/reprocessing
4. **Path → source citation** — same `parse_source_from_path()` logic
5. **Batch submission** — same batch plumbing; content type is `{"type": "text", "text": ocr_text}` instead of a base64 document block — substantially cheaper input tokens
6. **Response parsing** — same `parse_claude_response()` with code-fence stripping
7. **Output writing** — same `create_obsidian_document()`

With `--skip-claude`: steps 5–7 are skipped; raw OCR text is written directly into the Transcription section of a minimal `.md` file.

### Key Data Flow (local/LlamaBarn)

1. **PDF → PNG images** via PyMuPDF (`fitz`): each page rendered at configurable DPI, base64-encoded
2. **Path → source citation** — same `parse_source_from_path()` logic
3. **API call** — `openai.OpenAI(base_url="http://localhost:2276/v1", api_key="not-needed")`, images sent as `image_url` content parts in the user message
4. **Response parsing** — same `parse_claude_response()` logic
5. **Output writing** — same `create_obsidian_document()` logic

### API Usage

**Anthropic (image-based):**
- Batch API: `client.messages.batches.create()`, `.retrieve()`, `.results()`
- Single-doc: `client.messages.create()`
- Both use `temperature=0.1`, `max_tokens=8192`
- PDF content type: `{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": ...}}`

**Anthropic (Vision OCR):**
- Same batch/single-doc API calls
- Text content type: `{"type": "text", "text": ocr_text}` — no image/PDF data sent to API
- Input token cost is a fraction of the image-based pipeline for typed documents

**Apple Vision (macOS):**
- `Vision.VNRecognizeTextRequest` with `VNRequestTextRecognitionLevelAccurate` and `usesLanguageCorrection = True`
- Handler: `Vision.VNImageRequestHandler.initWithCGImage_options_()` — synchronous, no async needed
- Image loading: `Quartz.CGImageSourceCreateWithURL()` + `CGImageSourceCreateImageAtIndex()`
- Requires: `pyobjc-framework-Vision`, `pyobjc-framework-Quartz`

**LlamaBarn (OpenAI-compatible):**
- `openai.OpenAI(base_url="http://localhost:2276/v1", api_key="not-needed")`
- `client.chat.completions.create()` — blocks synchronously, no polling
- Image content type: `{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}`
- `temperature=0.1`, `max_tokens=4096`

---

## Development Workflow

### Running Scripts

```bash
# Vision OCR pipeline (macOS only — cheapest for typed documents)
make install-vision                                         # install PyMuPDF + pyobjc
make test-vision PDF=./sample.pdf                          # test one document
make test-vision PDF=./sample.pdf --skip-claude            # OCR only, no API call
make process-vision IN=./pdfs OUT=./transcriptions         # full batch
make process-vision IN=./pdfs OUT=./transcriptions --skip-claude  # OCR-only batch

# Image-based pipeline (Anthropic API)
make process IN=./pdfs OUT=./transcriptions
make test-single PDF=./sample.pdf

# Local model (LlamaBarn)
make install-local                                          # install PyMuPDF + openai
make list-models                                           # see what's loaded
make process-local MODEL=Qwen3-VL-2B IN=./pdfs OUT=./transcriptions

# Estimate cost before running (no API key needed)
make estimate IN=./pdfs

# Check cost/token/timing for a completed batch
make cost-check BATCH=msgbatch_xxx

# Consolidate themes after batch completes
make consolidate DIR=./transcriptions        # analyze only
make consolidate-apply DIR=./transcriptions  # analyze + rewrite files

# Specific models
make process-haiku IN=./pdfs OUT=./transcriptions   # fastest/cheapest
make process-opus  IN=./pdfs OUT=./transcriptions   # most accurate

# Clean build artifacts
make clean
```

### Direct Script Usage

```bash
python batch_pdf_processor_vision.py \
  --input ./pdfs \
  --output ./transcriptions \
  --model claude-sonnet-4-6 \
  --dpi 200 \
  --confidence-threshold 0.5

python test_single_vision.py path/to/document.pdf \
  --doc-type letter \
  --skip-claude \
  --ocr-out raw_ocr.txt

python batch_pdf_processor_claude.py \
  --input ./pdfs \
  --output ./transcriptions \
  --model claude-sonnet-4-6 \
  --check-interval 60

python test_single_claude.py path/to/document.pdf --doc-type letter

python batch_pdf_processor_gemini.py --input ./pdfs --output ./transcriptions

python compare_transcriptions.py ./transcriptions_claude ./transcriptions_gemini

python consolidate_themes.py \
  --input ./transcriptions \
  --report theme_analysis.md \
  --apply
```

### Linting

```bash
uv run ruff check .
uv run ruff format .
```

---

## Best Practices & Key Conventions

### Output Format
- YAML frontmatter is built **manually** via string concatenation (not `yaml.dump`) to preserve field ordering and avoid quoting issues with `[[wiki-link]]` values
- All entity values use Obsidian wiki-link format: `[[Name]]`
- Output tags: `to-do` and `source/primary/{doc_type}` (e.g. `source/primary/letter`)
- The `added` field uses ISO format `%Y-%m-%d` (e.g., "2025-02-05")

### Prompting
- The image-based pipeline system/user prompts live in `HistoricalDocumentProcessor.__init__` / `create_analysis_prompt()` in `batch_pdf_processor_claude.py`, duplicated in `test_single_claude.py`
- The Vision OCR pipeline system/user prompts live in `VisionOCRProcessor.__init__` / `create_correction_prompt()` in `batch_pdf_processor_vision.py`, duplicated in `test_single_vision.py`
- Editing any prompt requires editing both the batch script and its corresponding single-doc tester
- Low temperature (0.1) is critical for transcription fidelity; do not increase without strong reason

### Response Parsing
- `parse_claude_response()` handles two formats: standard `---` YAML frontmatter delimiters, and `\`\`\`yaml` code-fenced YAML (which Claude occasionally produces despite instructions)
- Code fence stripping uses `re.sub` to remove opening/closing fences before splitting on `---`
- Falls back to splitting on `## Transcription` directly if no `---` delimiters are found after stripping

### Error Handling
- Per-document failures are caught, logged, and counted; batch processing continues
- YAML parse errors fall back to `{}` metadata with the raw response as transcription
- Theme consolidation creates `.bak` backups before applying changes (default behavior)

### API Keys
- Store in `.env` at the project root — the Makefile auto-loads it via `-include .env` + `export`
- `.env` is git-ignored; never commit keys

---

## Notes for AI Agents

### When Modifying Prompts
- **Image-based pipeline:** system prompt in `HistoricalDocumentProcessor.__init__`, user prompt in `create_analysis_prompt()` — both duplicated in `test_single_claude.py`. All four locations must stay in sync.
- **Vision OCR pipeline:** system prompt in `VisionOCRProcessor.__init__`, user prompt in `create_correction_prompt()` — both duplicated in `test_single_vision.py`. All four locations must stay in sync.
- The two pipelines have **different prompts**: the image-based prompt asks Claude to transcribe from scratch; the Vision prompt asks Claude to correct OCR artifacts and extract entities from provided text.

### Output Format Changes
- `create_obsidian_document()` builds frontmatter via string list + `'\n'.join()` — it does not use `yaml.dump`. New metadata fields require explicit insertion into `frontmatter_lines`.
- The output section order is: frontmatter → Overview → Images → Notes → Connections → Transcription.
- Both pipelines share the same `create_obsidian_document()` implementation (duplicated per script).

### Model Names
Current valid model choices (hardcoded in `argparse` `choices` in all four Claude scripts):
- `claude-opus-4-6`
- `claude-sonnet-4-6` (default)
- `claude-haiku-4-5-20251001`

Update `choices` lists in `batch_pdf_processor_claude.py`, `test_single_claude.py`, `batch_pdf_processor_vision.py`, and `test_single_vision.py` when model versions change.

### What to Avoid
- Do not use `yaml.dump` for frontmatter output — wiki-link values like `[[Name]]` get quoted in ways Obsidian doesn't parse correctly
- Do not increase `temperature` above 0.2 for transcription tasks
- Do not add database or web dependencies — this tool is intentionally simple and portable
- Do not remove the code-fence stripping in `parse_claude_response()` — Claude occasionally wraps YAML in ` ```yaml ` despite prompt instructions

---

*Last Updated: 2026-03-21*
*This document is maintained for AI agent context and onboarding.*
