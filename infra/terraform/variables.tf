variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
  validation {
    condition     = contains(["dev", "research"], var.environment)
    error_message = "environment must be dev or research."
  }
}

variable "owner" {
  type        = string
  description = "Owner tag (a person/handle; no secrets)."
}

variable "cost_center" {
  type    = string
  default = "personal-research"
}

variable "name_prefix" {
  type    = string
  default = "quotashift"
}

# ---------------------------------------------------------------- networking
variable "network_mode" {
  type        = string
  default     = "nat"
  description = <<-EOT
    public_egress_only: public subnet, auto public IPv4, security groups with ZERO internet ingress (cheapest).
    nat:                private subnet + one NAT gateway (hourly + per-GB cost).
    endpoints:          private subnet + interface VPC endpoints (hourly per endpoint per AZ); no internet egress,
                        so model weights must come from S3 (model_source = "s3").
  EOT
  validation {
    condition     = contains(["public_egress_only", "nat", "endpoints"], var.network_mode)
    error_message = "network_mode must be public_egress_only, nat or endpoints."
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "az_count" {
  type    = number
  default = 1
  validation {
    condition     = var.az_count >= 1 && var.az_count <= 2
    error_message = "az_count must be 1 or 2."
  }
}

# ---------------------------------------------------------------- GPU host
variable "gpu_instance_type" {
  type        = string
  default     = "g6.xlarge" # X1 G1 (owner decision 2026-11-24): 1x NVIDIA L4 24 GB, 4 vCPU, 16 GiB; fits the 4-vCPU G/VT quota
  description = "X1 allows only g6.xlarge (also enforced by the quotashift-x1-operator IAM policy)."
  validation {
    condition     = contains(["g6.xlarge"], var.gpu_instance_type)
    error_message = "X1: gpu_instance_type must be g6.xlarge (owner decision; no quota increase)."
  }
}

variable "gpu_ami_ssm_parameter" {
  type    = string
  default = "/aws/service/ecs/optimized-ami/amazon-linux-2023/gpu/recommended/image_id"
}

variable "gpu_ami_id" {
  type        = string
  default     = ""
  description = "Pin an exact AMI ID for experiments (recommended after the first plan). Empty = resolve SSM parameter."
}

variable "gpu_desired_capacity" {
  type        = number
  default     = 0
  description = "ASG desired capacity. 0 = no GPU instance running (no GPU charges). Raised only by approval-gated start-gpu."
  validation {
    condition     = var.gpu_desired_capacity >= 0 && var.gpu_desired_capacity <= 1
    error_message = "At most one GPU instance in this project phase."
  }
}

variable "gpu_root_volume_gb" {
  type    = number
  default = 120 # ~10 GB vLLM image (compressed) + model cache + logs; verify after E0 smoke
}

# ---------------------------------------------------------------- vLLM task
variable "vllm_image" {
  type        = string
  default     = "vllm/vllm-openai@sha256:0dc46f74eb0e630675d83101dc66c6441c4475cceedcf9235ee42b87c3affd23" # v0.17.1 (X1: same as v5 / G0; Docker Hub index digest, 2026-11-24)
  description = "Must be pinned by digest."
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.vllm_image))
    error_message = "vllm_image must be pinned by @sha256 digest."
  }
}

variable "model_id" {
  type    = string
  default = "Qwen/Qwen2.5-7B-Instruct"
}

variable "model_revision" {
  type    = string
  default = "a09a35458c702b33eeacc393d103063234e8bc28" # Qwen/Qwen2.5-7B-Instruct @ main, resolved from HF API 2026-11-19
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.model_revision))
    error_message = "model_revision must be a 40-hex commit SHA."
  }
}

variable "model_source" {
  type        = string
  default     = "huggingface"
  description = "huggingface (needs internet egress) or s3 (pre-staged weights under s3://<results bucket>/models/)."
  validation {
    condition     = contains(["huggingface", "s3"], var.model_source)
    error_message = "model_source must be huggingface or s3."
  }
}

variable "vllm_max_model_len" {
  type    = number
  default = 4096 # conservative start (plan Phase 3); raise only after a measured smoke run
}

variable "vllm_gpu_memory_utilization" {
  type    = number
  default = 0.80 # X1 launch template (identical on all four platforms)
}

variable "vllm_extra_args" {
  type        = list(string)
  description = "X1 launch template flags (docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md rev 4, section 2.1); identical on G0 and G1."
  default = ["--dtype", "float16", "--enable-prefix-caching", "--enable-prompt-tokens-details",
  "--max-num-seqs", "256", "--max-num-batched-tokens", "2048"]
}

variable "vllm_model_args" {
  type        = list(string)
  default     = []
  description = "Model-specific flags. X1 M1 (Mistral): [\"--tokenizer-mode\", \"mistral\", \"--config-format\", \"mistral\", \"--load-format\", \"mistral\"]."
}

variable "vllm_dev_mode" {
  type        = bool
  default     = true
  description = "VLLM_SERVER_DEV_MODE=1: exposes /reset_prefix_cache and /server_info, required by the X1 verified pre-block cache reset. Private VPC only."
}

