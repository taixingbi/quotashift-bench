# Offline: mock provider, no AWS calls.
mock_provider "aws" {}

variables {
  bucket_suffix = "a1b2c3d4"
}

run "state_bucket_is_versioned_encrypted_private_and_protected" {
  command = plan
  assert {
    condition     = aws_s3_bucket.state.bucket == "quotashift-tfstate-a1b2c3d4"
    error_message = "Bucket must match the IAM scope quotashift-tfstate-*."
  }
  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled"
    error_message = "Versioning is required for state recovery."
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "State must be encrypted at rest."
  }
  assert {
    condition = alltrue([aws_s3_bucket_public_access_block.state.block_public_acls, aws_s3_bucket_public_access_block.state.block_public_policy,
    aws_s3_bucket_public_access_block.state.ignore_public_acls, aws_s3_bucket_public_access_block.state.restrict_public_buckets])
    error_message = "State bucket must block all public access."
  }
  assert {
    condition     = strcontains(output.backend_hcl, "use_lockfile = true")
    error_message = "S3 native locking must be on."
  }
}

run "account_id_like_suffix_rejected" {
  command = plan
  variables {
    bucket_suffix = "Bad_Suffix!"
  }
  expect_failures = [var.bucket_suffix]
}
