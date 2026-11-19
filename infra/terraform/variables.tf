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
  type    = string
  default = "g5.2xlarge" # 1x NVIDIA A10G 24 GB; verify regional availability, quota and price before approval
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
  default     = "vllm/vllm-openai@sha256:d825baf9ce4b1b6bfc5ecc7b79880c7e6748c65a72d697ce3d47607aafa84c6e" # v0.33.0
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
  default = 0.90
}

variable "vllm_extra_args" {
  type    = list(string)
  default = ["--no-enable-prefix-caching"] # fixed serving config; fcfs is vLLM default (QuotaShift studies workload, not the scheduler)
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
