resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = local.name }
}

# Lock down the default security group (no rules).
resource "aws_default_security_group" "default" {
  vpc_id = aws_vpc.this.id
}

resource "aws_subnet" "public" {
  count                   = var.az_count
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = var.network_mode == "public_egress_only"
  tags                    = { Name = "${local.name}-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = local.private_compute ? var.az_count : 0
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 100 + count.index)
  availability_zone = local.azs[count.index]
  tags              = { Name = "${local.name}-private-${count.index}" }
}

resource "aws_internet_gateway" "this" {
  count  = var.network_mode == "endpoints" ? 0 : 1
  vpc_id = aws_vpc.this.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
}

resource "aws_route" "public_inet" {
  count                  = var.network_mode == "endpoints" ? 0 : 1
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this[0].id
}

resource "aws_route_table_association" "public" {
  count          = var.az_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count  = var.network_mode == "nat" ? 1 : 0
  domain = "vpc"
}

resource "aws_nat_gateway" "this" {
  count         = var.network_mode == "nat" ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id
}

resource "aws_route_table" "private" {
  count  = local.private_compute ? 1 : 0
  vpc_id = aws_vpc.this.id
}

resource "aws_route" "private_nat" {
  count                  = var.network_mode == "nat" ? 1 : 0
  route_table_id         = aws_route_table.private[0].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

resource "aws_route_table_association" "private" {
  count          = local.private_compute ? var.az_count : 0
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[0].id
}

# Free S3 gateway endpoint (results upload, optional model staging) in every mode.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = concat([aws_route_table.public.id], aws_route_table.private[*].id)
}

# Interface endpoints only in "endpoints" mode (each costs per hour per AZ).
locals {
  interface_endpoints = var.network_mode == "endpoints" ? toset([
    "ecr.api", "ecr.dkr", "logs", "ecs", "ecs-agent", "ecs-telemetry", "ssm", "ssmmessages", "ec2messages", "sts"
  ]) : toset([])
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = local.interface_endpoints
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${var.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.endpoints[0].id]
}

# ---------------------------------------------------------------- security groups
# No security group in this module allows ingress from 0.0.0.0/0 or ::/0 (enforced by tests/plan_mock.tftest.hcl).

# Load generators (benign-runner / scenario-runner): no ingress; egress to the gateway only.
resource "aws_security_group" "runner" {
  name_prefix = "${local.name}-runner-"
  description = "Load generators: no ingress; talk to the gateway, not vLLM"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_egress_rule" "runner_all" {
  security_group_id = aws_security_group.runner.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "egress for image pulls, S3, and the internal gateway"
}

# Gateway (Fargate): ingress only from the load generators on 8080; no public listener.
resource "aws_security_group" "gateway" {
  name_prefix = "${local.name}-gateway-"
  description = "Internal tenant gateway: ingress from load generators only; egress to vLLM"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_ingress_rule" "gateway_from_generators" {
  security_group_id            = aws_security_group.gateway.id
  referenced_security_group_id = aws_security_group.runner.id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  description                  = "gateway chat API from load generators only"
}

resource "aws_vpc_security_group_egress_rule" "gateway_all" {
  security_group_id = aws_security_group.gateway.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "egress for image pulls, S3, and the private vLLM backend"
}

resource "aws_security_group" "gpu_host" {
  name_prefix = "${local.name}-gpuhost-"
  description = "GPU container instance (vLLM + DCGM in host networking): ingress only from gateway/generators; no SSH"
  vpc_id      = aws_vpc.this.id
}

# Only the gateway reaches vLLM. Generators never talk to the model directly.
resource "aws_vpc_security_group_ingress_rule" "vllm_from_gateway" {
  security_group_id            = aws_security_group.gpu_host.id
  referenced_security_group_id = aws_security_group.gateway.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
  description                  = "vLLM OpenAI API from the gateway only"
}

# X1: the in-process FCFS gateway runs inside the runner task, so the runner reaches vLLM (API + /metrics) directly.
resource "aws_vpc_security_group_ingress_rule" "vllm_from_runner" {
  count                        = var.x1_inprocess_gateway ? 1 : 0
  security_group_id            = aws_security_group.gpu_host.id
  referenced_security_group_id = aws_security_group.runner.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
  description                  = "X1: vLLM API from the runner (in-process FCFS gateway) only"
}

# DCGM / vLLM metrics are scraped by the generators' collector (not the model API).
resource "aws_vpc_security_group_ingress_rule" "dcgm_from_runner" {
  count                        = var.enable_dcgm_exporter ? 1 : 0
  security_group_id            = aws_security_group.gpu_host.id
  referenced_security_group_id = aws_security_group.runner.id
  ip_protocol                  = "tcp"
  from_port                    = 9400
  to_port                      = 9400
  description                  = "DCGM exporter metrics from the generators' collector only"
}

resource "aws_vpc_security_group_ingress_rule" "x2_snapshotd_from_runner" {
  count                        = var.enable_x2_snapshotd ? 1 : 0
  security_group_id            = aws_security_group.gpu_host.id
  referenced_security_group_id = aws_security_group.runner.id
  ip_protocol                  = "tcp"
  from_port                    = var.x2_snapshotd_port
  to_port                      = var.x2_snapshotd_port
  description                  = "X2 boundary-snapshot daemon from the runner only"
}

resource "aws_vpc_security_group_egress_rule" "gpu_host_all" {
  security_group_id = aws_security_group.gpu_host.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "ECS agent, SSM, image pulls"
}

resource "aws_security_group" "endpoints" {
  count       = var.network_mode == "endpoints" ? 1 : 0
  name_prefix = "${local.name}-vpce-"
  description = "Interface endpoints: HTTPS from inside the VPC"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_https" {
  count             = var.network_mode == "endpoints" ? 1 : 0
  security_group_id = aws_security_group.endpoints[0].id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "HTTPS from VPC"
}
