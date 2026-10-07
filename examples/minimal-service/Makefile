# IDP-19 conformance fixture (not a product, not a template): stdlib only, no uv project of its own.
# `make verify` = lint + test with the plain Python standard library; it needs no network and no uv.
# IDP_PROFILE_DIR defaults to the profile inside the platform checkout; `idp conformance` passes the resolved one.
PYTHON ?= python3
IDP ?= idp
IDP_PROFILE_DIR ?= ../../build-profiles/python-uv
include $(IDP_PROFILE_DIR)/defaults.mk

# sbom/sca are deliberately not listed here (IDP-18 caveat: .PHONY without a recipe bypasses the profile defaults).
.PHONY: verify lint test test-component spec-trace

verify: lint test

lint:
	$(PYTHON) -m compileall -q app.py tests

test:
	$(PYTHON) -m unittest discover -s tests -t .

test-component:
	@echo "test-component: no external dependencies; nothing to run"

spec-trace:
	$(IDP) spec-trace $(KEY)
