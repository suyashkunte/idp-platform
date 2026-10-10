# IDP-22 negative conformance fixture (GNUmakefile bypass). This Makefile defines every required Make contract
# target, so on its own it passes `idp validate`; its `verify` fails on purpose. A plain `make verify` here would
# read the GNUmakefile instead and pass, which is the bypass `idp validate` must reject.
.PHONY: lint test test-component verify spec-trace

lint:
	@echo "lint: ok"

test:
	@echo "test: ok"

test-component:
	@echo "test-component: no external dependencies; nothing to run"

verify:
	@echo "Makefile verify must not pass"; exit 1

spec-trace:
	@echo "spec-trace: ok"
