# live/bootstrap

One-time foundations: a Terraform state bucket, the GitHub OIDC provider, an OIDC smoke-test role and a monthly budget.
Applied by a human. Every other layer uses the state bucket created here.

## Accounts and credentials
| Profile | Account | What this layer creates there |
|---|---|---|
| `idp` | 736162637380 (workload) | state bucket, GitHub OIDC provider, OIDC smoke role |
| `idp-mgmt` | 324072340710 (organisation management) | organisation-wide monthly budget |

Terraform reads both `aws login` sessions directly (`allowed_account_ids` stops it from running against any other account).
Refresh expired sessions with `aws login --profile idp` / `aws login --profile idp-mgmt`.

## First apply (local state)
```bash
cd infra/terraform/live/bootstrap
cp terraform.tfvars.example terraform.tfvars                   # set budget_alert_email (git-ignored)
terraform init
terraform plan -out=bootstrap.tfplan
terraform apply bootstrap.tfplan
```
AWS sends a confirmation email for budget alerts. Accept it.

## Migrate state into the bucket
Add this to `main.tf` (bucket name from `terraform output state_bucket`), then run `terraform init -migrate-state`:
```hcl
backend "s3" {
  bucket       = "idp-tfstate-<account-id>-ap-southeast-2"
  key          = "live/bootstrap/terraform.tfstate"
  region       = "ap-southeast-2"
  use_lockfile = true
  encrypt      = true
}
```
Delete the local `terraform.tfstate*` files afterwards.
