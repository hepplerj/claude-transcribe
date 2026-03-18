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

A command-line tool for academic researchers to batch-transcribe historical PDFs using the Claude or Gemini APIs. PDFs are encoded as base64, submitted in bulk, and the structured responses are parsed into Obsidian-compatible markdown files with YAML frontmatter and `[[wiki-link]]` entity references.

Entry points:
- `batch_pdf_processor_claude.py` — main batch processor (Anthropic Batch API, 50% discount)
- `test_single_claude.py` — single-document tester (non-batch, for prompt validation)
- `batch_pdf_processor_gemini.py` — Gemini batch processor (sequential, free-tier rate limiting)
- `test_single_gemini.py` — single-document tester for Gemini
- `compare_transcriptions.py` — A/B comparison tool across two output directories
- `consolidate_themes.py` — post-processing theme normalization across a processed corpus
- `batch_pdf_processor_local.py` — local model processor via LlamaBarn (no API key, sequential)

---

## Tech Stack

- **Runtime:** Python 3.8+
- **Package manager:** `uv` (recommended) or `pip`
- **Core dependencies:** `anthropic>=0.40.0`, `pyyaml>=6.0`
- **Gemini dependencies** (`uv pip install -e ".[gemini]"`): `google-genai>=1.0.0`
- **Local model dependencies** (`uv pip install -e ".[local]"`): `openai>=1.0.0`, `PyMuPDF>=1.24.0`
- **Dev dependencies:** `pytest>=7.0`, `ruff>=0.1.0`
- **Build backend:** `hatchling`
- **Linter/formatter:** `ruff` (line length 100, target py38, rules E/F/I/N/W)

No database, no frontend framework — purely file-based I/O.

---

## Project Initialization

```bash
# Install uv (if not already installed)
brew install uv

# Install dependencies into local venv
uv pip install -e .

# Or use the setup script (creates venv, installs deps, runs smoke tests)
bash setup.sh

# Set API key
export ANTHROPIC_API_KEY='your-api-key-here'
```

---

## Project Structure

```
claude-transcribe/
├── batch_pdf_processor_claude.py  # Main batch processor (Anthropic Batch API)
├── test_single_claude.py          # Single document tester (Anthropic API)
├── batch_pdf_processor_gemini.py  # Batch processor (Gemini API, sequential)
├── test_single_gemini.py          # Single document tester (Gemini API)
├── compare_transcriptions.py      # A/B comparison across two output directories
├── consolidate_themes.py          # Theme normalization post-processor
├── batch_pdf_processor_local.py     # Local model processor (LlamaBarn/OpenAI-compatible)
├── check_batch_cost.py            # Post-run cost/token/timing report for a completed batch ID
├── pyproject.toml                 # Dependencies, ruff config, entry points
├── Makefile                       # Convenience commands
├── setup.sh                       # Full environment setup script
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
        ▼
HistoricalDocumentProcessor
  ├── encode_pdf()           → base64 strings
  ├── prepare_batch_requests() → Anthropic Batch API request list
  ├── submit_batch_job()     → batch_id
  ├── wait_for_batch_completion() → polls until status == "ended"
  ├── get_batch_results()    → list of result dicts
  ├── parse_claude_response() → (metadata dict, transcription string)
  └── create_obsidian_document() → writes .md files to output dir

Output Markdown Files (filesystem)
        │
        ▼
ThemeConsolidator (optional post-processing)
  ├── collect_all_themes()   → {theme: [files]}
  ├── consolidate_with_claude() → canonical theme groups
  └── apply_consolidation()  → rewrites .md frontmatter in place
```

### Key Data Flow (Anthropic batch)

1. **PDF → base64** via `encode_pdf()`
2. **Path → source citation** via `parse_source_from_path()` — expects `Archive/Collection/Box/Folder/file.pdf` hierarchy; builds `"Folder, Box, Collection, Archive"` string
3. **Batch submission** — `client.messages.batches.create(requests=[...])`
4. **Response parsing** — Claude returns a `---` YAML frontmatter block followed by a `## Transcription` header and plain markdown; `parse_claude_response()` splits on `---` delimiters then extracts transcription after the header marker
5. **Output writing** — `create_obsidian_document()` builds YAML frontmatter manually (not via `yaml.dump`) to control field ordering and wiki-link formatting

### Key Data Flow (local/LlamaBarn)

1. **PDF → PNG images** via PyMuPDF (`fitz`): each page rendered at configurable DPI, base64-encoded
2. **Path → source citation** — same `parse_source_from_path()` logic
3. **API call** — `openai.OpenAI(base_url="http://localhost:2276/v1", api_key="not-needed")`, images sent as `image_url` content parts in the user message
4. **Response parsing** — same `---` frontmatter + `## Transcription` parsing as the Claude batch processor
5. **Output writing** — same `create_obsidian_document()` logic

### API Usage

**Anthropic:**
- Batch API: `client.messages.batches.create()`, `.retrieve()`, `.results()`
- Single-doc: `client.messages.create()`
- Both use `temperature=0.1`, `max_tokens=8192`
- PDF content type: `{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": ...}}`

**LlamaBarn (OpenAI-compatible):**
- `openai.OpenAI(base_url="http://localhost:2276/v1", api_key="not-needed")`
- `client.chat.completions.create()` — blocks synchronously, no polling
- Image content type: `{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}`
- `temperature=0.1`, `max_tokens=4096`

---

## Development Workflow

### Running Scripts

```bash
# Process a batch (Anthropic API)
make process IN=./pdfs OUT=./transcriptions

# Test a single document first
make test-single PDF=./sample.pdf

# Local model (LlamaBarn)
make install-local                                          # install PyMuPDF + openai
make list-models                                           # see what's loaded
make process-local MODEL=Qwen3-VL-2B IN=./pdfs OUT=./transcriptions

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
- System prompt and user prompt are defined as module-level strings in `HistoricalDocumentProcessor.__init__` and `create_analysis_prompt()`
- `test_single_claude.py` duplicates these prompts — keep them in sync when modifying
- Low temperature (0.1) is critical for transcription fidelity; do not increase without strong reason

### Error Handling
- Per-document failures are caught, logged, and counted; batch processing continues
- YAML parse errors fall back to `{}` metadata with the raw response as transcription
- Theme consolidation creates `.bak` backups before applying changes (default behavior)

---

## Notes for AI Agents

### When Modifying Prompts
- The system prompt exists in **two places**: `HistoricalDocumentProcessor.__init__` (batch processor) and `process_single_document()` in `test_single_claude.py`. Both must be updated together.
- The user prompt similarly exists in `create_analysis_prompt()` and `test_single_claude.py`. Keep them synchronized.

### Output Format Changes
- `create_obsidian_document()` builds frontmatter via string list + `'\n'.join()` — it does not use `yaml.dump`. New metadata fields require explicit insertion into `frontmatter_lines`.
- The output section order is: frontmatter → Overview → Images → Notes → Connections → Transcription.

### Model Names
Current valid model choices (hardcoded in `argparse` `choices`):
- `claude-opus-4-6`
- `claude-sonnet-4-6` (default)
- `claude-haiku-4-5-20251001`

Update `choices` lists in both `batch_pdf_processor_claude.py` and `test_single_claude.py` when model versions change.

### What to Avoid
- Do not use `yaml.dump` for frontmatter output — wiki-link values like `[[Name]]` get quoted in ways Obsidian doesn't parse correctly
- Do not increase `temperature` above 0.2 for transcription tasks
- Do not add database or web dependencies — this tool is intentionally simple and portable

---

*Last Updated: 2026-03-17*
*This document is maintained for AI agent context and onboarding.*
