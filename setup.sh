#!/usr/bin/env bash
# Setup script for Historical PDF Batch Processor
# Uses uv for fast dependency installation

set -e

echo "=================================================="
echo "Historical PDF Batch Processor - Setup"
echo "=================================================="
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv not found"
    echo ""
    echo "Install uv with:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    echo "Or with brew:"
    echo "  brew install uv"
    echo ""
    exit 1
fi

echo "✓ Found uv $(uv --version)"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    uv venv
    echo "✓ Virtual environment created"
    echo ""
else
    echo "✓ Virtual environment exists"
    echo ""
fi

# Install dependencies
echo "📥 Installing dependencies..."
uv pip install -e .
echo "✓ Dependencies installed"
echo ""

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "⚠️  ANTHROPIC_API_KEY not set"
    echo ""
    echo "Get your API key from: https://console.anthropic.com/"
    echo "Then set it with:"
    echo "  export ANTHROPIC_API_KEY='your-key-here'"
    echo ""
    echo "Or add to your shell profile:"
    echo "  echo 'export ANTHROPIC_API_KEY=\"your-key\"' >> ~/.zshrc"
    echo ""
else
    echo "✓ ANTHROPIC_API_KEY is set"
    echo ""
fi

# Run tests
echo "🧪 Running setup tests..."
source .venv/bin/activate
python test_setup_claude.py
echo ""

echo "=================================================="
echo "✅ Setup complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Activate the virtual environment:"
echo "     source .venv/bin/activate"
echo ""
echo "  2. Test with a single PDF:"
echo "     python test_single_claude.py path/to/sample.pdf"
echo ""
echo "  3. Process a batch:"
echo "     python batch_pdf_processor_claude.py -i ./pdfs -o ./transcriptions"
echo ""
echo "Or use the installed commands:"
echo "  batch-process -i ./pdfs -o ./transcriptions"
echo "  test-setup"
echo "  test-single path/to/sample.pdf"
echo ""
