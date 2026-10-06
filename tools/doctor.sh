#!/usr/bin/env bash
# tools/doctor.sh: verify the local toolchain and connectivity for idp-platform (iteration 0).
# Read-only: it never changes anything. Exit code = number of failed checks.
set -u
REGION="${AWS_REGION:-ap-southeast-2}"
fail=0
ok()   { printf '  \033[32m✅\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m❌\033[0m %s — %s\n' "$1" "$2"; fail=$((fail+1)); }
need() { # name, command, hint
  if out=$(eval "$2" 2>/dev/null) && [ -n "$out" ]; then ok "$1: $(echo "$out" | head -1)"; else bad "$1" "$3"; fi
}

echo "Toolchain"
need "arch"        "[ \"\$(uname -m)\" = arm64 ] && echo arm64"                        "expected Apple Silicon"
need "brew"        "brew --version"                                                    "setup step 1"
need "aws cli v2"  "aws --version 2>&1 | grep -E '^aws-cli/2'"                     "brew install awscli (setup steps 2-3)"
need "gh"          "gh --version"                                                      "brew install gh"
need "uv"          "uv --version"                                                      "brew install uv"
need "python3.12"  "uv python find 3.12"                                               "uv python install 3.12"
need "terraform"   "terraform version"                                                 "brew install hashicorp/tap/terraform"
need "kubectl"     "kubectl version --client 2>/dev/null | head -1"                    "brew install kubectl"
need "helm"        "helm version --short"                                              "brew install helm"
need "helmfile"    "helmfile --version"                                                "brew install helmfile"
need "docker"      "docker info --format '{{.ServerVersion}}'"                         "colima start (or Docker Desktop)"
need "buildx"      "docker buildx version"                                             "link docker-buildx plugin (step 3)"
need "cosign"      "cosign version 2>&1 | grep -i gitversion"                          "brew install cosign"
need "syft"        "syft version 2>/dev/null | grep -i '^version'"                     "brew install syft"
need "trivy"       "trivy --version | head -1"                                         "brew install trivy"
need "pre-commit"  "pre-commit --version"                                              "brew install pre-commit"
need "jq"          "jq --version"                                                      "brew install jq"

echo "Connectivity"
need "git identity" "git config --global user.email"                                   "setup step 5"
need "GitHub auth"  "gh auth status 2>&1 | grep -i 'logged in to'"                     "gh auth login"
need "GitHub workflow scope" "gh auth status 2>&1 | grep -i 'scopes:.*workflow'"                  "gh auth refresh -s workflow"
need "AWS identity" "aws sts get-caller-identity --query Arn --output text"            "aws sso login --profile idp (step 4)"
need "AWS region"   "[ \"\$(aws configure get region)\" = \"$REGION\" ] && echo $REGION" "set region $REGION in profile"
need "EKS API"      "aws eks list-clusters --region $REGION --output text >/dev/null && echo reachable" "free-plan restriction? see step 4.4"
need "root not in use" "aws sts get-caller-identity --query Arn --output text | grep -v ':root'" "use Identity Center/IAM user, not root"
need ".mcp.json"    "[ -f .mcp.json ] && jq -r '.mcpServers|keys|join(\",\")' .mcp.json" "run from repo root"

echo
if [ "$fail" -eq 0 ]; then echo "All checks passed."; else echo "$fail check(s) failed."; fi
exit "$fail"
