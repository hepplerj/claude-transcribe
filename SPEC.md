# SPEC.md

> For technical implementation details, architecture, and developer documentation, see [AGENTS.md](./AGENTS.md).

---

## Table of Contents

- [Overview](#overview)
- [Users & Roles](#users--roles)
- [Business Rules](#business-rules)
- [Features](#features)
- [User Flows](#user-flows)
- [Out of Scope](#out-of-scope)
- [Open Questions](#open-questions)

---

## Overview

This tool batch-processes historical PDFs using the Claude or Gemini APIs to produce Obsidian-compatible markdown transcriptions with structured metadata. It solves the problem of manually transcribing archival documents at scale — a common bottleneck in academic historical research — by submitting documents in bulk and writing output files ready for direct use in an Obsidian vault.

Three processing pipelines are available:
- **Image-based (Claude Batch API):** PDFs sent directly as base64; Claude transcribes from vision. 50% cost savings via batch API.
- **Vision OCR (macOS only):** PDFs rasterized locally, OCR'd via Apple Vision framework, text sent to Claude for correction and entity extraction. Significantly cheaper input costs for typed documents.
- **Gemini:** Sequential processing with free-tier rate limiting available.

The primary audience is academic historians and archivists who maintain large collections of primary source PDFs and want searchable, linked transcriptions with consistent entity metadata.

---

## Users & Roles

### Researcher (Primary User)
- An individual academic or archivist managing a personal or project-level collection of archival PDFs
- Goals: transcribe documents accurately, extract consistent metadata (people, places, organizations, themes), integrate with Obsidian for research notes
- Runs all scripts locally from the command line; no multi-user or permission model

---

## Business Rules

### Source Path Parsing
- All processors expect PDFs organized in a five-level directory hierarchy: `Archive / Collection / Box / Folder / file.pdf`
- The source citation in each output file is derived from this hierarchy in reverse order: `"Folder, Box, Collection, Archive"`
- If fewer than 5 path parts are present, the script falls back to the parent directory path

### Entity Extraction
- Only extract entities **explicitly mentioned in the document body/content**
- Do **not** extract people from letterhead, headers, footers, officer lists, or organizational rosters
- Include the author/sender and recipient when identifiable from the letter text
- Mark unclear text as `[illegible]` rather than guessing
- If uncertain about an entity, omit it

### OCR Correction (Vision Pipeline)
- Fix only demonstrable OCR character substitutions — do not silently alter historical content
- When correction is certain (clear substitution + context confirms it): correct silently
- When reconstruction relies on inference: mark as `[reconstructed: ...]`
- When text is truly unrecoverable: mark as `[illegible]`
- Paratext (stamps, fax headers, marginal annotations): note their presence but exclude from transcription body; annotate inline (e.g. `[marginal notation present: "2:00pm"]`)

### OCR Confidence Threshold
- The Vision OCR pipeline reports a per-document average confidence score (0.0–1.0) across all text observations on all pages
- Documents below `--confidence-threshold` (default 0.5) are flagged in a summary report at run end
- Flagged documents are still processed normally — the threshold only triggers a log entry, not skipping
- Flagged documents may benefit from reprocessing with the image-based pipeline (using a vision model rather than OCR text)

### Output Metadata Fields
Required YAML frontmatter fields in every output file:
- `title`, `creator`, `publication`, `source`, `date`, `doc_type`
- `people`, `organization`, `locations`, `themes` (all as `[[wiki-link]]` format lists)
- `tags`: `to-do` and `source/primary/{doc_type}` (e.g. `source/primary/letter`)
- `added` (today's date in ISO format: `YYYY-MM-DD`)

When `--skip-claude` is used in the Vision pipeline, only `source` is populated from the path; all other fields are left blank.

### Obsidian Templates
The `templates/` directory provides two Obsidian note templates for manual note creation:
- `archival_template.md` — general archival documents; uses `creator` and `publication` fields; tags default to `source/primary/<item>`
- `correspondence_template.md` — letters and correspondence; uses `author` and `recipient` fields instead of `creator`/`publication`; tags default to `source/primary/letter`

These are reference templates for Obsidian's Templates plugin, not used by the scripts directly.

### Transcription Fidelity
- Preserve original spelling, punctuation, and grammar — no modernization or correction
- For multi-page documents, insert HTML page-break comments: `<!-- page 1 -->`, `<!-- page 2 -->`, etc.
- Apply document-type-specific boilerplate rules:
  - **Letters**: skip letterhead (addresses, phone numbers, officer/staff lists); preserve date, sender org, recipient
  - **Newspaper articles**: skip mastheads, column headers, page numbers, ad copy; preserve dateline, headline, byline, body
  - **Reports/memoranda**: skip cover page boilerplate; preserve title, date, authoring office, body
- When skipping non-content sections, note the omission inline: `[letterhead omitted]`, `[masthead omitted]`, etc.

### Model Parameters
- Requests use `temperature: 0.1` for factual accuracy
- `max_tokens: 8192` per document
- Single-document test mode uses standard (non-batch) pricing

### Theme Consolidation (Post-Processing)
- Run after a full batch completes, not mid-batch
- Consolidation is conservative: Claude only merges themes that clearly refer to the same concept
- When `--apply` is used, original themes are preserved in `original_themes` frontmatter field and a `themes_consolidated: true` flag is set
- Backup `.bak` files are created by default before any file updates

---

## Features

### Feature: Batch PDF Processing (Image-Based)

**Description:** Submit a directory of PDFs to Claude's Batch API in a single job. PDFs are encoded as base64 and sent to Claude's vision model. Polls for completion and writes one Obsidian markdown file per PDF.

**Functionality:**
- Recursively finds all `.pdf` files in the input directory
- Encodes each PDF as base64 and submits as a single batch job
- Polls batch status every N seconds (configurable, default 60)
- Parses Claude's structured YAML + transcription response per document
- Writes output `.md` files with YAML frontmatter, Overview, Images embed, Notes, Connections, and Transcription sections
- Displays estimated batch cost before submission

**Edge Cases:**
- YAML parsing failure: logs a warning, saves what it can, continues
- Empty API response: logs the failure, counts toward `failed` total
- No PDF files found in input directory: exits with message
- Missing API key: exits with error before submission

---

### Feature: Vision OCR Pipeline (macOS only)

**Description:** Rasterize PDFs locally via PyMuPDF, extract text using Apple's Vision framework OCR, then send only the text to Claude for correction and entity extraction. Substantially cheaper than the image-based pipeline for typed documents because input tokens are text rather than images.

**Functionality:**
- Rasterizes each PDF page to a PNG image at configurable DPI (default 200; use 300 for degraded docs)
- Runs `VNRecognizeTextRequest` (accurate level, language correction enabled) on each page image
- Reports per-page and per-document average OCR confidence scores
- Documents below `--confidence-threshold` are flagged in a summary at run end
- Sends OCR text to Claude Batch API as plain text content (not base64 image)
- Displays estimated cost based on actual OCR character count
- Writes same Obsidian markdown output format as the image-based pipeline

**`--skip-claude` mode:**
- Skips the Claude API call entirely (no API key required)
- Writes raw OCR text directly into the Transcription section with minimal frontmatter
- Useful for inspecting OCR quality before committing to a Claude batch, or when Vision confidence is high enough that correction isn't needed

**`--ocr-out FILE` (test script only):**
- Saves raw OCR text to a file for offline inspection before the Claude step

**Edge Cases:**
- Zero text extracted from a page: logged as a warning; document still submitted/written
- Low confidence document: flagged and logged, processing continues normally
- Non-macOS system: exits immediately with a clear error message

---

### Feature: Single Document Testing

**Description:** Process one PDF using the standard (non-batch) API for quick testing of prompts and output format before committing to a large batch. Available for both the image-based and Vision OCR pipelines.

**Functionality:**
- Vision version displays raw OCR text and per-page confidence scores before the Claude step
- Displays raw API response, parsed YAML metadata, entity counts, transcription preview (first 500 chars), and token usage/cost breakdown
- Accepts same model, API key, and pipeline-specific options as the corresponding batch processor

---

### Feature: Theme Consolidation

**Description:** After batch processing, scan all output markdown files, collect all unique themes, and use Claude to identify variants of the same concept. Optionally rewrite files with canonical theme names.

**Functionality:**
- Extracts themes from YAML frontmatter of all `.md` files in a directory
- Strips `[[wiki-link]]` brackets for analysis, re-applies them on output
- Generates a `theme_analysis.md` report with counts, groups, and reduction statistics
- `--apply` flag rewrites frontmatter with canonical themes; preserves originals in `original_themes`
- `--backup` flag (default: on) creates `.bak` files before any writes

---

## User Flows

### Flow 1: Vision OCR Batch (Recommended for Typed Documents)

**Goal:** Transcribe typed archival PDFs cheaply using local OCR + Claude text correction

**Steps:**
1. User installs Vision dependencies: `make install-vision`
2. User organizes PDFs in the expected hierarchy: `Archive/Collection/Box/Folder/*.pdf`
3. User sets API key in `.env` or environment
4. Optionally, user tests one document first: `make test-vision PDF=./sample.pdf`
   - Raw OCR text and per-page confidence scores are displayed
   - Claude's corrected output and cost estimate are shown
5. User runs: `make process-vision IN=./pdfs OUT=./transcriptions`
6. Script OCRs each PDF locally, logs confidence scores, submits text batch to Claude
7. On completion, script retrieves results and writes one `.md` file per PDF
8. Any flagged low-confidence documents are listed at the end for manual review
9. User opens output directory in Obsidian; entities auto-link via `[[wiki-link]]` format

**Confidence-based routing:**
- High confidence docs (≥0.5): proceed through Vision OCR pipeline
- Low confidence docs flagged in summary: consider reprocessing with `make process` (image-based)

---

### Flow 2: Image-Based Batch Processing

**Goal:** Transcribe a folder of archival PDFs (any quality) using Claude's vision model

**Steps:**
1. User organizes PDFs in the expected hierarchy: `Archive/Collection/Box/Folder/*.pdf`
2. User sets `ANTHROPIC_API_KEY` in `.env` or environment
3. User runs: `make process IN=./pdfs OUT=./transcriptions`
4. Script encodes each PDF, displays estimated cost, and submits batch job
5. Script polls status every 60 seconds, printing progress counts
6. On completion, script retrieves results and writes one `.md` file per PDF
7. User opens output directory in Obsidian; entities auto-link via `[[wiki-link]]` format

---

### Flow 3: OCR-Only (No Claude)

**Goal:** Quickly dump OCR text to Obsidian notes without any API cost

**Steps:**
1. User runs: `make process-vision IN=./pdfs OUT=./transcriptions` with `--skip-claude`
   (or: `python batch_pdf_processor_vision.py --input ./pdfs --output ./out --skip-claude`)
2. Script OCRs each PDF, writes minimal `.md` files with raw OCR as transcription
3. User reviews output in Obsidian; selectively reprocesses poor-quality documents with Claude

---

### Flow 4: Consolidate Themes Across a Corpus

**Goal:** Standardize inconsistent theme tags produced by independent per-document processing

**Steps:**
1. User runs theme analysis first (no file changes): `make consolidate DIR=./transcriptions`
2. User reviews `theme_analysis.md` report to verify proposed consolidations
3. User applies changes: `make consolidate-apply DIR=./transcriptions`
4. Script rewrites frontmatter of each `.md` file with canonical themes; `.bak` backups created
5. If results are unsatisfactory, user restores from `.bak` files

---

## Out of Scope

### Not Currently Implemented
- GUI or web interface
- Spatial column sorting for newspaper OCR (bounding box layout analysis) — groundwork laid with per-page rasterization, but column ordering not implemented
- Duplicate document detection
- CSV/JSON export of extracted metadata
- Progress bar during batch polling
- Multi-language support
- Controlled vocabulary file for theme consolidation (manual taxonomy input)
- Automatic fallback from Vision OCR to image-based pipeline for low-confidence documents

### Architectural Constraints
- Vision OCR pipeline is macOS-only (Apple Vision framework dependency)
- No multi-user support — single researcher, local CLI only
- No database — all state is in the filesystem (markdown files)
- Batch jobs may take up to 24 hours; the script blocks while polling

---

## Open Questions

### Product
- **Q:** Should the output section order (Overview, Images, Notes, Connections, Transcription) be configurable?
  - **Status:** Not currently configurable; hardcoded in `create_obsidian_document`

- **Q:** Should low-confidence documents be automatically routed to the image-based pipeline within the same run?
  - **Status:** Currently just logged; manual reprocessing required

### Technical
- **Q:** How should very large PDFs (exceeding Claude's context window) be handled?
  - **Status:** Currently truncated; no chunking or splitting implemented

- **Q:** Should newspaper column bounding boxes be spatially sorted for correct reading order?
  - **Status:** Not implemented; Vision returns observations in approximate top-to-bottom order which may not respect column layout

---

*Last Updated: 2026-03-21*
*This document is maintained for AI agent context and onboarding.*
