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

This tool batch-processes historical PDFs using the Claude API to produce Obsidian-compatible markdown transcriptions with structured metadata. It solves the problem of manually transcribing archival documents at scale — a common bottleneck in academic historical research — by submitting documents in bulk to Claude's Batch API (50% cost savings) and writing output files ready for direct use in an Obsidian vault. The primary audience is academic historians and archivists who maintain large collections of primary source PDFs and want searchable, linked transcriptions with consistent entity metadata.

---

## Users & Roles

### Researcher (Primary User)
- An individual academic or archivist managing a personal or project-level collection of archival PDFs
- Goals: transcribe documents accurately, extract consistent metadata (people, places, organizations, themes), integrate with Obsidian for research notes
- Runs all scripts locally from the command line; no multi-user or permission model

---

## Business Rules

### Source Path Parsing
- The batch processor expects PDFs organized in a five-level directory hierarchy: `Archive / Collection / Box / Folder / file.pdf`
- The source citation in each output file is derived from this hierarchy in reverse order: `"Folder, Box, Collection, Archive"`
- If fewer than 5 path parts are present, the script falls back to the parent directory path

### Entity Extraction
- Only extract entities **explicitly mentioned in the document body/content**
- Do **not** extract people from letterhead, headers, footers, officer lists, or organizational rosters
- Include the author/sender and recipient when identifiable from the letter text
- Mark unclear text as `[illegible]` rather than guessing
- If uncertain about an entity, omit it

### Output Metadata Fields
Required YAML frontmatter fields in every output file:
- `title`, `creator`, `publication`, `source`, `date`
- `people`, `organization`, `locations`, `themes` (all as `[[wiki-link]]` format lists)
- `tags` (hardcoded: `to-do`, `source/primary`)
- `added` (today's date, formatted as "Month DD, YYYY")

### Obsidian Templates
The `templates/` directory provides two Obsidian note templates for manual note creation:
- `archival_template.md` — general archival documents; uses `creator` and `publication` fields; tags default to `source/primary/<item>`
- `correspondence_template.md` — letters and correspondence; uses `author` and `recipient` fields instead of `creator`/`publication`; tags default to `source/primary/letter`

These are reference templates for Obsidian's Templates plugin, not used by the scripts directly.

### Transcription Fidelity
- Preserve original spelling, punctuation, and grammar — no modernization or correction
- For multi-page documents, insert HTML page-break comments: `<!-- page 1 -->`, `<!-- page 2 -->`, etc.
- Skip boilerplate letterhead content (addresses, phone numbers, staff rosters); preserve dates, sender/recipient info, and document titles

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

### Feature: Batch PDF Processing

**Description:** Submit a directory of PDFs to Claude's Batch API in a single job. Polls for completion and writes one Obsidian markdown file per PDF.

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

### Feature: Single Document Testing

**Description:** Process one PDF using the standard (non-batch) API for quick testing of prompts and output format before committing to a large batch.

**Functionality:**
- Displays raw API response, parsed YAML metadata, entity counts, transcription preview (first 500 chars), and token usage/cost breakdown
- Accepts same model and API key options as batch processor

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

### Flow 1: Batch Processing a Document Set

**Goal:** Transcribe a folder of archival PDFs and import into Obsidian

**Steps:**
1. User organizes PDFs in the expected hierarchy: `Archive/Collection/Box/Folder/*.pdf`
2. User sets `ANTHROPIC_API_KEY` environment variable
3. User runs: `make process IN=./pdfs OUT=./transcriptions` (or `python batch_pdf_processor_claude.py --input ... --output ...`)
4. Script encodes each PDF, displays estimated cost, and submits batch job
5. Script polls status every 60 seconds, printing progress counts
6. On completion, script retrieves results and writes one `.md` file per PDF
7. User opens output directory in Obsidian; entities auto-link via `[[wiki-link]]` format

**Error Paths:**
- API key missing → exits before encoding with clear error
- Input directory doesn't exist → exits with error
- Individual document YAML parse failure → logged as warning, file still written with partial content
- Individual document API error → logged, counted as failed, processing continues

---

### Flow 2: Test a Single Document Before Batch

**Goal:** Verify prompt output quality and cost estimate on one document before a large batch

**Steps:**
1. User runs: `make test-single PDF=./sample.pdf` (or `python test_single_claude.py sample.pdf`)
2. Script displays raw response, parsed metadata, entity counts, transcription preview, and per-request cost
3. If output looks correct, user proceeds with full batch

---

### Flow 3: Consolidate Themes Across a Corpus

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
- OCR for scanned documents (Claude receives the PDF directly; degraded scans may be incomplete)
- Image extraction from PDFs
- Duplicate document detection
- CSV/JSON export of extracted metadata
- Progress bar during batch polling
- Multi-language support
- Controlled vocabulary file for theme consolidation (manual taxonomy input)

### Architectural Constraints
- No multi-user support — single researcher, local CLI only
- No database — all state is in the filesystem (markdown files)
- Batch jobs may take up to 24 hours; the script blocks while polling

---

## Open Questions

### Product
- **Q:** Should the output section order (Overview, Images, Notes, Connections, Transcription) be configurable?
  - **Status:** Not currently configurable; hardcoded in `create_obsidian_document`

### Technical
- **Q:** How should very large PDFs (exceeding Claude's context window) be handled?
  - **Status:** Currently truncated; no chunking or splitting implemented

---

*Last Updated: 2026-02-24*
*This document is maintained for AI agent context and onboarding.*
