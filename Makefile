# ─────────────────────────────────────────────────────────────────────────────
# Bundesliga Wrapped — Makefile
# ─────────────────────────────────────────────────────────────────────────────
# Usage:
#   make setup       Create virtualenv and install Python dependencies
#   make sso-login   Authenticate with AWS SSO (run once per session)
#   make validate    Smoke-test AWS credentials
#   make test        Run the test suite
#   make run-demo    Dry-run the slide assembler pipeline
#   make clean       Remove generated artefacts
# ─────────────────────────────────────────────────────────────────────────────

PYTHON      := py
VENV        := venv
VENV_PYTHON := $(VENV)/Scripts/python   # Windows path; Linux/macOS: venv/bin/python
PIP         := $(VENV_PYTHON) -m pip
PYTEST      := $(VENV_PYTHON) -m pytest
REQUIREMENTS := backend/requirements.txt

.PHONY: setup sso-login validate test run-demo clean help

## Create a virtual environment and install all Python dependencies.
setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(REQUIREMENTS)
	@echo ""
	@echo "Setup complete. Activate the venv with:"
	@echo "  Windows:      $(VENV)\\Scripts\\activate"
	@echo "  Linux/macOS:  source $(VENV)/bin/activate"

## Authenticate with AWS SSO. Run this once per terminal session.
sso-login:
	aws sso login --profile hackathon

## Validate that S3 has the required data for all 18 Bundesliga clubs.
validate:
	$(VENV_PYTHON) -m backend.pipeline.automation --clubs all --validate-only

## Run the full pipeline in dry-run mode for Bayern + 3 mock users.
run-demo:
	$(VENV_PYTHON) -m backend.pipeline.automation --clubs DFL-CLU-00000G --users demo-user-001,demo-user-002,demo-user-003 --dry-run --tone fan

## Run the full test suite with verbose output.
test:
	$(PYTEST) backend/pipeline/test_personalization.py -v

## Dry-run the slide assembler for a single user (quick check).
run-single:
	$(VENV_PYTHON) -m backend.pipeline.slide_assembler --dry-run --tone commentator

## Remove generated artefacts: raw data cache, Python bytecode, output files.
clean:
	@if exist data\raw rmdir /s /q data\raw
	@if exist output rmdir /s /q output
	@for /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
	@echo "Clean complete."

## Show this help message.
help:
	@echo "Available targets:"
	@echo "  setup      Create venv + install dependencies"
	@echo "  sso-login  AWS SSO authentication"
	@echo "  validate   Smoke-test AWS credentials"
	@echo "  test       Run pytest suite"
	@echo "  run-demo   Dry-run slide assembler"
	@echo "  clean      Remove generated artefacts"
