# X1 G1 platform (docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md rev 4; X1-E, 2026-11-24). Applying is approval-gated (X1-J).
environment = "research"
# owner and budget_alert_emails live in the git-ignored infra/terraform/owner.auto.tfvars (see owner.auto.tfvars.example):
# personal contact details never enter the public repository.
network_mode         = "nat"                   # private subnets; no public IP on the GPU host or gateway
gpu_instance_type    = "g6.xlarge"             # 1x NVIDIA L4 24 GB, 4 vCPU, 16 GiB; fits the 4-vCPU G/VT on-demand quota
gpu_ami_id           = "ami-0b8f7c7154f9e8f8b" # al2023-ami-ecs-gpu-hvm-2023.0.20261119-kernel-6.1-x86_64-ebs (SSM recommended, resolved 2026-11-24)
gpu_desired_capacity = 0
vllm_desired_count   = 0
# M0 (default). For M1 add: -var-file=envs/research.m1-mistral.tfvars (separately reviewed plan).
model_id           = "Qwen/Qwen2.5-7B-Instruct"
model_revision     = "a09a35458c702b33eeacc393d103063234e8bc28"
vllm_max_model_len = 4096
# Cost controls (owner: $60 cap). Budgets alert only; they do not stop spend.
monthly_budget_usd = 60
max_run_minutes    = 1320 # longest single X1 AWS stage (X1-N main); X1-K uses <= 480
spending_limit_usd = 60
# Runner (Fargate): stage driver + in-process FCFS gateway + load generation. Sized so the runner never limits load
# (the CPU confounder under study is the GPU host's). runner_image = ECR digest after the approved build (X1-J prep).
runner_cpu       = 4096
runner_memory    = 8192
model_sync_image = "amazon/aws-cli@sha256:eccdb3ec77e159d43ca6a750a70738c546883138be7f094498294a1477ec7e42" # 2.39.6 (2026-11-06): results-upload sidecar
gateway_image    = ""                                                                                       # X1: in-process gateway only (x1_inprocess_gateway = true)
