# X1 M1 override (applied on top of research.tfvars): Mistral-7B-Instruct-v0.3 @ c170c708 (Apache-2.0),
# Mistral-native format (consolidated.safetensors, tokenizer.model.v3). Same launch template otherwise.
model_id        = "mistralai/Mistral-7B-Instruct-v0.3"
model_revision  = "c170c708c41dac9275d15a8fff4eca08d52bab71"
vllm_model_args = ["--tokenizer-mode", "mistral", "--config-format", "mistral", "--load-format", "mistral"]
