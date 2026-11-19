# ---------------------------------------------------------------- ECS cluster + one GPU instance
resource "aws_ecs_cluster" "this" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "disabled" # avoid per-metric CloudWatch charges; we scrape /metrics ourselves
  }
}

locals {
  compute_subnet_ids = local.private_compute ? aws_subnet.private[*].id : aws_subnet.public[*].id
}

resource "aws_launch_template" "gpu" {
  name_prefix   = "${local.name}-gpu-"
  image_id      = local.gpu_ami_id
  instance_type = var.gpu_instance_type

  iam_instance_profile {
    arn = aws_iam_instance_profile.gpu_host.arn
  }

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2
    http_endpoint               = "enabled"
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = var.gpu_root_volume_gb
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  network_interfaces {
    associate_public_ip_address = var.network_mode == "public_egress_only"
    security_groups             = [aws_security_group.gpu_host.id]
    delete_on_termination       = true
  }

  user_data = base64encode(<<-EOT
    #!/bin/bash
    cat >> /etc/ecs/ecs.config <<CFG
    ECS_CLUSTER=${aws_ecs_cluster.this.name}
    ECS_ENABLE_GPU_SUPPORT=true
    ECS_ENABLE_CONTAINER_METADATA=true
    ECS_IMAGE_PULL_BEHAVIOR=prefer-cached
    CFG
  EOT
  )

  tag_specifications {
    resource_type = "instance"
    tags          = merge(local.tags, { Name = "${local.name}-gpu" })
  }
  tag_specifications {
    resource_type = "volume"
    tags          = local.tags
  }
}

resource "aws_autoscaling_group" "gpu" {
  name_prefix         = "${local.name}-gpu-"
  min_size            = 0
  max_size            = 1
  desired_capacity    = var.gpu_desired_capacity
  vpc_zone_identifier = [local.compute_subnet_ids[0]] # single AZ: one GPU, no cross-AZ traffic

  launch_template {
    id      = aws_launch_template.gpu.id
    version = aws_launch_template.gpu.latest_version
  }

  dynamic "tag" {
    for_each = local.tags
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }

  lifecycle {
    # start-gpu / stop-gpu scripts change desired capacity out-of-band (approval-gated)
    ignore_changes = [desired_capacity]
  }
}

# ---------------------------------------------------------------- vLLM task (host networking, 1 GPU)
locals {
  model_arg = var.model_source == "s3" ? "/models/${var.model_id}" : var.model_id
  vllm_container = {
    name       = "vllm"
    image      = var.vllm_image
    essential  = true
    entryPoint = ["vllm", "serve"]
    command = concat([
      local.model_arg,
      "--revision", var.model_revision,
      "--tokenizer-revision", var.model_revision,
      "--host", "0.0.0.0",
      "--port", "8000",
      "--max-model-len", tostring(var.vllm_max_model_len),
      "--gpu-memory-utilization", tostring(var.vllm_gpu_memory_utilization),
    ], var.vllm_extra_args)
    resourceRequirements = [{ type = "GPU", value = "1" }]
    memoryReservation    = 12288
    portMappings         = [{ containerPort = 8000, hostPort = 8000, protocol = "tcp" }]
    linuxParameters      = { sharedMemorySize = 4096 }
    mountPoints          = [{ sourceVolume = "hf-cache", containerPath = "/root/.cache/huggingface" }, { sourceVolume = "models", containerPath = "/models" }]
    environment          = [{ name = "VLLM_NO_USAGE_STATS", value = "1" }, { name = "HF_HUB_DISABLE_TELEMETRY", value = "1" }]
    healthCheck = {
      command     = ["CMD-SHELL", "curl -fsS http://localhost:8000/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 10
      startPeriod = 300
    }
    dependsOn = var.model_source == "s3" ? [{ containerName = "model-sync", condition = "SUCCESS" }] : []
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.vllm.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "vllm"
      }
    }
  }
  model_sync_container = {
    name        = "model-sync"
    image       = var.model_sync_image
    essential   = false
    command     = ["s3", "sync", "s3://${aws_s3_bucket.results.bucket}/models/${var.model_id}/${var.model_revision}/", "/models/${var.model_id}/"]
    memory      = 512
    mountPoints = [{ sourceVolume = "models", containerPath = "/models" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.vllm.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "model-sync"
      }
    }
  }
}

resource "aws_ecs_task_definition" "vllm" {
  family                   = "${local.name}-vllm"
  requires_compatibilities = ["EC2"]
  network_mode             = "host"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.vllm_task.arn
  # jsonencode each branch separately (tuples of different object shapes cannot share a conditional type)
  container_definitions = (
    var.model_source == "s3"
    ? jsonencode([local.model_sync_container, local.vllm_container])
    : jsonencode([local.vllm_container])
  )
  volume {
    name      = "hf-cache"
    host_path = "/opt/quotashift/hf-cache"
  }
  volume {
    name      = "models"
    host_path = "/opt/quotashift/models"
  }

  lifecycle {
    precondition {
      condition     = var.model_source != "s3" || var.model_sync_image != ""
      error_message = "model_source = s3 requires a digest-pinned model_sync_image."
    }
    precondition {
      condition     = var.network_mode != "endpoints" || var.model_source == "s3"
      error_message = "network_mode = endpoints has no internet egress; use model_source = s3."
    }
  }
}

resource "aws_ecs_service" "vllm" {
  name                               = "${local.name}-vllm"
  cluster                            = aws_ecs_cluster.this.id
  task_definition                    = aws_ecs_task_definition.vllm.arn
  desired_count                      = var.vllm_desired_count
  launch_type                        = "EC2"
  deployment_minimum_healthy_percent = 0 # single GPU: stop old task before starting new
  deployment_maximum_percent         = 100

  lifecycle {
    ignore_changes = [desired_count] # controlled by approval-gated scripts; no autoscaling
  }
}

