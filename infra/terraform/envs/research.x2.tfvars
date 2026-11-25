# X2 overlay (docs/X2_INSTRUMENTATION_SPEC.md section 2), applied ON TOP of research.tfvars (+ research.m1-mistral.tfvars for
# Mistral). Applying is approval-gated (x2_aws_*); nothing here is applied by the repository.
# Measured-window policy on G1: no resident telemetry daemon samples the GPU host; the only X2 host component is the
# idle boundary-snapshot daemon, requested by the runner outside measured windows.
enable_host_sampler  = false # X1 1 Hz sampler daemon: off for X2
enable_dcgm_exporter = false # DCGM exporter daemon (and its scrape): off for X2 (energy is not an X2 endpoint)
enable_x2_snapshotd  = true  # X2 boundary-snapshot daemon (port 9500, runner security group only)
