# Quick Start Guide - Claude API Version

Get up and running with the Historical Document Batch Processor in 5 minutes.

**Privacy First** • **50% Cost Savings** • **No Training on Your Data**

## Prerequisites

- Python 3.8 or higher
- Anthropic account (free to start, $5 credit included)
- PDF documents to process

## Step 1: Install Dependencies

### Option A: Using uv (Recommended - Much Faster)

Install uv if you don't have it:
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv
```

Run the setup script:
```bash
chmod +x setup.sh
./setup.sh
```

Or manually:
```bash
uv venv                    # Create virtual environment
source .venv/bin/activate  # Activate it
uv pip install -e .        # Install dependencies
```

### Option B: Using pip (Traditional)

```bash
pip install -r requirements_claude.txt
```

**Both methods install:**
- `anthropic` - Claude API client  
- `PyYAML` - YAML parsing

## Step 2: Get API Key

1. Go to: https://console.anthropic.com/
2. Sign up (you get $5 free credit!)
3. Navigate to "API Keys"
4. Click "Create Key"
5. Copy your key
6. Set it in your environment:

```bash
export ANTHROPIC_API_KEY='your-api-key-here'
```

**Make it permanent** (add to ~/.zshrc or ~/.bashrc):
```bash
echo 'export ANTHROPIC_API_KEY="your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

## Step 3: Test Your Setup

### Using Make (Easiest)

```bash
make test
```

### Using Python Directly

```bash
python test_setup_claude.py
```

You should see:
```
✓ API Key Configuration
✓ YAML Processing
✓ File System Operations
✓ PDF Support
✓ API Connection
✓ Batch API

6/6 tests passed
✅ All tests passed! You're ready to process documents.
```

If any tests fail, address the issues before continuing.

## Step 4: Test Single Document

Before processing a large batch, test one document:

```bash
python test_single_claude.py path/to/sample.pdf
```

This will:
1. Encode the PDF
2. Send it to Claude
3. Show you the raw response
4. Display extracted metadata
5. Preview the transcription
6. Show token usage and estimated batch cost

**Check the output carefully:**
- Is the transcription accurate?
- Are entities correctly identified?
- Is the YAML valid?

If anything looks wrong, you can adjust the prompts in `batch_pdf_processor_claude.py`.

## Step 5: Process Your Batch

### Using Make (Easiest)

```bash
# Process with default model (Sonnet)
make process IN=./pdfs OUT=./transcriptions

# Or use specific models
make process-haiku IN=./pdfs OUT=./transcriptions  # Fastest/cheapest
make process-opus IN=./pdfs OUT=./transcriptions   # Most accurate
```

### Using Python Directly

Once you're satisfied with the test results:

```bash
python batch_pdf_processor_claude.py \
  --input ./pdfs \
  --output ./transcriptions
```

### Using Installed Command

If you installed with `uv pip install -e .`:

```bash
batch-process --input ./pdfs --output ./transcriptions
```

The script will:
1. Encode all PDFs to base64
2. Create batch requests
3. Submit to Claude API
4. Poll for completion (every 60 seconds)
5. Generate markdown files in the output directory

**Typical timeline:**
- 10 documents: ~15-30 minutes
- 50 documents: ~30-60 minutes
- 100 documents: ~1-2 hours

Most batches complete faster than the maximum 24-hour window.

## Step 6: Review Output

Open the output directory:

```bash
ls -lh ./transcriptions/
```

Each PDF will have a corresponding `.md` file with:
- YAML frontmatter with metadata
- Entity lists (people, organizations, locations, themes)
- Notes section (for your research)
- Full transcription

**Open in Obsidian:**

1. Open Obsidian
2. "Open folder as vault" → select `transcriptions` directory
3. Browse your processed documents
4. Use wiki-links to explore connections

## Model Selection Guide

Choose the right model for your documents:

### Claude Haiku 4.5 ($0.50/$2.50 per MTok)
**Use for:**
- Clean, typed documents
- Simple layouts
- High volume processing
- Budget constraints

**Cost:** ~$1.50 per 100 documents

### Claude Sonnet 4.5 ($1.50/$7.50 per MTok) ← Recommended
**Use for:**
- General-purpose processing
- Mixed document quality
- Balance of speed and accuracy
- Most use cases

**Cost:** ~$2.25 per 100 documents

### Claude Opus 4.5 ($2.50/$12.50 per MTok)
**Use for:**
- Handwritten documents
- Poor quality scans
- Complex layouts
- Maximum accuracy needed

**Cost:** ~$3.75 per 100 documents

Change model with `--model` flag:
```bash
python batch_pdf_processor_claude.py \
  --input ./pdfs \
  --output ./transcriptions \
  --model claude-haiku-4-5-20251001
```

