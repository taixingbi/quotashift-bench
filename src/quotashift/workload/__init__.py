import os as _os

if _os.environ.get("QUOTASHIFT_TOKEN_COUNTER"):  # X2 Amendment A3 (docs/PROTOCOL_X2_AMENDMENT_A3.md); unset: no-op
    from quotashift.workload.tokenize_a3 import activate_from_env as _a3

    _a3()
