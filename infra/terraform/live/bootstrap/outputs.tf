output "state_bucket" {
  description = "S3 bucket for all other Terraform layers' state."
  value       = aws_s3_bucket.tfstate.bucket
}

output "github_oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.github.arn
}

output "oidc_smoke_role_arn" {
  description = "Set as repo variable AWS_OIDC_SMOKE_ROLE_ARN for the smoke workflow."
  value       = aws_iam_role.oidc_smoke.arn
}
