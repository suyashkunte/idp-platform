# Build profile python-uv: default Make targets (ADR-0012, IDP-18). Use: include $(IDP_PROFILE_DIR)/defaults.mk
# A target the tenant does not define (sbom, sca) runs idp-default-<target>; defining it yourself overrides the
# default without warnings. Caveats: listing sbom/sca in .PHONY without a recipe, or your own `%:` rule, bypasses the
# fallback. Reserved names: idp-default-*, _idp_*. No commands run at parse time.
# Include guard: a second include is a no-op (no duplicate rules, no override warnings).
ifndef _idp_python_uv_defaults
_idp_python_uv_defaults := 1
# Never pass the guard to sub-makes (a tenant's bare `export` would otherwise hide the defaults in `$(MAKE) sca`).
unexport _idp_python_uv_defaults
_idp_saved_goal := $(.DEFAULT_GOAL)
UV ?= uv
REPORTS_DIR ?= reports
# Tools are pinned (override the *_SPEC variables to upgrade) and run in uv's isolated tool environments. Both scan
# the project's locked dependencies, exported with hashes from uv.lock using --locked: the export fails if uv.lock is
# stale (out of date with pyproject.toml) and never writes uv.lock or the project environment. Network is needed only
# when the recipes run (tool download, vulnerability database).
# The SBOM describes what ships (runtime dependencies, --no-dev); SCA audits all groups, dev included, because dev
# tools run in CI.
IDP_CYCLONEDX_SPEC ?= cyclonedx-bom==7.5.0
IDP_PIP_AUDIT_SPEC ?= pip-audit==2.10.1
IDP_REQUIREMENTS ?= $(REPORTS_DIR)/requirements.locked.txt
IDP_EXPORT_CMD ?= $(UV) export --quiet --locked --all-packages --no-emit-project --no-emit-workspace --format requirements-txt --output-file $(IDP_REQUIREMENTS)
IDP_SBOM_REQUIREMENTS ?= $(REPORTS_DIR)/requirements.sbom.txt
IDP_SBOM_EXPORT_CMD ?= $(UV) export --quiet --locked --all-packages --no-dev --no-emit-project --no-emit-workspace --format requirements-txt --output-file $(IDP_SBOM_REQUIREMENTS)
IDP_SBOM_CMD ?= $(IDP_SBOM_EXPORT_CMD) && $(UV) tool run --from $(IDP_CYCLONEDX_SPEC) cyclonedx-py requirements --output-format JSON --output-file $(REPORTS_DIR)/sbom.cdx.json $(IDP_SBOM_REQUIREMENTS)
IDP_SCA_CMD ?= $(IDP_EXPORT_CMD) && $(UV) tool run --from $(IDP_PIP_AUDIT_SPEC) pip-audit --disable-pip --requirement $(IDP_REQUIREMENTS) --format json --output $(REPORTS_DIR)/sca.json

.PHONY: idp-default-sbom idp-default-sca
# An empty command fails (fail closed) instead of silently producing no evidence.
idp-default-sbom:
	$(if $(strip $(IDP_SBOM_CMD)),,$(error IDP_SBOM_CMD is empty: set it or define your own sbom target))
	@mkdir -p $(REPORTS_DIR)
	$(IDP_SBOM_CMD)
idp-default-sca:
	$(if $(strip $(IDP_SCA_CMD)),,$(error IDP_SCA_CMD is empty: set it or define your own sca target))
	@mkdir -p $(REPORTS_DIR)
	$(IDP_SCA_CMD)

# A target with no recipe of its own runs idp-default-<target> when that exists; tenant rules win without warnings.
%: idp-default-%
	@:

.DEFAULT_GOAL := $(_idp_saved_goal)
endif
