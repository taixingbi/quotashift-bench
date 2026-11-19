# Offline plan tests: mock AWS provider => no credentials, no API calls, no cost.
# Run: terraform -chdir=infra/terraform test

mock_provider "aws" {
  override_data {
    target = data.aws_availability_zones.available
    values = { names = ["us-east-1a", "us-east-1b"] }
  }
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "123456789012" }
  }
  override_data {
    target = data.aws_ssm_parameter.ecs_gpu_ami
    values = { value = "ami-0123456789abcdef0" }
  }
}

variables {
  owner              = "test-owner"
  max_run_minutes    = 60
  spending_limit_usd = 25
}

run "defaults_are_private_and_idle_safe" {
  command = plan

  assert {
    condition     = aws_autoscaling_group.gpu.desired_capacity == 0 && aws_autoscaling_group.gpu.max_size == 1
    error_message = "GPU ASG must default to 0 desired and at most 1 instance."
  }
  assert {
    condition     = aws_ecs_service.vllm.desired_count == 0
    error_message = "vLLM service must default to 0 tasks."
  }
  # QuotaShift defaults to the private nat network: exactly one NAT, no public IP on the
  # GPU host, and no gateway/generator compute until their images are provided.
  assert {
    condition     = length(aws_nat_gateway.this) == 1 && length(aws_vpc_endpoint.interface) == 0
    error_message = "Default (nat) mode must create exactly one NAT gateway and no interface endpoints."
  }
  assert {
    condition     = aws_launch_template.gpu.network_interfaces[0].associate_public_ip_address == "false"
    error_message = "Default private network must not assign a public IP to the GPU host."
  }
  assert {
    condition     = length(aws_ecs_service.gateway) == 0 && length(aws_ecs_task_definition.gateway) == 0 && length(aws_ecs_task_definition.generator) == 0
    error_message = "Gateway and generator compute must not exist until gateway_image/runner_image are set."
  }
  assert {
    condition     = length(aws_budgets_budget.monthly) == 0
    error_message = "Budget only when alert emails are configured."
  }
  assert {
    condition     = length(aws_budgets_budget.monthly) == 0
    error_message = "Budget only when alert emails are configured."
  }
  assert {
    condition = alltrue([
      aws_vpc_security_group_ingress_rule.vllm_from_gateway.cidr_ipv4 == null,
      aws_vpc_security_group_ingress_rule.vllm_from_gateway.cidr_ipv6 == null,
      aws_vpc_security_group_ingress_rule.dcgm_from_runner[0].cidr_ipv4 == null,
    ])
    error_message = "vLLM / metrics ingress must be SG-referenced only (no internet CIDRs)."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.vllm_from_gateway.from_port == 8000 && aws_vpc_security_group_ingress_rule.vllm_from_gateway.to_port == 8000
    error_message = "Only port 8000 may be opened to the runner for vLLM."
  }
  assert {
    condition     = aws_launch_template.gpu.metadata_options[0].http_tokens == "required"
    error_message = "IMDSv2 must be required."
  }
  assert {
    condition     = aws_launch_template.gpu.block_device_mappings[0].ebs[0].encrypted == "true"
    error_message = "Root EBS must be encrypted."
  }
  assert {
    condition     = aws_launch_template.gpu.key_name == null
    error_message = "No SSH key pair (use SSM Session Manager)."
  }
  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.results.block_public_acls,
      aws_s3_bucket_public_access_block.results.block_public_policy,
      aws_s3_bucket_public_access_block.results.ignore_public_acls,
      aws_s3_bucket_public_access_block.results.restrict_public_buckets,
    ])
    error_message = "Results bucket must block all public access."
  }
  assert {
    condition     = aws_cloudwatch_log_group.vllm.retention_in_days == 14 && aws_cloudwatch_log_group.runner.retention_in_days == 14
    error_message = "Log retention must be bounded."
  }
  assert {
    condition     = strcontains(aws_ecs_task_definition.vllm.container_definitions, "@sha256:")
    error_message = "vLLM image must be digest-pinned."
  }
  assert {
    condition     = strcontains(aws_ecs_task_definition.vllm.container_definitions, "\"GPU\"")
    error_message = "vLLM task must reserve exactly one GPU."
  }
  assert {
    condition     = length(aws_ecs_task_definition.runner) == 0
    error_message = "Runner task definition only when a digest-pinned runner image is provided."
  }
}

