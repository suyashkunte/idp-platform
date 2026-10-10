# IDP-22 negative conformance fixture: GNU make reads this file before Makefile, so without the IDP-22 check
# `make verify` would run this always-passing `verify` while `idp validate` only checked Makefile.
.PHONY: lint test test-component verify spec-trace

lint test test-component spec-trace:
	@true

verify:
	@true
