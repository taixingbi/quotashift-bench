# Offline plan tests: mock AWS provider => no credentials, no API calls, no cost.
# Run: terraform -chdir=infra/terraform test

mock_provider "aws" {
  # realistic ARNs so that (in-memory) mock applies pass provider-side ARN validation
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/quotashift-mock" }
  }
  mock_resource "aws_iam_instance_profile" {
    defaults = { arn = "arn:aws:iam::123456789012:instance-profile/quotashift-mock" }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = { arn = "arn:aws:ecs:us-east-1:123456789012:task-definition/quotashift-mock:1" }
  }
  mock_resource "aws_ecs_cluster" {
    defaults = { arn = "arn:aws:ecs:us-east-1:123456789012:cluster/quotashift-mock", id = "arn:aws:ecs:us-east-1:123456789012:cluster/quotashift-mock" }
  }
  mock_resource "aws_service_discovery_service" {
    defaults = { arn = "arn:aws:servicediscovery:us-east-1:123456789012:service/srv-mock", id = "srv-mock0123456789" }
  }
  mock_resource "aws_service_discovery_private_dns_namespace" {
    defaults = { arn = "arn:aws:servicediscovery:us-east-1:123456789012:namespace/ns-mock", hosted_zone = "Z0MOCKZONE" }
  }
  mock_resource "aws_launch_template" {
    defaults = { id = "lt-0123456789abcdef0", arn = "arn:aws:ec2:us-east-1:123456789012:launch-template/lt-0123456789abcdef0" }
  }
  mock_resource "aws_autoscaling_group" {
    defaults = { arn = "arn:aws:autoscaling:us-east-1:123456789012:autoScalingGroup:mock:autoScalingGroupName/quotashift-mock" }
  }
  mock_resource "aws_vpc" {
    defaults = { id = "vpc-0123456789abcdef0", arn = "arn:aws:ec2:us-east-1:123456789012:vpc/vpc-0123456789abcdef0" }
  }
  mock_resource "aws_subnet" {
    defaults = { id = "subnet-0123456789abcdef0", arn = "arn:aws:ec2:us-east-1:123456789012:subnet/subnet-0123456789abcdef0" }
  }
  mock_resource "aws_security_group" {
    defaults = { id = "sg-0123456789abcdef0", arn = "arn:aws:ec2:us-east-1:123456789012:security-group/sg-0123456789abcdef0" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::quotashift-mock" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:/quotashift/mock" }
  }
  mock_resource "aws_ecr_repository" {
    defaults = { arn = "arn:aws:ecr:us-east-1:123456789012:repository/quotashift-mock", repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/quotashift-mock" }
  }
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
    x1_inprocess_gateway = false # pre-X1 standalone-gateway layout
    gateway_image        = "123456789012.dkr.ecr.us-east-1.amazonaws.com/quotashift-dev-gateway@sha256:1111111111111111111111111111111111111111111111111111111111111111"
    runner_image         = "123456789012.dkr.ecr.us-east-1.amazonaws.com/quotashift-dev-runner@sha256:2222222222222222222222222222222222222222222222222222222222222222"
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

# ---------------------------------------------------------------- X1 (X1-E, 2026-11-24)
run "x1_defaults_match_the_launch_template" {
  command = plan

  assert {
    condition     = aws_launch_template.gpu.instance_type == "g6.xlarge"
    error_message = "X1 G1 must be g6.xlarge."
  }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.vllm.container_definitions)[0].image == "vllm/vllm-openai@sha256:0dc46f74eb0e630675d83101dc66c6441c4475cceedcf9235ee42b87c3affd23"
    error_message = "vLLM image must be the pinned 0.17.1 digest."
  }
  assert {
    condition = alltrue([for f in ["--revision", "--dtype", "float16", "--max-model-len", "4096", "--gpu-memory-utilization", "0.80",
      "--enable-prefix-caching", "--enable-prompt-tokens-details", "--max-num-seqs", "256", "--max-num-batched-tokens", "2048"] :
    contains(jsondecode(aws_ecs_task_definition.vllm.container_definitions)[0].command, f)])
    error_message = "vLLM argv must carry every X1 template flag."
  }
  assert {
    condition     = !contains(jsondecode(aws_ecs_task_definition.vllm.container_definitions)[0].command, "--tokenizer-revision") && !contains(jsondecode(aws_ecs_task_definition.vllm.container_definitions)[0].command, "--no-enable-prefix-caching")
    error_message = "No flags outside the X1 template."
  }
  assert {
    condition     = contains([for e in jsondecode(aws_ecs_task_definition.vllm.container_definitions)[0].environment : "${e.name}=${e.value}"], "VLLM_SERVER_DEV_MODE=1")
    error_message = "Dev mode is required for the verified prefix-cache reset."
  }
  assert {
    condition     = aws_ecs_task_definition.host_sampler[0].pid_mode == "host" && aws_ecs_service.host_sampler[0].scheduling_strategy == "DAEMON"
    error_message = "Host sampler must run as a host-PID daemon."
  }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.host_sampler[0].container_definitions)[0].readonlyRootFilesystem == true && length([for p in try(jsondecode(aws_ecs_task_definition.host_sampler[0].container_definitions)[0].portMappings, []) : p]) == 0
    error_message = "Host sampler must be read-only with no ports."
  }
}

run "x1_other_instance_types_rejected" {
  command = plan
  variables {
    gpu_instance_type = "g6.2xlarge"
  }
  expect_failures = [var.gpu_instance_type]
}

