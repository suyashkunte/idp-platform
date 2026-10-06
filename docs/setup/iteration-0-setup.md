# Iteration 0: local setup and connectivity (macOS, Apple Silicon)

Do the steps in order. After each step, run `./tools/doctor.sh` from the repo root (or ask Claude to run it). It prints ✅/❌ per item.
Commands marked **(you)** need your password, a browser login or the AWS console, so Claude can't run them for you.

---

## Step 1: Homebrew (you)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
brew --version
```

## Step 2: Remove the broken x86 AWS CLI (you, needs sudo)
The current `/usr/local/bin/aws` is an Intel binary that this Mac can't run.
```bash
sudo rm -f /usr/local/bin/aws /usr/local/bin/aws_completer
sudo rm -rf /usr/local/aws-cli
```

## Step 3: Toolchain
```bash
brew install awscli gh uv jq git pre-commit kubectl helm helmfile cosign syft trivy colima docker docker-buildx
brew tap hashicorp/tap && brew install hashicorp/tap/terraform
# docker buildx plugin + a lightweight container runtime (instead of Docker Desktop)
mkdir -p ~/.docker/cli-plugins && ln -sfn "$(brew --prefix)/opt/docker-buildx/bin/docker-buildx" ~/.docker/cli-plugins/docker-buildx
colima start --cpu 4 --memory 8 --disk 60     # re-run after a reboot (or: brew services start colima)
# Python 3.12, managed by uv (leaves the system Python 3.9 untouched)
uv python install 3.12
# Optional but recommended: Claude Code CLI (headless runs, `claude mcp ...`)
curl -fsSL https://claude.ai/install.sh | bash
```
Why Colima: it is free and scriptable. Docker Desktop works too if you prefer it; then skip the `colima` and `docker*` lines.

## Step 4: AWS access (you)
Goal: never use the root user day to day; use short-lived credentials on the CLI.

> **What worked for this project (2026-10-06):** the account uses AWS's newer sign-in experience, with no root login and no Identity
> Center access. The console sign-in is a role session (`AccountFullAccessRole`). The CLI reuses it with short-lived credentials:
> ```bash
> aws login --profile idp --region ap-southeast-2     # browser sign-in; re-run when the session expires
> aws configure set region ap-southeast-2 --profile idp
> echo 'export AWS_PROFILE=idp' >> ~/.zprofile
> ```
> Use 4.1–4.2 below only on accounts that have a root user / Identity Center.

4.1 **Secure root.** Console → top-right account menu → *Security credentials* → assign an **MFA device** to root.

4.2 **Create your admin identity: IAM Identity Center (recommended).**
1. Console → region **ap-southeast-2** → *IAM Identity Center* → **Enable** (this creates an AWS Organization, which is free).
2. *Users* → **Add user** `suyash` (your email) → finish the email invite and set up MFA.
3. *Permission sets* → **Create** → predefined `AdministratorAccess`, session 8 h.
4. *AWS accounts* → select your account → **Assign users** → `suyash` + `AdministratorAccess`.
5. Copy the **AWS access portal URL** (looks like `https://d-xxxxxxxxxx.awsapps.com/start`).

Then on the Mac:
```bash
aws configure sso --profile idp
#   SSO session name: idp
#   SSO start URL:   <access portal URL>
#   SSO region:      ap-southeast-2
#   scopes:          (press Enter)
#   → browser opens, approve → pick the account + AdministratorAccess
#   CLI default region: ap-southeast-2 ; output: json
echo 'export AWS_PROFILE=idp' >> ~/.zprofile && export AWS_PROFILE=idp
aws sts get-caller-identity
```
Daily: `aws sso login --profile idp`.

> **Fallback** if Identity Center is unavailable on the Free plan: create an IAM user `suyash-admin` with `AdministratorAccess` + MFA,
> create an access key, and run `aws configure --profile idp`. We will move to SSO later. (GitHub Actions never uses keys; it uses OIDC.)

4.3 **Billing guardrails.** Console → *Billing* → *Budgets*: Claude will create the $25 budget with Terraform in iteration 0b. Now,
only enable *Billing preferences → Receive Free Tier usage alerts* and confirm your email.

4.4 **Check EKS access on the Free plan.**
```bash
aws eks list-clusters --region ap-southeast-2        # expect: {"clusters": []}
aws ec2 describe-instance-types --instance-types t3.large --region ap-southeast-2 --query 'InstanceTypes[0].InstanceType'
```
If either returns an error mentioning your plan or subscription, upgrade: *Billing → Account plan → Upgrade to paid plan*. Credits carry
over; check the Billing console for current terms.

## Step 5: Git and GitHub (you)
```bash
git config --global user.name  "Suyash Kunte"
git config --global user.email "<your GitHub email>"
git config --global init.defaultBranch main
gh auth login            # GitHub.com → HTTPS → authenticate Git: Yes → login with browser
gh auth refresh -s workflow,delete_repo   # 'workflow' lets us push .github/workflows/*
gh auth status
```
Claude then creates the public repo `idp-platform` and pushes (asks you first).

## Step 6: Jira connectivity via MCP (you)
The repo ships `.mcp.json` with the **Atlassian Rovo MCP server** (OAuth, no tokens stored in Git).
1. Reload the VS Code window (`Cmd+Shift+P` → *Developer: Reload Window*) so Claude Code picks up `.mcp.json`; approve the
   project MCP server when prompted.
2. In the Claude Code panel type `/mcp` → select **atlassian** → **Authenticate** → the browser opens → log in to
   `suyashkunte.atlassian.net` → **Accept**.
3. Ask Claude: *"list the issues in Jira project IDP"*. A result means connectivity works.

If the panel reports a transport error, switch the URL in `.mcp.json` to `https://mcp.atlassian.com/v1/sse` with `"type": "sse"`.

**Jira API token (needed later for pipeline-created Gate Hold tickets, iteration 3):**
https://id.atlassian.com/manage-profile/security/api-tokens → *Create API token* → name `idp-github-actions`. Keep it in your password
manager; we will add it as a GitHub Actions secret, never to the repo.

## Step 7: Jira project shape (you, about 10 min; Claude can do parts via MCP afterwards)
In project **IDP** → *Project settings*:
- **Issue types:** keep Epic / Story / Task / Bug; **add** `Gate Hold`.
- **Fields:** add a dropdown **Found in phase** (DEV, G0, G1, G2, G3, G5, PROD) to Bug, and a dropdown **Severity** (P0–P3) to Bug and Gate Hold.
- **Workflow / board columns:** To Do → Ready → In Progress → In Review → Done.
- Labels need no setup; Claude adds them when creating tickets.

## Done when
`./tools/doctor.sh` is all ✅, and Claude can read a IDP issue. Next: **iteration 0b** (Claude): Terraform bootstrap (state bucket,
lock table, GitHub OIDC provider, $25 budget), first commit, GitHub repo creation, and an OIDC smoke-test workflow.
