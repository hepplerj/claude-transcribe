# Makefile for Historical PDF Batch Processor

.PHONY: help install setup test test-single clean process

help:  ## Show this help message
	@echo "Historical PDF Batch Processor - Make Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies with uv
	@echo "Installing dependencies..."
	@uv pip install -e .

setup:  ## Complete setup (venv + deps + tests)
	@bash setup.sh

test:  ## Run setup tests
	@python test_setup_claude.py

test-single:  ## Test single PDF (usage: make test-single PDF=path/to/file.pdf)
	@if [ -z "$(PDF)" ]; then \
		echo "Usage: make test-single PDF=path/to/file.pdf"; \
		exit 1; \
	fi
	@python test_single_claude.py $(PDF)

process:  ## Process PDFs (usage: make process IN=./pdfs OUT=./transcriptions)
	@if [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make process IN=./pdfs OUT=./transcriptions"; \
		exit 1; \
	fi
	@python batch_pdf_processor_claude.py --input $(IN) --output $(OUT)

process-haiku:  ## Process with Haiku (fastest/cheapest)
	@if [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make process-haiku IN=./pdfs OUT=./transcriptions"; \
		exit 1; \
	fi
	@python batch_pdf_processor_claude.py --input $(IN) --output $(OUT) --model claude-haiku-4-5-20251001

process-opus:  ## Process with Opus (most accurate)
	@if [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make process-opus IN=./pdfs OUT=./transcriptions"; \
		exit 1; \
	fi
	@python batch_pdf_processor_claude.py --input $(IN) --output $(OUT) --model claude-opus-4-5-20251101

clean:  ## Remove virtual environment and cache files
	@echo "Cleaning up..."
	@rm -rf .venv
	@rm -rf __pycache__
	@rm -rf *.pyc
	@rm -rf .pytest_cache
	@rm -rf .ruff_cache
	@echo "✓ Clean complete"

.DEFAULT_GOAL := help
