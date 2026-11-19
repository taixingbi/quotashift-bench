terraform {
  required_version = ">= 1.10.0, < 2.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0" # exact pin; lock file records hashes
    }
  }
  # Partial S3 backend with native lockfile locking (Terraform >= 1.10).
  # Supply settings at init time:  terraform init -backend-config=backend.hcl
  # (backend.hcl is gitignored; see backend.hcl.example). For offline validation use -backend=false.
  backend "s3" {}
}

provider "aws" {
  region = var.region
  default_tags {
    tags = local.tags
  }
}