variable "enable_host_sampler" {
  type        = bool
  default     = true
  description = "X1 host-telemetry sampler (scripts/x1_host_sampler.py) as an ECS daemon with host PID namespace; read-only /proc, output to CloudWatch."
}

variable "enable_x2_snapshotd" {
  type        = bool
  default     = false
  description = "X2 boundary-snapshot daemon (scripts/x2_host_snapshot.py --serve) on the GPU host: host PID namespace, read-only /proc, no logging, idle in accept() between requests; reachable from the runner only. X1 stacks leave it off."
}

variable "x2_snapshotd_port" {
  type    = number
  default = 9500
}

variable "host_sampler_image" {
  type    = string
  default = "python@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36" # = python 3.12.13-slim (Docker Hub index digest, 2026-11-24)
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.host_sampler_image))
    error_message = "host_sampler_image must be pinned by @sha256 digest."
  }
}

variable "vllm_desired_count" {
  type    = number
  default = 0
  validation {
    condition     = var.vllm_desired_count >= 0 && var.vllm_desired_count <= 1
    error_message = "Fixed single vLLM task (0 or 1); no autoscaling during experiments."
  }
}

variable "enable_dcgm_exporter" {
  type    = bool
  default = true
}

variable "dcgm_exporter_image" {
  type    = string
  default = "nvidia/dcgm-exporter@sha256:2490e1dfb5baaee6765ef2841813af7d978bb459a566c22c326a8fc27c64eea9" # 4.7.0-4.9.0
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.dcgm_exporter_image))
    error_message = "dcgm_exporter_image must be pinned by digest."
  }
}

# ---------------------------------------------------------------- runner (gateway + load generator)
variable "runner_image" {
  type        = string
  default     = ""
  description = "quotashift image in ECR pinned by digest (built from docker/Dockerfile). Empty = task definition not created."
  validation {
    condition     = var.runner_image == "" || can(regex("@sha256:[0-9a-f]{64}$", var.runner_image))
    error_message = "runner_image must be empty or pinned by @sha256 digest."
  }
}

variable "vllm_backend_url" {
  type        = string
  default     = "http://vllm.quotashift.internal:8000"
  description = "Private URL the gateway uses to reach vLLM. Set to the GPU host's private address/Cloud Map name at deploy; must be a private host (the gateway enforces this at runtime)."
}

variable "gateway_image" {
  type        = string
  default     = ""
  description = "quotashift gateway image in ECR pinned by digest (built from docker/Dockerfile, gateway entrypoint). Empty = gateway task/service not created."
  validation {
    condition     = var.gateway_image == "" || can(regex("@sha256:[0-9a-f]{64}$", var.gateway_image))
    error_message = "gateway_image must be empty or pinned by @sha256 digest."
  }
}

variable "runner_cpu" {
  type    = number
  default = 2048
}

variable "runner_memory" {
  type    = number
  default = 4096
}

# ---------------------------------------------------------------- observability / cost guards
variable "log_retention_days" {
  type    = number
  default = 14
}

variable "monthly_budget_usd" {
  type    = number
  default = 150
}

# Hard cost stop-conditions (plan Phase 3): no default => an apply must set them deliberately.
variable "max_run_minutes" {
  type        = number
  description = "Maximum intended GPU-on wall-clock minutes for the campaign. Operational budget used by scripts/estimate_cost.py and run controls; must be positive."
  validation {
    condition     = var.max_run_minutes > 0
    error_message = "max_run_minutes must be a positive number (deliberate cost stop-condition)."
  }
}

variable "spending_limit_usd" {
  type        = number
  description = "Owner-approved spending ceiling for this environment (USD). Must be positive; recorded in outputs and cost docs."
  validation {
    condition     = var.spending_limit_usd > 0
    error_message = "spending_limit_usd must be a positive number (deliberate cost stop-condition)."
  }
}

variable "budget_alert_emails" {
  type        = list(string)
  default     = []
  description = "Empty = budget resource not created. Budgets alert only; they do NOT stop spend."
}

variable "results_expiration_days" {
  type        = number
  default     = 0
  description = "0 = never expire raw results (research data). Staged model weights under models/ always expire after 30 days."
}

variable "model_sync_image" {
  type        = string
  default     = ""
  description = "Digest-pinned AWS CLI image used to sync weights from S3 when model_source = s3."
  validation {
    condition     = var.model_sync_image == "" || can(regex("@sha256:[0-9a-f]{64}$", var.model_sync_image))
    error_message = "model_sync_image must be pinned by @sha256 digest."
  }
}

# ---------------------------------------------------------------- X1 (X1-E completion, 2026-11-24)
variable "x1_inprocess_gateway" {
  type        = bool
  default     = true
  description = "X1/v5 semantics: the FCFS gateway runs IN-PROCESS inside the runner task (cap from each scenario). The standalone Fargate gateway service must stay disabled (gateway_image = \"\"), otherwise requests would pass two admission layers."
}

variable "enable_private_dns" {
  type        = bool
  default     = true
  description = "Cloud Map private namespace <name_prefix>.internal with an A record vllm.<ns> registered by the GPU host at boot (X1 targets use http://vllm.quotashift.internal:8000)."
}