run "nat_mode_creates_single_nat" {
  command = plan
  variables {
    network_mode = "nat"
  }
  assert {
    condition     = length(aws_nat_gateway.this) == 1 && length(aws_subnet.private) == 1
    error_message = "nat mode: one NAT gateway and private compute subnet."
  }
  assert {
    condition     = aws_launch_template.gpu.network_interfaces[0].associate_public_ip_address == "false"
    error_message = "Private modes must not assign public IPs to the GPU host."
  }
}

run "endpoints_mode_requires_s3_model_source" {
  command = plan
  variables {
    network_mode = "endpoints"
  }
  expect_failures = [aws_ecs_task_definition.vllm]
}

run "endpoints_mode_with_s3_weights" {
  command = plan
  variables {
    network_mode     = "endpoints"
    model_source     = "s3"
    model_sync_image = "amazon/aws-cli@sha256:0000000000000000000000000000000000000000000000000000000000000000"
  }
  assert {
    condition     = length(aws_vpc_endpoint.interface) == 10 && length(aws_internet_gateway.this) == 0
    error_message = "endpoints mode: interface endpoints, no internet gateway."
  }
}

run "unpinned_vllm_image_rejected" {
  command = plan
  variables {
    vllm_image = "vllm/vllm-openai:latest"
  }
  expect_failures = [var.vllm_image]
}

run "more_than_one_gpu_rejected" {
  command = plan
  variables {
    gpu_desired_capacity = 2
  }
  expect_failures = [var.gpu_desired_capacity]
}

run "budget_created_with_emails" {
  command = plan
  variables {
    budget_alert_emails = ["alerts@example.com"]
  }
  assert {
    condition     = length(aws_budgets_budget.monthly) == 1
    error_message = "Budget alert expected when emails provided."
  }
}

run "gateway_and_generators_are_private_when_enabled" {
  command = plan
  variables {
    gateway_image = "123456789012.dkr.ecr.us-east-1.amazonaws.com/quotashift-dev-gateway@sha256:1111111111111111111111111111111111111111111111111111111111111111"
    runner_image  = "123456789012.dkr.ecr.us-east-1.amazonaws.com/quotashift-dev-runner@sha256:2222222222222222222222222222222222222222222222222222222222222222"
  }
  assert {
    condition     = length(aws_ecs_service.vllm[*]) == 1
    error_message = "Exactly one shared vLLM service (one GPU backend for all tenants)."
  }
  assert {
    condition     = aws_ecs_service.gateway[0].network_configuration[0].assign_public_ip == false
    error_message = "Gateway service must never be assigned a public IP."
  }
  assert {
    condition     = length(aws_ecs_task_definition.generator) == 2
    error_message = "Two load-generator task definitions (benign + scenario)."
  }
  assert {
    condition     = length(aws_service_discovery_private_dns_namespace.internal) == 1
    error_message = "Internal private DNS namespace must exist when the gateway is enabled."
  }
}

run "no_admin_access_on_any_role" {
  command = plan
  assert {
    condition = alltrue([
      aws_iam_role_policy_attachment.task_execution.policy_arn != "arn:aws:iam::aws:policy/AdministratorAccess",
      aws_iam_role_policy_attachment.gpu_host_ecs.policy_arn != "arn:aws:iam::aws:policy/AdministratorAccess",
      aws_iam_role_policy_attachment.gpu_host_ssm.policy_arn != "arn:aws:iam::aws:policy/AdministratorAccess",
    ])
    error_message = "No task/instance role may attach AdministratorAccess."
  }
}

run "missing_cost_gates_block_plan" {
  command = plan
  variables {
    max_run_minutes = 0
  }
  expect_failures = [var.max_run_minutes]
}
