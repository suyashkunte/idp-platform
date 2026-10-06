variable "region" {
  description = "Home region for the platform."
  type        = string
  default     = "ap-southeast-2"
}

variable "github_owner" {
  description = "GitHub user or organisation that owns the platform repo."
  type        = string
  default     = "suyashkunte"
}

variable "platform_repo" {
  description = "Name of the platform repository (OIDC smoke role is scoped to it)."
  type        = string
  default     = "idp-platform"
}

variable "github_owner_id" {
  description = "Numeric GitHub owner ID (immutable OIDC subject). gh api users/<owner> --jq .id"
  type        = string
  default     = "9319802"
}

variable "platform_repo_id" {
  description = "Numeric GitHub repo ID (immutable OIDC subject). gh api repos/<owner>/<repo> --jq .id"
  type        = string
  default     = "1407798795"
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget (USD, before credits)."
  type        = string
  default     = "25"
}

variable "budget_alert_email" {
  description = "Email address that receives budget alerts. Set in terraform.tfvars (git-ignored)."
  type        = string
}

variable "workload_profile" {
  description = "AWS CLI profile for the workload account (aws login --profile idp)."
  type        = string
  default     = "idp"
}

variable "workload_account_id" {
  description = "Guard rail: Terraform refuses to run against any other account."
  type        = string
  default     = "736162637380"
}

variable "mgmt_profile" {
  description = "AWS CLI profile for the organisation management account (aws login --profile idp-mgmt)."
  type        = string
  default     = "idp-mgmt"
}

variable "mgmt_account_id" {
  type    = string
  default = "324072340710"
}
