# Everyday commands. `make help` lists them.
LJMU_DIR ?= data/ljmu
LANDMARKS ?= $(LJMU_DIR)/landmarks

.PHONY: help test lint format typecheck check contract evaluate fetch-ljmu fetch-ljmu-imu leg-labels kinematics references

help:
	@echo "make test       run the test suite (SQLite)"
	@echo "make lint       ruff lint and format check"
	@echo "make format     apply ruff fixes and formatting"
	@echo "make typecheck  mypy"
	@echo "make check      lint, typecheck and tests: what CI and pre-commit run"
	@echo "make contract   regenerate contracts/openapi.json after an API change"
	@echo "make fetch-ljmu download the LJMU side-view videos to \$$LJMU_DIR/videos"
	@echo "make evaluate   accuracy check on LJMU -> evaluation/results/"
	@echo "make leg-labels left/right check against the LJMU thigh sensor (make fetch-ljmu-imu first)"
	@echo "make kinematics label-free knee/hip measures on LJMU -> evaluation/results/kinematics.json"
	@echo "make references same-method references and the release gate -> gaitcore/norms/ljmu_references.json"

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

fetch-ljmu-imu:
	uv run --with remotezip --with zipfile-deflate64 python -m evaluation.fetch_ljmu --imu $(LJMU_DIR)/imu

leg-labels:
	ENV=dev uv run python -m evaluation.leg_labels --landmarks $(LANDMARKS) --sensor $(LJMU_DIR)/imu

kinematics:
	ENV=dev uv run python -m evaluation.kinematics --landmarks $(LANDMARKS) --sensor $(LJMU_DIR)/imu

references:
	ENV=dev uv run --with openpyxl python -m evaluation.references --landmarks $(LANDMARKS) --meta $(LJMU_DIR)/Participant_Anthropometry.xlsx
