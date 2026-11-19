locals {
  name = "${var.name_prefix}-${var.environment}"
  tags = {
    Project     = "mlsys-gpu-scheduling"
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
