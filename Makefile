# Make contract (docs/platform/service-contract.md, I2). Humans, agents, hooks and CI call only these targets.
.DEFAULT_GOAL := help
SHELL := /bin/bash
UV ?= uv
REPORTS_DIR ?= reports
COV_MIN ?= 85

.PHONY: help setup lint fmt format test verify verify-fast spec-trace approve-spec validate-plugin clean

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python 3.12, workspace packages and git hooks
	$(UV) sync --all-packages
	$(UV) run pre-commit install

lint: ## ruff (lint + format check) and mypy strict
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy

fmt: ## Format the whole repo
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

format: ## Format only FILES="a.py b.py" (used by the agent's PostToolUse hook)
	@py=$$(printf '%s\n' $(FILES) | grep -E '\.py$$' || true); \
	if [ -n "$$py" ]; then $(UV) run ruff check --fix --quiet $$py; $(UV) run ruff format --quiet $$py; fi

test: ## Unit tests with coverage; JUnit + Cobertura into $(REPORTS_DIR)/
	@mkdir -p $(REPORTS_DIR)
	$(UV) run pytest --cov --cov-report=xml:$(REPORTS_DIR)/coverage.xml --cov-report=term \
	  --cov-fail-under=$(COV_MIN) --junitxml=$(REPORTS_DIR)/junit-unit.xml

verify-fast: lint test ## Quick local gate (agent Stop hook)

verify: verify-fast validate-plugin ## Everything a PR must pass locally
	$(UV) run bandit -q -c pyproject.toml -r packages
	@if git rev-parse --verify -q origin/main >/dev/null; then \
	  $(UV) run diff-cover $(REPORTS_DIR)/coverage.xml --compare-branch=origin/main --fail-under=80; fi
	@changed=$$(git diff --name-only origin/main... 2>/dev/null | grep -E '(^|/)test_[^/]*\.py$$' || true); \
	if [ -n "$$changed" ]; then $(UV) run idp test-quality-lint $$changed; fi
	@key=$$(git branch --show-current | sed -nE 's#^feature/([A-Z]+-[0-9]+).*#\1#p'); \
	if [ -n "$$key" ] && [ -f specs/$$key/spec.md ]; then $(UV) run idp spec-trace $$key; fi

validate-plugin: ## Structural checks for the idp-agentic plugin and marketplace
	$(UV) run pytest -q tests/plugin --no-cov -p no:cacheprovider

spec-trace: ## make spec-trace KEY=IDP-12
	$(UV) run idp spec-trace $(KEY)

approve-spec: ## HUMANS ONLY: make approve-spec KEY=IDP-12 (refused inside agent sessions)
	$(UV) run idp approve-spec $(KEY)

clean:
	rm -rf $(REPORTS_DIR) .pytest_cache .mypy_cache .ruff_cache .coverage
