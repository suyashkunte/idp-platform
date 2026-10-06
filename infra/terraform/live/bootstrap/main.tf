# live/bootstrap: one-time foundations for the IDP platform.
#   1. Terraform remote state bucket (S3 native locking, no DynamoDB table needed)
#   2. GitHub Actions OIDC identity provider (no static AWS keys anywhere)
#   3. A permission-less smoke-test role to prove OIDC works end to end
#   4. Organisation-wide monthly cost budget with email alerts (management account)
#
# Applied by a human from a laptop. State starts local and is then migrated into the bucket it creates (see README.md).

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  # Created by this layer, then migrated into (see README.md).
  backend "s3" {
    bucket       = "idp-tfstate-736162637380-ap-southeast-2"
    key          = "live/bootstrap/terraform.tfstate"
    region       = "ap-southeast-2"
    profile      = "idp"
    use_lockfile = true
    encrypt      = true
  }
}

# Default provider = workload account (state bucket, OIDC provider, roles).
provider "aws" {
  region              = var.region
  profile             = var.workload_profile
  allowed_account_ids = [var.workload_account_id]
  default_tags {
    tags = {
      project    = "idp-platform"
      layer      = "bootstrap"
      managed-by = "terraform"
    }
  }
}

# Management account: organisation-wide billing only.
provider "aws" {
  alias               = "mgmt"
  region              = var.region
  profile             = var.mgmt_profile
  allowed_account_ids = [var.mgmt_account_id]
  default_tags {
    tags = {
      project    = "idp-platform"
      layer      = "bootstrap"
      managed-by = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  state_bucket = "idp-tfstate-${local.account_id}-${var.region}"
  github_oidc  = "token.actions.githubusercontent.com"
}

# --- 1. Terraform state bucket ------------------------------------------------------------------------------------
resource "aws_s3_bucket" "tfstate" {
  bucket = local.state_bucket
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

data "aws_iam_policy_document" "tfstate_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.tfstate.arn,
      "${aws_s3_bucket.tfstate.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tfstate" {
  bucket     = aws_s3_bucket.tfstate.id
  policy     = data.aws_iam_policy_document.tfstate_tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.tfstate]
}

# --- 2. GitHub Actions OIDC provider ------------------------------------------------------------------------------
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://${local.github_oidc}"
  client_id_list = ["sts.amazonaws.com"]
}

# --- 3. OIDC smoke-test role (no permissions: sts:GetCallerIdentity needs none) -----------------------------------
data "aws_iam_policy_document" "oidc_smoke_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "${local.github_oidc}:sub"
      # GitHub immutable subject: names plus numeric IDs, so a deleted-and-recreated repo or renamed owner can't reuse the role.
      values = ["repo:${var.github_owner}@${var.github_owner_id}/${var.platform_repo}@${var.platform_repo_id}:*"]
    }
  }
}

resource "aws_iam_role" "oidc_smoke" {
  name                 = "idp-bootstrap-oidc-smoke"
  description          = "Proves GitHub Actions -> AWS OIDC works. Has no permissions."
  assume_role_policy   = data.aws_iam_policy_document.oidc_smoke_trust.json
  max_session_duration = 3600
}

# --- 4. Monthly budget (in the MANAGEMENT account: consolidated billing covers every account in the organisation) --
resource "aws_budgets_budget" "monthly" {
  provider     = aws.mgmt
  name         = "idp-monthly"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Track real usage before credits are applied, so alerts fire while credits are still being consumed.
  cost_types {
    include_credit = false
    include_refund = false
  }

  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.budget_alert_email]
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
