# IDP-19 negative conformance fixture (missing required target). Defines every required Make contract target
# except `verify`; idp.yaml beside it is valid, so the missing target is the only defect.
IDP ?= idp
IDP_PROFILE_DIR ?= ../../../../build-profiles/python-uv
include $(IDP_PROFILE_DIR)/defaults.mk

.PHONY: lint test test-component spec-trace

lint:
	@echo "lint: ok"

test:
	@echo "test: ok"

test-component:
	@echo "test-component: no external dependencies; nothing to run"

spec-trace:
	$(IDP) spec-trace $(KEY)
