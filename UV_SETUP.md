# uv Setup Guide

This project uses [uv](https://github.com/astral-sh/uv) for fast, reliable Python dependency management.

## Why uv?

- **10-100x faster** than pip
- **Reliable** dependency resolution
- **Compatible** with pip and requirements.txt
- **Modern** Python tooling

## Quick Start

### 1. Install uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Setup Project

```bash
# Automated setup
chmod +x setup.sh
./setup.sh

# Or manual setup
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .
```

### 3. Use Make Commands

```bash
# See all commands
make help

# Run tests
make test

# Test single PDF
make test-single PDF=./sample.pdf

# Process batch
make process IN=./pdfs OUT=./transcriptions
```

## Project Structure

```
historical-pdf-batch-processor/
├── batch_pdf_processor_claude.py  # Main processor
├── test_setup_claude.py           # Setup tests
├── test_single_claude.py          # Single PDF test
├── pyproject.toml                 # Project config (uv compatible)
├── requirements_claude.txt        # Legacy pip compatibility
├── setup.sh                       # Automated setup script
├── Makefile                       # Convenient commands
└── README_CLAUDE.md               # Full documentation
```

## Common Commands

### Install/Update Dependencies

```bash
# Install from pyproject.toml
uv pip install -e .

# Update dependencies
uv pip install --upgrade anthropic pyyaml

# Add new dependency
uv pip install <package>
# Then update pyproject.toml
```

### Create Fresh Environment

```bash
# Remove old environment
rm -rf .venv

# Create new one
uv venv

# Activate
source .venv/bin/activate

# Install
uv pip install -e .
```

### Development Workflow

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Make changes to scripts

# 3. Test
make test

# 4. Test single document
make test-single PDF=./test.pdf

# 5. Process batch
make process IN=./pdfs OUT=./transcriptions
```

## Working with Installed Commands

After `uv pip install -e .`, you get three commands:

```bash
# Instead of: python batch_pdf_processor_claude.py
batch-process --input ./pdfs --output ./transcriptions

# Instead of: python test_setup_claude.py
test-setup

# Instead of: python test_single_claude.py sample.pdf
test-single sample.pdf
```

These work from anywhere, not just the project directory.

## uv vs pip Comparison

| Task | uv | pip |
|------|-----|-----|
| Install deps | `uv pip install -e .` | `pip install -e .` |
| Create venv | `uv venv` | `python -m venv .venv` |
| Speed | 10-100x faster | Baseline |
| Compatibility | 100% pip compatible | N/A |

## Troubleshooting

### "uv: command not found"

```bash
# Add to PATH (usually automatic)
export PATH="$HOME/.cargo/bin:$PATH"

# Or reinstall
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Virtual environment not activating

```bash
# Make sure you're in project directory
cd /path/to/historical-pdf-batch-processor

# Recreate venv
rm -rf .venv
uv venv
source .venv/bin/activate
```

### Dependencies not installing

```bash
# Try with verbose output
uv pip install -e . -v

# Or fall back to pip
pip install -r requirements_claude.txt
```

## Integration with Your Workflow

### With Poetry

Already using Poetry? You can:
1. Export to requirements.txt: `poetry export -f requirements.txt > requirements.txt`
2. Use uv for faster installs: `uv pip install -r requirements.txt`

### With Conda

You can use uv inside Conda environments:
```bash
conda activate myenv
uv pip install -e .
```

### In CI/CD

```yaml
# GitHub Actions example
- name: Setup uv
  run: curl -LsSf https://astral.sh/uv/install.sh | sh

- name: Install dependencies
  run: |
    uv venv
    source .venv/bin/activate
    uv pip install -e .
```

## Performance Tips

### Cache uv packages

uv automatically caches packages. To clear cache:
```bash
uv cache clean
```

### Parallel installs

uv installs packages in parallel by default - no extra flags needed.

### Faster Docker builds

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

WORKDIR /app
COPY pyproject.toml .
RUN uv venv && uv pip install -e .

COPY . .
```

## Additional Resources

- [uv Documentation](https://github.com/astral-sh/uv)
- [pyproject.toml Spec](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [Project README](README_CLAUDE.md)
- [Quick Start Guide](QUICKSTART_CLAUDE.md)
