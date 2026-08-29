resource "aws_cloudwatch_log_group" "watcher" {
  name              = "/aws/lambda/${var.project_name}"
  retention_in_days = 30
}

resource "aws_lambda_function" "watcher" {
  function_name = var.project_name
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.watcher.repository_url}:latest"
  timeout       = 60
  memory_size   = 2048

  ephemeral_storage {
    size = 1024
  }

  environment {
    variables = {
      STATE_BACKEND             = "s3"
      STATE_BUCKET               = aws_s3_bucket.state.bucket
      STATE_KEY                  = "state.json"
      DISCORD_WEBHOOK_SSM_PARAM  = aws_ssm_parameter.discord_webhook_url.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.watcher]
}

resource "aws_iam_role" "scheduler_invoke" {
  name = "${var.project_name}-scheduler-invoke"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "scheduler_invoke" {
  name = "${var.project_name}-scheduler-invoke"
  role = aws_iam_role.scheduler_invoke.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.watcher.arn
    }]
  })
}

resource "aws_scheduler_schedule" "watcher" {
  name       = "${var.project_name}-schedule"
  group_name = "default"
  # Enabled in Task 8, at the same time the old GitHub Actions cron
  # trigger was removed, so the two triggers never ran in parallel and
  # never double-notified Discord for the same opening.
  state = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(${var.schedule_rate_minutes} minutes)"

  target {
    arn      = aws_lambda_function.watcher.arn
    role_arn = aws_iam_role.scheduler_invoke.arn
  }
}
