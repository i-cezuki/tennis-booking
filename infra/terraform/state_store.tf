resource "aws_s3_bucket" "state" {
  bucket = "${var.project_name}-state-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_ssm_parameter" "discord_webhook_url" {
  name  = "/${var.project_name}/discord_webhook_url"
  type  = "SecureString"
  value = var.discord_webhook_url
}
