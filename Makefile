# Accuracy check on LJMU (Plan V3 Phase 3). Videos and landmarks stay outside git (data/ljmu/).
LJMU_DIR ?= data/ljmu

.PHONY: evaluate fetch-ljmu

fetch-ljmu:
	uv run --with remotezip --with zipfile-deflate64 python -m evaluation.fetch_ljmu $(LJMU_DIR)/videos

LANDMARKS ?= $(LJMU_DIR)/landmarks

evaluate:
	uv run python -m evaluation.evaluate --landmarks $(LANDMARKS) --videos $(LJMU_DIR)/videos
