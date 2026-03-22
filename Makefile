# Makefile for Historical PDF Batch Processor

PYTHON := .venv/bin/python

# Load .env if present
-include .env
export

.PHONY: help install setup test test-single clean \
        process process-haiku process-opus \
        install-gemini test-gemini process-gemini process-gemini-pro \
        install-local list-models process-local \
        install-vision test-vision process-vision \
        estimate cost-check consolidate consolidate-apply

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
	@$(PYTHON) test_setup_claude.py

test-single:  ## Test single PDF (usage: make test-single PDF=path/to/file.pdf)
	@if [ -z "$(PDF)" ]; then \
		echo "Usage: make test-single PDF=path/to/file.pdf"; \
		exit 1; \
	fi
	@$(PYTHON) test_single_claude.py "$(PDF)"

process:  ## Process PDFs (usage: make process IN=./pdfs OUT=./transcriptions)
	@if [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make process IN=./pdfs OUT=./transcriptions"; \
		exit 1; \
	fi
	@$(PYTHON) batch_pdf_processor_claude.py --input "$(IN)" --output "$(OUT)"

process-haiku:  ## Process with Haiku (fastest/cheapest)
	@if [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make process-haiku IN=./pdfs OUT=./transcriptions"; \
		exit 1; \
	fi
	@$(PYTHON) batch_pdf_processor_claude.py --input "$(IN)" --output "$(OUT)" --model claude-haiku-4-5-20251001

process-opus:  ## Process with Opus (most accurate)
	@if [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make process-opus IN=./pdfs OUT=./transcriptions"; \
		exit 1; \
	fi
	@$(PYTHON) batch_pdf_processor_claude.py --input "$(IN)" --output "$(OUT)" --model claude-opus-4-6

install-gemini:  ## Install Gemini API dependencies
	@uv pip install -e ".[gemini]"

test-gemini:  ## Test single PDF with Gemini (usage: make test-gemini PDF=path/to/file.pdf)
	@if [ -z "$(PDF)" ]; then \
		echo "Usage: make test-gemini PDF=path/to/file.pdf"; \
		exit 1; \
	fi
	@$(PYTHON) test_single_gemini.py "$(PDF)"

process-gemini:  ## Process PDFs with Gemini Flash free tier (usage: make process-gemini IN=./pdfs OUT=./transcriptions)
	@if [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make process-gemini IN=./pdfs OUT=./transcriptions"; \
		exit 1; \
	fi
	@$(PYTHON) batch_pdf_processor_gemini.py --input "$(IN)" --output "$(OUT)"

process-gemini-pro:  ## Process PDFs with Gemini 1.5 Pro (most accurate)
	@if [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make process-gemini-pro IN=./pdfs OUT=./transcriptions"; \
		exit 1; \
	fi
	@$(PYTHON) batch_pdf_processor_gemini.py --input "$(IN)" --output "$(OUT)" --model gemini-1.5-pro --delay 0

install-local:  ## Install local model dependencies (PyMuPDF + openai)
	@uv pip install -e ".[local]"

list-models:  ## List models available in LlamaBarn
	@$(PYTHON) batch_pdf_processor_local.py --list-models

process-local:  ## Process with local LlamaBarn model (usage: make process-local MODEL=Qwen3-VL-2B IN=./pdfs OUT=./transcriptions)
	@if [ -z "$(MODEL)" ] || [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make process-local MODEL=Qwen3-VL-2B IN=./pdfs OUT=./transcriptions"; \
		exit 1; \
	fi
	@$(PYTHON) batch_pdf_processor_local.py --input "$(IN)" --output "$(OUT)" --model "$(MODEL)"

install-vision:  ## Install Vision OCR dependencies (macOS only: PyMuPDF + pyobjc)
	@uv pip install -e ".[vision]"

test-vision:  ## Test single PDF with Vision OCR (usage: make test-vision PDF=path/to/file.pdf)
	@if [ -z "$(PDF)" ]; then \
		echo "Usage: make test-vision PDF=path/to/file.pdf"; \
		exit 1; \
	fi
	@$(PYTHON) test_single_vision.py "$(PDF)"

process-vision:  ## Process PDFs with Vision OCR + Claude text API (usage: make process-vision IN=./pdfs OUT=./transcriptions)
	@if [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make process-vision IN=./pdfs OUT=./transcriptions"; \
		exit 1; \
	fi
	@$(PYTHON) batch_pdf_processor_vision.py --input "$(IN)" --output "$(OUT)"

estimate:  ## Estimate batch cost before running (usage: make estimate IN=./pdfs)
	@if [ -z "$(IN)" ]; then \
		echo "Usage: make estimate IN=./pdfs"; \
		exit 1; \
	fi
	@$(PYTHON) utils/estimate_batch_cost.py --input "$(IN)"

cost-check:  ## Check cost and token usage for a completed batch (usage: make cost-check BATCH=msgbatch_xxx)
	@if [ -z "$(BATCH)" ]; then \
		echo "Usage: make cost-check BATCH=msgbatch_xxx"; \
		exit 1; \
	fi
	@$(PYTHON) utils/check_batch_cost.py "$(BATCH)"

consolidate:  ## Consolidate themes (usage: make consolidate DIR=./transcriptions)
	@if [ -z "$(DIR)" ]; then \
		echo "Usage: make consolidate DIR=./transcriptions"; \
		exit 1; \
	fi
	@$(PYTHON) utils/consolidate_themes.py --input "$(DIR)" --report theme_analysis.md

consolidate-apply:  ## Consolidate and apply themes to files
	@if [ -z "$(DIR)" ]; then \
		echo "Usage: make consolidate-apply DIR=./transcriptions"; \
		exit 1; \
	fi
	@$(PYTHON) utils/consolidate_themes.py --input "$(DIR)" --report theme_analysis.md --apply

clean:  ## Remove virtual environment and cache files
	@echo "Cleaning up..."
	@rm -rf .venv
	@rm -rf __pycache__
	@rm -rf *.pyc
	@rm -rf .pytest_cache
	@rm -rf .ruff_cache
	@echo "✓ Clean complete"

.DEFAULT_GOAL := help
