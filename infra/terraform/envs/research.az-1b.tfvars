# Placement overlay (owner decision "B", 2026-11-25): g6.xlarge had no capacity in us-east-1a at first boot.
# Keeps the stack single-AZ (GPU, runner and NAT co-located) in us-east-1b. Use: QUOTASHIFT_OVERLAYS="x2 az-1b".
primary_az = "us-east-1b"
