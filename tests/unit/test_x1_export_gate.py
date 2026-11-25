"""X1 AWS-identifier sanitizer + gate (src/quotashift/x1/export_gate.py). Synthetic identifiers only."""

from __future__ import annotations

from quotashift.x1.export_gate import gate, sanitize

ACCT = "111122223333"
SAMPLE = (
    f'{{"task": "arn:aws:ecs:us-east-1:{ACCT}:task/quotashift-research/0123456789abcdef0123456789abcdef", '
    f'"role": "arn:aws:iam::{ACCT}:role/quotashift-x1-operator", "image": "{ACCT}.dkr.ecr.us-east-1.amazonaws.com/qs@sha256:'
    + "a" * 64 + '", "host": "ip-10-0-1-23.ec2.internal", "instance": "i-0abc123def4567890", "vpc": "vpc-0a1b2c3d", '
    '"sg": "sg-0123456789abcdef0", "bucket": "quotashift-research-results-' + ACCT + '", '
    '"key": "AKIAABCDEFGHIJKLMNOP", "ami": "ami-0b8f7c7154f9e8f8b", "type": "g6.xlarge", "az": "us-east-1a"}'
)


def test_sanitize_removes_aws_identifiers_and_keeps_public_values():
    out, counts = sanitize(SAMPLE)
    assert ACCT not in out and "i-0abc" not in out and "vpc-0a1b" not in out and "sg-0123" not in out
    assert "ip-10-0-1-23" not in out and "AKIA" not in out
    assert "ami-0b8f7c7154f9e8f8b" in out and "g6.xlarge" in out and "us-east-1a" in out   # public values kept
    assert "sha256:" + "a" * 64 in out                                                     # image digests kept
    assert counts["arn"] == 2 and counts["ec2_id"] == 3
    assert gate(out, frozenset({ACCT})) == []


def test_gate_refuses_unsanitized_text_and_literal_account_ids():
    assert set(gate(SAMPLE)) >= {"arn_with_account", "ecr_host", "access_key", "ec2_private_dns", "ec2_id"}
    assert gate(f"account {ACCT} in free text", frozenset({ACCT})) == ["account_id:3333"]
    assert gate("aws_secret_access_key = x") == ["secret_access_key_field"]
    assert gate("plain text with model c170c708c41dac9275d15a8fff4eca08d52bab71") == []    # 40-hex revisions ok
