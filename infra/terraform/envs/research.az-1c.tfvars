# Placement overlay (owner decision, 2026-11-25 "AWS Capacity Recovery"): no g6.xlarge capacity in us-east-1a or
# us-east-1b at first boot. Keeps the stack single-AZ (GPU, runner and NAT co-located) in us-east-1c.
# Use: QUOTASHIFT_OVERLAYS="x2 az-1c". Replaces az-1b (not combined with it).
primary_az = "us-east-1c"
