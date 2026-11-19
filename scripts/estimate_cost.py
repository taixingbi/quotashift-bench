#!/usr/bin/env python3
"""Cost estimate from a USER-SUPPLIED price file (no prices are hardcoded here).

    python scripts/estimate_cost.py --prices configs/infrastructure/prices.yaml --gpu-hours 40 --network-mode public_egress_only

Fill prices.yaml from the AWS Pricing Calculator / Price List API for your region
on the day you request approval; record the date in the file.
"""

from __future__ import annotations

import argparse
import sys

import yaml

REQUIRED = ["gpu_instance_hour", "public_ipv4_hour", "ebs_gp3_gb_month", "nat_gateway_hour", "nat_gateway_gb",
            "interface_endpoint_hour_per_az", "cloudwatch_logs_ingest_gb", "s3_standard_gb_month",
            "fargate_vcpu_hour", "fargate_gb_hour", "ecr_gb_month"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True)
    ap.add_argument("--gpu-hours", type=float, required=True, help="GPU instance running hours in the period")
    ap.add_argument("--network-mode", choices=["public_egress_only", "nat", "endpoints"], default="public_egress_only")
    ap.add_argument("--infra-hours", type=float, default=None, help="hours NAT/endpoints exist (default = gpu-hours)")
    ap.add_argument("--ebs-gb", type=float, default=120)
    ap.add_argument("--nat-gb", type=float, default=30, help="GB through NAT (model + image downloads)")
    ap.add_argument("--log-gb", type=float, default=2)
    ap.add_argument("--s3-gb", type=float, default=20)
    ap.add_argument("--ecr-gb", type=float, default=1)
    ap.add_argument("--runner-hours", type=float, default=None)
    ap.add_argument("--runner-vcpu", type=float, default=2)
    ap.add_argument("--runner-gb", type=float, default=4)
    ap.add_argument("--azs", type=int, default=1)
    a = ap.parse_args()
    p = yaml.safe_load(open(a.prices))
    missing = [k for k in REQUIRED if p.get(k) in (None, "")]
    if missing:
        print(f"price file missing values: {missing}", file=sys.stderr)
        return 2
    infra_h = a.infra_hours if a.infra_hours is not None else a.gpu_hours
    runner_h = a.runner_hours if a.runner_hours is not None else a.gpu_hours
    hours_in_month = 730
    lines = {
        "gpu_instance": a.gpu_hours * p["gpu_instance_hour"],
        "public_ipv4 (gpu host + runner)": (a.gpu_hours + runner_h) * p["public_ipv4_hour"] if a.network_mode == "public_egress_only" else 0,
        # EBS exists only while the instance exists (delete_on_termination=true)
        "ebs_root": a.ebs_gb * p["ebs_gp3_gb_month"] * a.gpu_hours / hours_in_month,
        "nat_gateway": (infra_h * p["nat_gateway_hour"] + a.nat_gb * p["nat_gateway_gb"]) if a.network_mode == "nat" else 0,
        "interface_endpoints(10)": 10 * a.azs * infra_h * p["interface_endpoint_hour_per_az"] if a.network_mode == "endpoints" else 0,
        "cloudwatch_logs": a.log_gb * p["cloudwatch_logs_ingest_gb"],
        "s3_results(month)": a.s3_gb * p["s3_standard_gb_month"],
        "ecr(month)": a.ecr_gb * p["ecr_gb_month"],
        "fargate_runner": runner_h * (a.runner_vcpu * p["fargate_vcpu_hour"] + a.runner_gb * p["fargate_gb_hour"]),
    }
    print(f"price file: {a.prices} (as_of: {p.get('as_of', 'UNSPECIFIED')}, region: {p.get('region', '?')})")
    for k, v in lines.items():
        print(f"  {k:34s} {v:10.2f} USD")
    print(f"  {'TOTAL':34s} {sum(lines.values()):10.2f} USD   (excludes taxes, data transfer out, support plans)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
