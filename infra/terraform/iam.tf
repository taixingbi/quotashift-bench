locals {
  ec2_assume = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  ecs_tasks_assume = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

# GPU container instance: ECS agent + SSM Session Manager (no SSH keys).
resource "aws_iam_role" "gpu_host" {
  name_prefix        = "${local.name}-gpuhost-"
  assume_role_policy = local.ec2_assume
}

resource "aws_iam_role_policy_attachment" "gpu_host_ecs" {
  role       = aws_iam_role.gpu_host.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_role_policy_attachment" "gpu_host_ssm" {
  role       = aws_iam_role.gpu_host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "gpu_host" {
  name_prefix = "${local.name}-gpuhost-"
  role        = aws_iam_role.gpu_host.name
}

# Task execution: pull images, write logs.
resource "aws_iam_role" "task_execution" {
  name_prefix        = "${local.name}-exec-"
  assume_role_policy = local.ecs_tasks_assume
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# vLLM task: read-only access to staged model weights.
resource "aws_iam_role" "vllm_task" {
  name_prefix        = "${local.name}-vllm-"
  assume_role_policy = local.ecs_tasks_assume
}

resource "aws_iam_role_policy" "vllm_models_read" {
  name = "models-read"
  role = aws_iam_role.vllm_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.results.arn}/models/*" },
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.results.arn,
      Condition = { StringLike = { "s3:prefix" = ["models/*"] } } },
    ]
  })
}

# Runner: write results, read configs; nothing else.
resource "aws_iam_role" "runner_task" {
  name_prefix        = "${local.name}-runner-"
  assume_role_policy = local.ecs_tasks_assume
}

resource "aws_iam_role_policy" "runner_s3" {
  name = "results-rw"
  role = aws_iam_role.runner_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject"], Resource = "${aws_s3_bucket.results.arn}/results/*" },
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.results.arn}/configs/*" },
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.results.arn}/inputs/*" }, # X2 per-phase inputs (read-only)
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.results.arn,
      Condition = { StringLike = { "s3:prefix" = ["results/*", "configs/*", "inputs/*"] } } },
    ]
  })
}

# X2: ECS Exec into the runner (qualification on G1: the frozen driver asks the operator for an interactive "yes").
# These are the four channel actions ECS Exec requires on the TASK role; the operator additionally needs
# ecs:ExecuteCommand (proposed in infra/iam/x2-operator-additions.json, not applied).
resource "aws_iam_role_policy" "runner_exec" {
  name = "ecs-exec-channels"
  role = aws_iam_role.runner_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["ssmmessages:CreateControlChannel", "ssmmessages:CreateDataChannel",
    "ssmmessages:OpenControlChannel", "ssmmessages:OpenDataChannel"], Resource = "*" }]
  })
}

# X1: the GPU host registers its private IP as vllm.<ns> at boot (user_data). Scoped to that one Cloud Map service
# and the namespace's private hosted zone.
resource "aws_iam_role_policy" "gpu_host_cloudmap" {
  count = var.enable_private_dns ? 1 : 0
  name  = "cloudmap-register-vllm"
  role  = aws_iam_role.gpu_host.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["servicediscovery:RegisterInstance", "servicediscovery:DeregisterInstance"],
      Resource = aws_service_discovery_service.vllm[0].arn },
      { Effect = "Allow", Action = ["servicediscovery:GetOperation"], Resource = "*" },
      { Effect = "Allow", Action = ["route53:ChangeResourceRecordSets", "route53:GetHostedZone"],
      Resource = "arn:aws:route53:::hostedzone/${aws_service_discovery_private_dns_namespace.internal[0].hosted_zone}" },
    ]
  })
}
