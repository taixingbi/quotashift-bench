# Remote-state bootstrap for QuotaShift (X1-E). PROPOSED, NOT APPLIED. Applying creates one S3 bucket and is a separate,
# approval-gated owner step (X1-J prep). Uses LOCAL state itself (a chicken-and-egg bootstrap; keep its state file in the
# owner's encrypted backup, see docs/X1_AWS_DEPLOYMENT_READINESS.md).
terraform {
  required_version = ">= 1.10.0, < 2.0.0" # S3 native state locking (use_lockfile)
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0" # same exact pin as infra/terraform
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "QuotaShift", ManagedBy = "terraform", Purpose = "tfstate" }
  }
}
