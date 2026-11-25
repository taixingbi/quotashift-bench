# ---------------------------------------------------------------- S3 raw results (+ optional staged models)
resource "aws_s3_bucket" "results" {
  bucket = "${local.name}-results-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_ownership_controls" "results" {
  bucket = aws_s3_bucket.results.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "results" {
  bucket                  = aws_s3_bucket.results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "results" {
  bucket = aws_s3_bucket.results.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3: no per-request KMS charges
    }
  }
}

resource "aws_s3_bucket_versioning" "results" {
  bucket = aws_s3_bucket.results.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "results" {
  bucket = aws_s3_bucket.results.id
  rule {
    id     = "abort-mpu-and-noncurrent"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
  rule {
    id     = "expire-staged-models"
    status = "Enabled"
    filter {
      prefix = "models/"
    }
    expiration {
      days = 30
    }
  }
  dynamic "rule" {
    for_each = var.results_expiration_days > 0 ? [1] : []
    content {
      id     = "expire-results"
      status = "Enabled"
      filter {
        prefix = "results/"
      }
      expiration {
        days = var.results_expiration_days
      }
    }
  }
}

resource "aws_s3_bucket_policy" "results_tls_only" {
  bucket = aws_s3_bucket.results.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.results.arn, "${aws_s3_bucket.results.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.results]
}

# ---------------------------------------------------------------- ECR (runner image; immutable digests)
resource "aws_ecr_repository" "runner" {
  name                 = "${local.name}-runner"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "runner" {
  repository = aws_ecr_repository.runner.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 20 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
      action       = { type = "expire" }
    }]
  })
}

# Gateway image (separate repo so the gateway and the load generators version independently).
resource "aws_ecr_repository" "gateway" {
  name                 = "${local.name}-gateway"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "gateway" {
  repository = aws_ecr_repository.gateway.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 20 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
      action       = { type = "expire" }
    }]
  })
}

# ---------------------------------------------------------------- logs (bounded retention)
resource "aws_cloudwatch_log_group" "vllm" {
  name              = "/${var.name_prefix}/${var.environment}/vllm"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "runner" {
  name              = "/${var.name_prefix}/${var.environment}/runner"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/${var.name_prefix}/${var.environment}/gateway"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "host_telemetry" {
  name              = "/${var.name_prefix}/${var.environment}/x1-host-telemetry"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "dcgm" {
  name              = "/${var.name_prefix}/${var.environment}/dcgm"
  retention_in_days = var.log_retention_days
}

# ---------------------------------------------------------------- budget alert (alerts only; not a hard stop)
resource "aws_budgets_budget" "monthly" {
  count        = length(var.budget_alert_emails) > 0 ? 1 : 0
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Project$QuotaShift"]
  }

  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.budget_alert_emails
    }
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.budget_alert_emails
  }
}
