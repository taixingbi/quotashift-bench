"""X1 export: AWS-identifier sanitizer and fail-closed gate (draft rev 4 section 8; stage X1-E).

The v5 exporter (scripts/export_v5_raw.py) is FROZEN and is not modified. X1 exports run that exporter's rules and then
this additional layer, which removes AWS identifiers that only appear on G1:

  account ids (12 digits) in ARNs / ECR hosts / bucket names, ARNs, EC2 instance/volume/ENI/VPC/subnet/SG/NAT/IGW/
  route-table/launch-template ids, EC2 private DNS names (ip-10-0-1-23.ec2.internal), ECS task/container-instance ids
  in ARNs, IAM access-key ids (AKIA/ASIA), and STS session principals.

Public, non-identifying values are KEPT on purpose: AMI ids (public SSM-recommended image), instance types, region and
AZ names, image digests. `gate()` returns the patterns that survive sanitizing (empty = clean).
"""

from __future__ import annotations

import re

# order matters: whole ARNs first, then embedded ids
_SUBS: list[tuple[str, re.Pattern[str], str]] = [
    ("arn", re.compile(r"arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:\d{12}:[^\s\"',)\]}]+"), "<aws-arn>"),
    ("ecr_host", re.compile(r"\b\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com"), "<ecr-host>"),
    ("access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "<aws-access-key-id>"),
    ("ec2_private_dns", re.compile(r"\bip-\d{1,3}-\d{1,3}-\d{1,3}-\d{1,3}(?:\.[a-z0-9-]+)?\.(?:ec2\.)?internal\b"),
     "<ec2-private-dns>"),
    ("ec2_id", re.compile(r"\b(?:i|vol|eni|vpc|subnet|sg|nat|igw|rtb|lt|eipalloc|vpce|snap)-[0-9a-f]{8,17}\b"),
     "<ec2-id>"),
    ("account_id_in_name", re.compile(r"(?<=-)\d{12}\b"), "<acct>"),          # e.g. quotashift-research-results-<acct>
]

_GATE: list[tuple[str, re.Pattern[str]]] = [
    ("arn_with_account", re.compile(r"arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:\d{12}:")),
    ("ecr_host", re.compile(r"\b\d{12}\.dkr\.ecr\.")),
    ("access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("ec2_private_dns", re.compile(r"\bip-\d{1,3}-\d{1,3}-\d{1,3}-\d{1,3}\.")),
    ("ec2_id", re.compile(r"\b(?:i|vol|eni|vpc|subnet|sg|nat|igw|rtb|lt|eipalloc|vpce|snap)-[0-9a-f]{8,17}\b")),
    ("secret_access_key_field", re.compile(r"(?i)aws_secret_access_key\s*[=:]")),
]


def sanitize(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for name, pat, repl in _SUBS:
        text, n = pat.subn(repl, text)
        if n:
            counts[name] = counts.get(name, 0) + n
    return text, counts


def gate(text: str, account_ids: frozenset[str] = frozenset()) -> list[str]:
    """Names of forbidden patterns still present. `account_ids` (known from the run manifest) are matched literally
    anywhere, so a bare 12-digit account id that no pattern anticipated still refuses the export."""
    hits = [name for name, pat in _GATE if pat.search(text)]
    hits += [f"account_id:{a[-4:]}" for a in account_ids if a in text]
    return hits