## Privacy & Data Security

**What happens to your data:**

✅ **NOT used for training** - Your documents never train Claude  
✅ **7-day retention** - Automatically deleted after 7 days  
✅ **No human review** - Only automated safety checks  
✅ **Workspace isolated** - Your data never mixes with others  

**This is different from consumer Claude:**
- Free/Pro/Team accounts can opt-in to training
- API (commercial) accounts never train on data
- Much stronger privacy guarantees

## Common Workflows

### Research Project Structure

```
my-research/
├── sources/
│   ├── congressional-hearings/
│   ├── newspapers/
│   └── agency-reports/
├── transcriptions/
│   ├── congressional-hearings/
│   ├── newspapers/
│   └── agency-reports/
└── notes/
```

Process by category:

```bash
# Congressional hearings
python batch_pdf_processor_claude.py \
  --input sources/congressional-hearings \
  --output transcriptions/congressional-hearings

# Newspapers  
python batch_pdf_processor_claude.py \
  --input sources/newspapers \
  --output transcriptions/newspapers
```

### Zettelkasten Integration

```
zettelkasten/
├── 0-inbox/          # Process PDFs here
├── 1-sources/        # Generated transcriptions
├── 2-literature/     # Your literature notes
├── 3-permanent/      # Permanent notes
└── 4-index/          # Index cards
```

Workflow:
1. Drop PDFs in `0-inbox/`
2. Run: `python batch_pdf_processor_claude.py -i 0-inbox -o 1-sources`
3. Review transcriptions in `1-sources/`
4. Create literature notes in `2-literature/`
5. Extract permanent notes to `3-permanent/`

### Newsletter Research

```
newsletter/
├── sources/         # PDFs for upcoming issues
├── processed/       # Transcribed documents
└── drafts/          # Newsletter drafts
```

Monthly workflow:
```bash
# Process all sources for February issue
python batch_pdf_processor_claude.py \
  --input sources/2025-02 \
  --output processed/2025-02
```

## Troubleshooting

### Issue: "No PDF files found"

**Check:**
```bash
ls -la ./pdfs/*.pdf
```

### Issue: "API key required"

**Fix:**
```bash
echo $ANTHROPIC_API_KEY  # Should show your key
export ANTHROPIC_API_KEY='your-key-here'
```

### Issue: Poor transcription quality

**Try:**
1. Use `claude-opus-4-5-20251101` for complex documents
2. Test single document first to verify quality
3. Check if PDF is readable (not corrupted/encrypted)

### Issue: Missing entities

**Remember:** The system is conservative to avoid hallucinations.

Claude only includes entities explicitly mentioned in the document. If you need inferred entities, add them manually in the Notes section.

### Issue: Batch taking too long

**Normal behavior:**
- Most batches complete in <1 hour
- Maximum: 24 hours
- You can check status in Claude Console with batch ID

## Cost Management

### Free Credits
You start with $5 in free credits = enough for:
- ~220 documents with Haiku
- ~140 documents with Sonnet
- ~130 documents with Opus

### Monitoring Usage
Check your usage at: https://console.anthropic.com/settings/usage

### Setting Limits
Set monthly budget limits in Console to avoid surprises.

### Optimization Tips
1. Use Haiku for clear documents
2. Only use Opus when necessary
3. Batch process (automatic 50% savings)
4. Remove duplicate files before processing

## Next Steps

Once you're comfortable with the basic workflow:

1. **Integrate with Obsidian** - Set up templates, queries, dataview
2. **Customize prompts** - Add domain-specific instructions
3. **Build research database** - Use outputs for literature review
4. **Create connections** - Use wiki-links to build knowledge graph
5. **Develop workflow** - Integrate into your research process

## Support

- **Claude API Issues**: https://docs.anthropic.com/
- **YAML Problems**: Check syntax at http://www.yamllint.com/
- **Obsidian Help**: https://help.obsidian.md/

## Comparison: Why Claude API?

vs **Consumer Claude (Free/Pro/Max)**:
- ❌ Consumer: Can opt-in to training
- ✅ API: Never trains on data

vs **Gemini Free API**:
- ❌ Gemini: Uses data for training
- ✅ Claude: Never trains on data

vs **Gemini Paid API**:
- ⚠️ Gemini: 55-day retention
- ✅ Claude: 7-day retention

vs **GPT-4 API**:
- ⚠️ GPT-4: 30-day retention
- ✅ Claude: 7-day retention, 50% batch discount

**Bottom line:** Claude API offers the best combination of privacy, cost, and quality for research document processing.

---

**You're ready to go!** Start with a small test batch and scale up as you get comfortable with the workflow.

Questions? Check the full [README_CLAUDE.md](README_CLAUDE.md) for detailed documentation.
