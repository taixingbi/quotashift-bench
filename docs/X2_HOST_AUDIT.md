# X2 host-process audit (GPU hosts and measurement path)

**Date:** 2026-11-25, 08:44–08:50 EST. **Status:** an input to `docs/X2_INSTRUMENTATION_SPEC.md`; not frozen.

**Method:** read-only.
- **gpu-node-2:** `ps`, `systemctl list-units` / `list-timers`, cron listings, listening sockets, `nvidia-smi` query, the journal for 07:32–07:55, and 100 ICMP echoes from the runner.
- **G1:** repository Terraform only; no AWS call.
- **Nothing changed:** no process was started, stopped or reconfigured, and the vLLM server was not restarted.
- **Sanitised:** addresses, user names and cluster endpoints are removed.

## 1. G0 (gpu-node-2): resident processes and periodic activity

| Class | Found | X2 relevance |
|---|---|---|
| vLLM | API server (python, about 0.2% CPU idle) and EngineCore (**about 11.6% CPU at idle**, busy-polling), under the X1 template since 00:10 | Part of the system under test. Its pids are recorded in every snapshot; a pid change fails the arm |
| X1 instrumentation | none running (no `x1_host_sampler`) | X2 starts no sampler process |
| GPU telemetry exporters | **none**: no node exporter, DCGM, cAdvisor or telegraf; nvidia-persistenced service present | Nothing scrapes the GPU host. The runner has no `nvidia-smi`, so the harness does not poll the GPU on G0 |
| Container runtimes | **k3s agent** (cluster server unreachable: reconnect error every about 8 s in the journal), containerd, dockerd; **0 running containers or pods** | Low CPU, but it is a cluster agent that could schedule work onto the host if its server returned. **Owner action recommended:** stop or disable k3s for the X2 campaign. Until then, it is tracked by the inventory hash |
| Desktop session | gdm, gnome-shell, tracker-miner (file indexer), evolution-alarm, update-notifier, gnome-remote-desktop, cups-browsed, avahi | Intermittent CPU and disk work is possible. Tracked by inventory and the per-arm host CPU mean |
| Package and maintenance timers | apt-daily, apt-daily-upgrade, unattended-upgrades service, fwupd-refresh, snapd, man-db, logrotate, e2scrub_all, fstrim, dpkg-db-backup, motd-news, apport-autoreport, ua-timer, update-notifier timers | **Unattended upgrades could change packages, including the NVIDIA driver, during a campaign.** Recorded at each snapshot; any inventory change flags the arm. **Owner action recommended:** hold or disable unattended upgrades and apt timers for the campaign |
| sysstat | `sysstat-collect.timer` every 10 min (`*:00/10`) plus cron `5-55/10` | Periodic, short. With 120 s arms, about 1 in 5 arms overlaps a collection, equally in both arms in expectation. Recorded (descriptive) |
| Network | **Wi-Fi** (`wlp13s0`, wpa_supplicant); link rate varied **15 to 390 Mbit/s** within minutes (journal) | See §2 |

## 2. Measurement path (runner ↔ G0)

- **Both ends are wireless.** The runner reaches gpu-node-2 over its **Wi-Fi** interface, and the host is on Wi-Fi too.
- **The path is very jittery right now.** 100 ICMP echoes at 0.2 s: RTT min/avg/max/sd = **6.8 / 22.4 / 94.8 / 22.5 ms**, 0% loss.
- **Why it matters:** every TTFT in X1 and v5-era runs on this pair of hosts includes this path. Its jitter is one to two orders of magnitude larger than the 1 ms qualification tolerance.
- **X1 A1 run, descriptive and post hoc:** the five slow sampler-on segments had a lower median Wi-Fi link rate (180 vs about 290–350 Mbit/s elsewhere). That is n = 5 and not a conclusion, but it is consistent with the server's own TTFT histogram showing no ON/OFF difference.
- **X2 consequence:** the Q1 sensitivity analysis shows power collapsing when 20–30% of segments are up to 10 ms slower in both arms (power 0.12–0.02). A jittery wireless path is the most plausible source of such segments.
- **Recommendation (owner action, blocker B-X2-1 in the readiness report):** wired Ethernet for both the runner and gpu-node-2 before X2-Q on G0. A Q0 run on the wired path then shows whether the host is quiet enough.

## 3. G1 (AWS g6.xlarge, from the repository)

| Component | X1 stack | X2 overlay (`envs/research.x2.tfvars`) |
|---|---|---|
| ECS agent, SSM agent, docker `awslogs` shipping of vLLM stdout | resident | unchanged; part of the platform, constant across Q0/Q1/calibration/main |
| **X1 host sampler** (1 Hz ECS daemon) | `enable_host_sampler = true` | **false** |
| **DCGM exporter** (ECS daemon), **scraped by the runner every metrics interval** through `gpu_exporter_url`, plus an idle-power settle before and after each arm (up to 90 s) | on | **off**: `enable_dcgm_exporter = false`, and X2 targets have no exporter URL and `gpu_telemetry: none` |
| X2 boundary-snapshot daemon | absent | **on**: idle in `accept()`, one `/proc` read per runner request, outside measured windows; reachable on port 9500 from the runner's security group only; no logging |
| Runner ↔ GPU host | VPC, wired | unchanged (no wireless path) |

**The X1 asymmetry this removes:** on G1, X1 would have polled DCGM on the GPU host during arms, while on G0 no GPU polling happened, because the runner has no `nvidia-smi`. X2 polls the GPU on neither.

## 4. Harness activity inside measured windows (both GPUs; the frozen v5 harness)

| Activity | Inside an arm? | X2 handling |
|---|---|---|
| Workload requests | yes | the experiment |
| `/metrics` scrape of the vLLM API server, every 0.5 s (`metrics_interval_s`) | yes, both arms | **Kept**: the frozen v5 gates (occupancy reconstruction, engine queue for X2-H4) need it. Q0 and Q1 segments run the same poller, so qualification covers it |
| GPU telemetry polling | G1 under X1 targets: yes (DCGM); G0: no | **Removed** (`gpu_telemetry: none`) |
| Idle-power settle before and after an arm | G1 under X1 targets | **Removed** (only runs when GPU telemetry is available) |
| Pre-block verified prefix-cache reset | before the block, outside arms | unchanged (frozen v5 run_block) |
| X2 boundary snapshots | **never**: before-snapshot, then the 15 s guard, then the arm, then the after-snapshot | the X2 procedure |

## 5. Policy consistency check

The X2 measured-window policy (spec §2) has two halves:
- **The harness itself** starts nothing and opens no host session inside a window.
- **Resident processes** may exist but must be inventoried, identical across Q0, Q1, calibration and main, and never X2-specific samplers.

The audit is consistent with this policy if three things hold:
- **G1:** the overlay disables the sampler and DCGM daemons. Enforced by Terraform plan test `x2_overlay_disables_daemons_and_enables_snapshotd`.
- **X2 targets:** they disable GPU polling. Enforced by unit tests.
- **Inventory changes:** any change on either host flags the arm; a vLLM pid change fails it.

**What the policy cannot control without owner action:** the G0 desktop session, k3s, package timers and the wireless path. These are recorded, flagged and listed as readiness blockers or recommendations, not silently accepted.
