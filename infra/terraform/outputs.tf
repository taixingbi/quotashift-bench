output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "gpu_asg_name" {
  value = aws_autoscaling_group.gpu.name
}

output "vllm_service_name" {
  value = aws_ecs_service.vllm.name
}

output "results_bucket" {
  value = aws_s3_bucket.results.bucket
}

output "runner_ecr_repository_url" {
  value = aws_ecr_repository.runner.repository_url
}

output "runner_security_group_id" {
  value = aws_security_group.runner.id
}

output "compute_subnet_ids" {
  value = local.compute_subnet_ids
}

output "resolved_gpu_ami_id" {
  value       = local.gpu_ami_id
  description = "Record this in the run manifest; pin it via gpu_ami_id for the experiment campaign."
}
