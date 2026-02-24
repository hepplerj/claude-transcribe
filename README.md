# Historical Document Batch Processor - Claude API

> ⚠️ This is a vibe coded test, so use at your own risk.

Batch process historical PDFs using Claude's API to create transcriptions and extract structured metadata for Obsidian.

**50% cost savings with batch processing** | **Privacy-first: No training on your data**

## Features

- **Batch Processing**: 50% discount on all token costs (input + output)
- **Privacy Protected**: Data NOT used for training, 7-day retention
- **Accurate Transcription**: Preserves original spelling, punctuation, and formatting
- **Entity Extraction**: Identifies people, organizations, locations, and themes
- **Obsidian Integration**: Outputs markdown with wiki-links and YAML frontmatter
- **Source Tracking**: Maintains links back to original PDF files
- **Hallucination Prevention**: Strict prompting to avoid invented information

## Installation

### Using uv (Recommended)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or: brew install uv

# Automated setup (creates venv, installs deps, runs smoke tests)
chmod +x setup.sh
./setup.sh

# Or manual setup
uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e .
```

After installing with `uv pip install -e .`, three CLI shortcuts are available from anywhere:

```bash
batch-process --input ./pdfs --output ./transcriptions  # instead of python batch_pdf_processor_claude.py
test-setup                                              # instead of python test_setup_claude.py
test-single sample.pdf                                  # instead of python test_single_claude.py
```

### Using pip

```bash
pip install -r requirements_claude.txt
```

### Using Make

```bash
make setup  # Complete setup with uv
```

## Setup

### 1. Get Claude API Key

1. Go to [Claude Console](https://console.anthropic.com/)
2. Sign up or log in
3. Navigate to API Keys
4. Create a new key
5. You get $5 in free credits to start!

Set it as an environment variable:

```bash
export ANTHROPIC_API_KEY='your-api-key-here'
```

Or add to your shell profile (~/.zshrc, ~/.bashrc):
```bash
echo 'export ANTHROPIC_API_KEY="your-api-key-here"' >> ~/.zshrc
```

### 2. Organize Your Files

```
project/
├── pdfs/           # Input: Your PDF files
├── transcriptions/ # Output: Generated markdown
└── batch_pdf_processor_claude.py
```

## Usage

### Quick Start with Make

```bash
# See all available commands
make help

# Process documents (default: Sonnet model)
make process IN=./pdfs OUT=./transcriptions

# Process with specific models
make process-haiku IN=./pdfs OUT=./transcriptions  # Fastest/cheapest
make process-opus IN=./pdfs OUT=./transcriptions   # Most accurate

# Test single document
make test-single PDF=./sample.pdf

# Run setup tests
make test
```

### Basic Usage

```bash
python batch_pdf_processor_claude.py --input ./pdfs --output ./transcriptions
```

### With Custom Model

```bash
# Fastest/cheapest - good for clear typed documents
python batch_pdf_processor_claude.py \
  --input ./sources \
  --output ./notes \
  --model claude-haiku-4-5-20251001

# Most accurate - best for complex/handwritten documents  
python batch_pdf_processor_claude.py \
  --input ./sources \
  --output ./notes \
  --model claude-opus-4-5-20251101
```

### Arguments

- `-i, --input`: Input directory containing PDF files (required)
- `-o, --output`: Output directory for markdown files (required)
- `--api-key`: Anthropic API key (optional if ANTHROPIC_API_KEY is set)
- `--model`: Claude model to use (default: claude-sonnet-4-5-20250929)
  - `claude-haiku-4-5-20251001` - Fastest, cheapest
  - `claude-sonnet-4-5-20250929` - Balanced (recommended)
  - `claude-opus-4-5-20251101` - Most capable
- `--check-interval`: Seconds between batch status checks (default: 60)

## Pricing (with Batch API - 50% off)

| Model | Input (per MTok) | Output (per MTok) | Best For |
|-------|-----------------|-------------------|----------|
| **Haiku 4.5** | $0.50 | $2.50 | Clear, typed documents |
| **Sonnet 4.5** | $1.50 | $7.50 | General use (recommended) |
| **Opus 4.5** | $2.50 | $12.50 | Complex/handwritten docs |

**Typical costs (10-page PDF):**
- Haiku: ~$0.015 per document
- Sonnet: ~$0.0225 per document  
- Opus: ~$0.0375 per document

**100 documents:**
- Haiku: ~$1.50
- Sonnet: ~$2.25
- Opus: ~$3.75

*Includes $5 in free credits to start*

## Privacy & Data Handling

Unlike consumer AI tools, the Claude commercial API:

✅ **NOT used for model training** (ever)  
✅ **7-day data retention** (down from 30 days as of Sept 2025)  
✅ **No human review** (unless flagged for safety violations)  
✅ **Workspace isolation** (your data never mixes with others)  
✅ **Zero data retention available** (enterprise customers)

This means your historical documents remain private for your research.

## Output Format

Each PDF generates a markdown file with this structure:

```markdown
---
title: Letter from Harold Ickes to Bernard DeVoto
creator: [[Harold Ickes]]
publication:
source: Folder 12, Box 3, DeVoto Papers, American Heritage Center
date: 1946-04-10
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
  - source/primary
added: February 05, 2025
---

## Overview

Brief 2-3 sentence summary of the document's content.

