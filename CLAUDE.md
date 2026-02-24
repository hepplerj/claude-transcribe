# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Commands

```bash
# Setup
uv pip install -e .          # Install dependencies
bash setup.sh                # Full setup (venv + deps + smoke tests)

# Process documents
make process IN=./pdfs OUT=./transcriptions                       # Sonnet (default)
make process-haiku IN=./pdfs OUT=./transcriptions                 # Fastest/cheapest
make process-opus  IN=./pdfs OUT=./transcriptions                 # Most accurate

# Test a single document before batching
make test-single PDF=./sample.pdf

# Theme consolidation (run after batch completes)
make consolidate DIR=./transcriptions        # analyze only, no file changes
make consolidate-apply DIR=./transcriptions  # analyze + rewrite files

# Lint
uv run ruff check .
uv run ruff format .
```

`ANTHROPIC_API_KEY` must be set in the environment before running any script.

---

## Architecture

Three independent scripts; no shared module or library layer between them.

| Script | API mode | Purpose |
|--------|----------|---------|
| `batch_pdf_processor_claude.py` | Batch API | Main processor — submits all PDFs as one job, polls until complete, writes output |
| `test_single_claude.py` | Standard API | Test one PDF interactively; prints raw response, metadata, token cost |
| `consolidate_themes.py` | Standard API | Post-process: normalize inconsistent themes across all output `.md` files |

### Data flow (batch processor)

```
PDFs → base64 encode → Anthropic Batch API → poll until "ended"
    → parse YAML fence + trailing markdown → write .md files
```

Claude's response for each document is expected to be a fenced `\`\`\`yaml` block (metadata) followed by plain markdown (transcription). `parse_claude_response()` splits on these fence markers.

### Output format

Each `.md` file has handcrafted YAML frontmatter (not `yaml.dump` — wiki-link values like `[[Name]]` get mis-quoted by pyyaml). Frontmatter field order: `title → creator → publication → source → date → people → organization → locations → themes → tags → added`. Sections after frontmatter: **Overview → Images → Notes → Connections → Transcription**.

### Source citation parsing

`parse_source_from_path()` expects PDFs organized as `Archive/Collection/Box/Folder/file.pdf` and builds the citation string `"Folder, Box, Collection, Archive"`. Falls back to `str(pdf_path.parent)` if depth < 5.

---

## Critical Conventions

**Prompts are duplicated.** The system prompt and user prompt appear in both `batch_pdf_processor_claude.py` (`HistoricalDocumentProcessor.__init__` / `create_analysis_prompt()`) and `test_single_claude.py` (`process_single_document()`). Editing one requires editing the other.

**Never use `yaml.dump` for frontmatter.** Wiki-link strings (`[[Name]]`) are quoted by pyyaml in ways Obsidian does not parse correctly. Frontmatter is built as a list of strings joined with `\n`.

**Model names are hardcoded** in `argparse choices` in both `batch_pdf_processor_claude.py` and `test_single_claude.py`. Update both when model versions change. Current choices:
- `claude-haiku-4-5-20251001`
- `claude-sonnet-4-5-20250929` (default)
- `claude-opus-4-5-20251101`

**`temperature=0.1`** is intentional for transcription accuracy. Do not raise it.
