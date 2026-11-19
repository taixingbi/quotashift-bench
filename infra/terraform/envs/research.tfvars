environment          = "research"
owner                = "REPLACE-owner-handle"
network_mode         = "nat"        # private subnets; no public IP on the GPU host or gateway
gpu_instance_type    = "g5.2xlarge" # 1x NVIDIA A10G 24 GB; verify quota (0 by default) + price first
gpu_desired_capacity = 0
vllm_desired_count   = 0
model_id             = "Qwen/Qwen2.5-7B-Instruct"
model_revision       = "a09a35458c702b33eeacc393d103063234e8bc28" # HF @ main, resolved 2026-11-19
vllm_max_model_len   = 4096
monthly_budget_usd   = 150
budget_alert_emails  = []
# Deliberate cost stop-conditions (no defaults): set before any apply.
max_run_minutes    = 900 # <= 15 GPU-hours planning envelope for the full campaign
spending_limit_usd = 150
