variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-northeast-1"
}

variable "project_name" {
  description = "Prefix used for naming all resources"
  type        = string
  default     = "meguro-tennis-watcher"
}

variable "github_repo" {
  description = "GitHub repo allowed to assume the deploy role, as owner/repo"
  type        = string
  default     = "i-cezuki/tennis-booking"
}

variable "discord_webhook_url" {
  description = "Discord webhook URL, stored in SSM as SecureString. Set via TF_VAR_discord_webhook_url env var, never commit it."
  type        = string
  sensitive   = true
}

variable "schedule_rate_minutes" {
  description = "How often EventBridge Scheduler invokes the watcher Lambda"
  type        = number
  default     = 5
}
