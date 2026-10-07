# Build profile python-uv: default Make targets (ADR-0012, IDP-18). Use: include $(IDP_PROFILE_DIR)/defaults.mk
# A target the tenant does not define (sbom, sca) runs idp-default-<target>; defining it yourself overrides the
# default without warnings. Caveats: listing sbom/sca in .PHONY without a recipe, or your own `%:` rule, bypasses the
# fallback. Reserved names: idp-default-*, _idp_saved_goal. No commands run at parse time.
_idp_saved_goal := $(.DEFAULT_GOAL)
UV ?= uv
REPORTS_DIR ?= reports
IDP_SBOM_CMD ?= $(UV) run --with cyclonedx-bom cyclonedx-py environment --output-format JSON --output-file $(REPORTS_DIR)/sbom.cdx.json
IDP_SCA_CMD ?= $(UV) run --with pip-audit pip-audit --format json --output $(REPORTS_DIR)/sca.json

.PHONY: idp-default-sbom idp-default-sca
idp-default-sbom:
	@mkdir -p $(REPORTS_DIR)
	$(IDP_SBOM_CMD)
idp-default-sca:
	@mkdir -p $(REPORTS_DIR)
	$(IDP_SCA_CMD)

# A target with no recipe of its own runs idp-default-<target> when that exists; tenant rules win without warnings.
%: idp-default-%
	@:

.DEFAULT_GOAL := $(_idp_saved_goal)
