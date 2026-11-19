locals {
  name = "${var.name_prefix}-${var.environment}"
  tags = {
    Project     = "QuotaShift"
    Owner       = var.owner
    Environment = var.environment
    CostCenter  = var.cost_center
    ManagedBy   = "terraform"
  }
  azs             = slice(data.aws_availability_zones.available.names, 0, var.az_count)
  private_compute = var.network_mode != "public_egress_only"
  gpu_ami_id      = var.gpu_ami_id != "" ? var.gpu_ami_id : nonsensitive(data.aws_ssm_parameter.ecs_gpu_ami[0].value)
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

data "aws_ssm_parameter" "ecs_gpu_ami" {
  count = var.gpu_ami_id == "" ? 1 : 0
  name  = var.gpu_ami_ssm_parameter
}

# Defense-in-depth assertions evaluated on every plan/apply (plan Phase 3 preflight).
check "no_public_gateway_or_model" {
  assert {
    condition     = var.gateway_image == "" ? true : aws_ecs_service.gateway[0].network_configuration[0].assign_public_ip == false
    error_message = "The gateway service must never be assigned a public IP."
  }
  assert {
    condition     = var.network_mode != "public_egress_only"
    error_message = "QuotaShift default is a private network (nat/endpoints); public_egress_only gives the GPU host a public egress IP and must be a deliberate, documented choice."
  }
}

check "cost_stop_conditions_set" {
  assert {
    condition     = var.max_run_minutes > 0 && var.spending_limit_usd > 0
    error_message = "max_run_minutes and spending_limit_usd must be set to positive values before any apply."
  }
}
