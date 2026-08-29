output "ecr_repository_url" {
  value = aws_ecr_repository.watcher.repository_url
}

output "state_bucket_name" {
  value = aws_s3_bucket.state.bucket
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}

output "aws_account_id" {
  value = data.aws_caller_identity.current.account_id
}