run "x1_mistral_override_appends_model_args" {
  command = plan
  variables {
    model_id        = "mistralai/Mistral-7B-Instruct-v0.3"
    model_revision  = "c170c708c41dac9275d15a8fff4eca08d52bab71"
    vllm_model_args = ["--tokenizer-mode", "mistral", "--config-format", "mistral", "--load-format", "mistral"]
  }
  assert {
    condition     = slice(jsondecode(aws_ecs_task_definition.vllm.container_definitions)[0].command, length(jsondecode(aws_ecs_task_definition.vllm.container_definitions)[0].command) - 6, length(jsondecode(aws_ecs_task_definition.vllm.container_definitions)[0].command)) == ["--tokenizer-mode", "mistral", "--config-format", "mistral", "--load-format", "mistral"]
    error_message = "Mistral flags must be appended after the shared template."
  }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.vllm.container_definitions)[0].command[0] == "mistralai/Mistral-7B-Instruct-v0.3"
    error_message = "Model id must be the first argv element."
  }
}

# ---------------------------------------------------------------- X1-E completion
run "x1_private_dns_runner_access_and_cloudmap_registration" {
  command = apply # mock apply (in memory): the Cloud Map service id in user_data is known only after create
  assert {
    condition     = length(aws_service_discovery_private_dns_namespace.internal) == 1 && aws_service_discovery_private_dns_namespace.internal[0].name == "quotashift.internal" && length(aws_service_discovery_service.vllm) == 1 && aws_service_discovery_service.vllm[0].name == "vllm"
    error_message = "vllm.quotashift.internal must exist (X1 targets)."
  }
  assert {
    condition     = strcontains(base64decode(aws_launch_template.gpu.user_data), "servicediscovery register-instance") && strcontains(base64decode(aws_launch_template.gpu.user_data), "--instance-id gpu-host")
    error_message = "GPU host must register its private IP in Cloud Map at boot under a fixed instance id."
  }
  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.vllm_from_runner) == 1 && aws_vpc_security_group_ingress_rule.vllm_from_runner[0].from_port == 8000 && aws_vpc_security_group_ingress_rule.vllm_from_runner[0].cidr_ipv4 == null
    error_message = "Runner (in-process gateway) reaches vLLM via security-group reference only."
  }
  assert {
    condition     = length(aws_iam_role_policy.gpu_host_cloudmap) == 1
    error_message = "GPU host needs the scoped Cloud Map registration policy."
  }
  assert {
    condition     = length(aws_ecs_service.gateway) == 0
    error_message = "X1: no standalone gateway service."
  }
}

run "x1_standalone_gateway_refused" {
  command = plan
  variables {
    gateway_image = "123456789012.dkr.ecr.us-east-1.amazonaws.com/quotashift-dev-gateway@sha256:1111111111111111111111111111111111111111111111111111111111111111"
  }
  expect_failures = [aws_ecs_service.gateway]
}

run "x1_runner_with_results_sidecar_qwen" {
  command = plan
  variables {
    runner_image     = "123456789012.dkr.ecr.us-east-1.amazonaws.com/quotashift-research-runner@sha256:2222222222222222222222222222222222222222222222222222222222222222"
    model_sync_image = "amazon/aws-cli@sha256:eccdb3ec77e159d43ca6a750a70738c546883138be7f094498294a1477ec7e42"
  }
  assert {
    condition     = length(jsondecode(aws_ecs_task_definition.runner[0].container_definitions)) == 2 && jsondecode(aws_ecs_task_definition.runner[0].container_definitions)[1].dependsOn[0].condition == "COMPLETE"
    error_message = "Results upload sidecar must run after the runner completes."
  }
  assert {
    condition     = contains([for e in jsondecode(aws_ecs_task_definition.runner[0].container_definitions)[0].environment : "${e.name}=${e.value}"], "QUOTASHIFT_IN_VPC_RUNNER=1") && contains([for e in jsondecode(aws_ecs_task_definition.runner[0].container_definitions)[0].environment : "${e.name}=${e.value}"], "QUOTASHIFT_TARGET=x1-g1-qwen")
    error_message = "Runner must carry the in-VPC flag and the model's private target."
  }
}

run "x1_runner_target_follows_model_switch" {
  command = plan
  variables {
    runner_image    = "123456789012.dkr.ecr.us-east-1.amazonaws.com/quotashift-research-runner@sha256:2222222222222222222222222222222222222222222222222222222222222222"
    model_id        = "mistralai/Mistral-7B-Instruct-v0.3"
    model_revision  = "c170c708c41dac9275d15a8fff4eca08d52bab71"
    vllm_model_args = ["--tokenizer-mode", "mistral", "--config-format", "mistral", "--load-format", "mistral"]
  }
  assert {
    condition     = contains([for e in jsondecode(aws_ecs_task_definition.runner[0].container_definitions)[0].environment : "${e.name}=${e.value}"], "QUOTASHIFT_TARGET=x1-g1-mistral")
    error_message = "Runner target must switch with the model."
  }
}

run "x1_budget_is_60_with_actual_and_forecast_alerts" {
  command = plan
  variables {
    budget_alert_emails = ["alerts@example.com"]
    monthly_budget_usd  = 60
  }
  assert {
    condition     = aws_budgets_budget.monthly[0].limit_amount == "60" && length(aws_budgets_budget.monthly[0].notification) == 4
    error_message = "X1 budget: $60 with 50/80/100% actual + 100% forecast alerts."
  }
}

run "x1_apply_and_destroy_on_mock_leave_gpu_at_zero" {
  command = apply
  assert {
    condition     = aws_autoscaling_group.gpu.desired_capacity == 0 && aws_ecs_service.vllm.desired_count == 0 && aws_ecs_service.host_sampler[0].scheduling_strategy == "DAEMON"
    error_message = "A (mock) apply must start no GPU and no vLLM task; the test framework then destroys everything."
  }
}
