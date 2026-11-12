# Everyday commands. `make help` lists them.
LJMU_DIR ?= data/ljmu
LANDMARKS ?= $(LJMU_DIR)/landmarks

.PHONY: help test lint format typecheck check contract evaluate fetch-ljmu

help:
	@echo "make test       run the test suite (SQLite)"
	@echo "make lint       ruff lint and format check"
	@echo "make format     apply ruff fixes and formatting"
	@echo "make typecheck  mypy"
	@echo "make check      lint, typecheck and tests: what CI and pre-commit run"
	@echo "make contract   regenerate contracts/openapi.json after an API change"
	@echo "make fetch-ljmu download the LJMU side-view videos to \$$LJMU_DIR/videos"
	@echo "make evaluate   accuracy check on LJMU -> evaluation/results/"

test:
	ENV=dev uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff check --fix . && uv run ruff format .

typecheck:
	uv run mypy

check: lint typecheck test

contract:
	ENV=dev uv run python tests/test_contract.py --write

# Accuracy check on LJMU (Plan V3 Phase 3). Videos and landmarks stay outside git (data/ljmu/).
fetch-ljmu:
	uv run --with remotezip --with zipfile-deflate64 python -m evaluation.fetch_ljmu $(LJMU_DIR)/videos

evaluate:
	uv run python -m evaluation.evaluate --landmarks $(LANDMARKS) --videos $(LJMU_DIR)/videos
