# X2 owner approval record (2026-11-25, "Autonomous Execution Plan")

| Token / scope | Granted | Executed |
|---|---|---|
| `x2_freeze1` | X2 Freeze Commit 1 using the reviewed 24-file manifest from `6fc5707` | 2026-11-25 10:38 EST. Re-generated candidate identical to `6fc5707` (files, v5 dependencies, X1 manifest hashes); `experiments/x2/FROZEN_SHA256.json` sha256 `b5033468…`. The protocol keeps its reviewed "rev 2, FREEZE CANDIDATE" header, because those reviewed bytes are what is frozen |
| Phase A offline work | AWS stage orchestration, Terraform, runner-image spec (no build/push), tests, read-only host/network checks, non-frozen fixes, commits | this session |
| Phase B | network/host readiness checks after the owner confirms the wired connection | pending owner confirmation |
| Phase C | prepare the qualification → calibration A → main sequence | prepared only. **Every live stage needs a separate explicit owner approval** (`x2_qual_<p>`, `x2_freeze_calA_<p>`, `x2_cal_<p>`, `x2_freeze_main_<p>`, `x2_main_<p>`) |

Not granted: live GPU work before Ethernet readiness and separate approval; host restart or reconfiguration; terraform
apply / AWS provisioning; credential changes; changes to frozen X1/X2/v4/v5 artifacts; external image build or push;
publication of private raw data.
