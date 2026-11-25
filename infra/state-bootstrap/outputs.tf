output "state_bucket" {
  value = aws_s3_bucket.state.bucket
}

output "backend_hcl" {
  description = "Paste into infra/terraform/backend.hcl (gitignored)."
  value       = <<-EOT
    bucket       = "${aws_s3_bucket.state.bucket}"
    key          = "quotashift/research/terraform.tfstate"
    region       = "${var.region}"
    encrypt      = true
    use_lockfile = true
  EOT
}