# ---------------------------------------------------------------- DCGM exporter (daemon on the GPU host)
resource "aws_ecs_task_definition" "dcgm" {
  count                    = var.enable_dcgm_exporter ? 1 : 0
  family                   = "${local.name}-dcgm"
  requires_compatibilities = ["EC2"]
  network_mode             = "host"
  execution_role_arn       = aws_iam_role.task_execution.arn
  container_definitions = jsonencode([{
    name              = "dcgm-exporter"
    image             = var.dcgm_exporter_image
    essential         = true
    memoryReservation = 256
    portMappings      = [{ containerPort = 9400, hostPort = 9400, protocol = "tcp" }]
    environment       = [{ name = "NVIDIA_VISIBLE_DEVICES", value = "all" }]
    linuxParameters   = { capabilities = { add = ["SYS_ADMIN"] } }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.dcgm.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "dcgm"
      }
    }
  }])
}

resource "aws_ecs_service" "dcgm" {
  count               = var.enable_dcgm_exporter ? 1 : 0
  name                = "${local.name}-dcgm"
  cluster             = aws_ecs_cluster.this.id
  task_definition     = aws_ecs_task_definition.dcgm[0].arn
  launch_type         = "EC2"
  scheduling_strategy = "DAEMON" # runs only while a GPU instance exists
}

# ---------------------------------------------------------------- runner (gateway + load generator) on Fargate
resource "aws_ecs_task_definition" "runner" {
  count                    = var.runner_image == "" ? 0 : 1
  family                   = "${local.name}-runner"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.runner_cpu)
  memory                   = tostring(var.runner_memory)
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.runner_task.arn
  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([{
    name        = "runner"
    image       = var.runner_image
    essential   = true
    environment = [{ name = "QUOTASHIFT_RESULTS_S3", value = "s3://${aws_s3_bucket.results.bucket}/results/" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.runner.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "runner"
      }
    }
  }])
}

# ---------------------------------------------------------------- internal service discovery
# Private DNS namespace so generators resolve the gateway by name. Created only when a
# gateway image is provided (keeps the default plan free of a private hosted zone).
resource "aws_service_discovery_private_dns_namespace" "internal" {
  count       = var.gateway_image == "" ? 0 : 1
  name        = "${var.name_prefix}.internal"
  description = "QuotaShift internal service discovery (no public records)"
  vpc         = aws_vpc.this.id
}

resource "aws_service_discovery_service" "gateway" {
  count = var.gateway_image == "" ? 0 : 1
  name  = "gateway"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.internal[0].id
    dns_records {
      type = "A"
      ttl  = 10
    }
    routing_policy = "MULTIVALUE"
  }
}

# ---------------------------------------------------------------- tenant gateway (Fargate, internal only)
resource "aws_ecs_task_definition" "gateway" {
  count                    = var.gateway_image == "" ? 0 : 1
  family                   = "${local.name}-gateway"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.runner_task.arn
  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([{
    name         = "gateway"
    image        = var.gateway_image
    essential    = true
    entryPoint   = ["python", "-m", "uvicorn", "--factory", "quotashift.gateway.app:app_from_env", "--host", "0.0.0.0", "--port", "8080"]
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]
    environment = [
      { name = "QUOTASHIFT_TENANTS", value = "/app/configs/gateway/tenants.example.yaml" },
      { name = "QUOTASHIFT_BACKEND_URL", value = var.vllm_backend_url },
      { name = "QUOTASHIFT_MODEL", value = var.model_id },
      { name = "QUOTASHIFT_MAX_GLOBAL_INFLIGHT", value = "4" },
      { name = "QUOTASHIFT_RUN_DEADLINE_S", value = tostring(var.max_run_minutes * 60) },
    ]
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://localhost:8080/healthz')\" || exit 1"]
      interval    = 15
      timeout     = 5
      retries     = 5
      startPeriod = 20
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.gateway.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "gateway"
      }
    }
  }])
}

resource "aws_ecs_service" "gateway" {
  count           = var.gateway_image == "" ? 0 : 1
  name            = "${local.name}-gateway"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.gateway[0].arn
  desired_count   = 0 # raised deliberately at experiment time; never a standing public service
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.compute_subnet_ids
    security_groups  = [aws_security_group.gateway.id]
    assign_public_ip = false # gateway is never reachable from the internet
  }

  service_registries {
    registry_arn = aws_service_discovery_service.gateway[0].arn
  }

  lifecycle {
    ignore_changes = [desired_count]
  }
}

# ---------------------------------------------------------------- load generators (Fargate run-task, no service)
# benign-runner (fixed seeded victims) and scenario-runner (controlled competing patterns).
resource "aws_ecs_task_definition" "generator" {
  for_each                 = var.runner_image == "" ? toset([]) : toset(["benign", "scenario"])
  family                   = "${local.name}-${each.key}-runner"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.runner_cpu)
  memory                   = tostring(var.runner_memory)
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.runner_task.arn
  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([{
    name      = "${each.key}-runner"
    image     = var.runner_image
    essential = true
    environment = [
      { name = "QUOTASHIFT_ROLE", value = each.key },
      { name = "QUOTASHIFT_RESULTS_S3", value = "s3://${aws_s3_bucket.results.bucket}/results/" },
      { name = "QUOTASHIFT_GATEWAY_URL", value = "http://gateway.${var.name_prefix}.internal:8080" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.runner.name
        awslogs-region        = var.region
        awslogs-stream-prefix = each.key
      }
    }
  }])
}
