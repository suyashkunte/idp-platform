# IDP-19 negative conformance fixture (unknown field in idp.yaml). This Makefile is complete: it defines every
# required Make contract target, so the only defect is `spec.bogusField` in idp.yaml.
IDP ?= idp
IDP_PROFILE_DIR ?= ../../../../build-profiles/python-uv
include $(IDP_PROFILE_DIR)/defaults.mk

.PHONY: verify lint test test-component spec-trace

verify: lint test

lint:
	@echo "lint: ok"

test:
	@echo "test: ok"

test-component:
	@echo "test-component: no external dependencies; nothing to run"

spec-trace:
	$(IDP) spec-trace $(KEY)
