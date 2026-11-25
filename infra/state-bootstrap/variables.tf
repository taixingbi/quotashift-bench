variable "region" {
  type    = string
  default = "us-east-1"
}

variable "bucket_suffix" {
  type        = string
  description = "Random, non-identifying suffix chosen by the owner (e.g. 8 hex chars). Never the account id."
  validation {
    condition     = can(regex("^[a-z0-9]{6,16}$", var.bucket_suffix))
    error_message = "bucket_suffix: 6-16 lowercase alphanumerics (no account id)."
  }
}

variable "noncurrent_version_days" {
  type        = number
  default     = 365
  description = "Keep old state versions this long (recovery window)."
}