## Images

![[letter-ickes-devoto-1946.pdf]]

## Notes


## Connections


## Transcription

[Exact text from the document...]
```

### Obsidian Templates

The `templates/` directory contains Obsidian note templates for use with Obsidian's core Templates plugin:

- **`archival_template.md`** — General archival documents (uses `creator` and `publication` fields)
- **`correspondence_template.md`** — Letters and correspondence (uses `author` and `recipient` fields instead)

To use: copy the `templates/` folder into your Obsidian vault and configure the Templates plugin to point to it.

## How It Works

### 1. PDF Encoding
The script encodes each PDF to base64 for API submission

### 2. Batch Submission
All documents are submitted as a single batch job with:
- 50% cost discount
- Low temperature (0.1) for accuracy
- Strict system instructions against hallucination
- Prompts emphasizing exact transcription

### 3. Asynchronous Processing
- Most batches complete in under 1 hour
- Maximum processing time: 24 hours
- Results available for 29 days

### 4. Entity Extraction
Claude extracts only explicitly mentioned:
- People (proper names)
- Organizations (companies, agencies, groups)
- Locations (places, regions, landmarks)
- Themes (major topics and subjects)

### 5. Wiki-Link Formatting
All entities are formatted as `[[Entity Name]]` for Obsidian linking

### 6. Output Generation
Creates structured markdown files with:
- YAML frontmatter
- Entity lists
- Notes section (for your research)
- Full transcription

## Accuracy Guidelines

The system is designed to prevent hallucinations:

- **Only Explicit Entities**: Won't infer people/places not directly mentioned
- **Exact Transcription**: Preserves original spelling and grammar
- **Illegible Marking**: Uses `[illegible]` for unclear text instead of guessing
- **No Modernization**: Keeps historical language intact
- **No Interpretation**: Provides facts, not analysis

## Workflow Integration

### With Obsidian

1. Run the batch processor
2. Open output directory in Obsidian
3. Entities automatically create linked notes
4. Add your analysis in the Notes section
5. Use Obsidian's graph view to explore connections

### With Zettelkasten

The output structure works naturally with your notecard system:
- Each transcription is a source card
- Entities become index cards
- Notes section for your analysis cards
- Wiki-links preserve connections

### Post-Processing

Review generated files for:
- Transcription accuracy (especially for handwritten or degraded documents)
- Entity completeness (Claude errs on the side of caution)
- Date formatting (may need standardization)
- Theme relevance (may need refinement)

## Troubleshooting

### "No PDF files found"
Check that your input directory contains .pdf files (case-sensitive)

### "API key required"
Set ANTHROPIC_API_KEY environment variable or use --api-key parameter

### "YAML parsing error"
Claude occasionally formats YAML incorrectly. The script will note this and save what it can.

### Slow Processing
- Most batches complete in <1 hour
- Check status with the batch ID in Claude Console
- Use `--check-interval` to adjust polling frequency

### Incomplete Transcriptions
Some documents may be:
- Too large (very long PDFs may be truncated)
- Too degraded (consider manual transcription)
- Complex layouts (try Opus model)

### "uv: command not found"
```bash
export PATH="$HOME/.cargo/bin:$PATH"
# Or reinstall: curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Virtual environment issues
```bash
rm -rf .venv
uv venv
source .venv/bin/activate
uv pip install -e .
```

## Examples

### Processing Dissertation Sources
```bash
python batch_pdf_processor_claude.py \
  --input ~/Research/Sagebrush/sources \
  --output ~/Research/Sagebrush/transcriptions \
  --model claude-sonnet-4-5-20250929
```

### Newsletter Research Materials
```bash
python batch_pdf_processor_claude.py \
  --input ~/Newsletter/pdfs \
  --output ~/Newsletter/notes \
  --model claude-haiku-4-5-20251001
```

### Congressional Documents
```bash
python batch_pdf_processor_claude.py \
  --input ~/Documents/Congressional-Testimony \
  --output ~/Obsidian/Sources \
  --model claude-opus-4-5-20251101
```

## Comparison with Other Options

| Feature | Claude API | Gemini API (Free) | Gemini API (Paid) |
|---------|-----------|-------------------|-------------------|
| Training on data | ❌ Never | ✅ Yes | ❌ Opt-out default |
| Data retention | 7 days | 55 days | 55 days |
| Batch discount | 50% off | None | None |
| Human review | Safety only | Yes | Limited |
| Privacy controls | Strong | Weak | Moderate |
| Cost (100 docs) | ~$2.25 | Free | ~$1-2 |

**Recommendation**: For research with publicly accessible archival materials, Claude offers the best balance of privacy, cost, and quality.

## Future Enhancements

Potential additions:
- Image extraction from PDFs
- OCR for scanned documents
- Integration with existing Obsidian vault structure
- Batch result exports (CSV/JSON)
- Progress bar during processing
- Duplicate detection
- Multi-language support

## Support

For issues with:
- **Script**: Check the troubleshooting section above
- **Claude API**: See [Anthropic documentation](https://docs.anthropic.com/)
- **Obsidian**: See [Obsidian documentation](https://help.obsidian.md/)

## License

MIT License - feel free to modify for your research needs

---

**Ready to get started?** Check out [QUICKSTART.md](QUICKSTART.md) for a 5-minute setup guide.
