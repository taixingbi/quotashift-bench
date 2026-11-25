#!/usr/bin/env bash
# X1 G0 server control. Runs ON gpu-node-2 (piped over ssh); NEVER used for gpu-node-1.
#   ssh gpu-node-2 'bash -s' -- start g0m1 < scripts/x1_g0_server.sh      # X1 launch template (rev 4 section 2.1)
#   ssh gpu-node-2 'bash -s' -- stop < scripts/x1_g0_server.sh             # SIGTERM any `vllm serve` of this user
#   ssh gpu-node-2 'bash -s' -- status < scripts/x1_g0_server.sh
# The server is started directly (no bash -c wrapper, so P1 can match exactly one python process) from the pinned
# env "vllm0171"; the previous "vllm" (0.34.0) env is left untouched for rollback (rollback command in ~/x1/ROLLBACK.txt).
set -euo pipefail
ACTION="${1:?start|stop|status}"; PLAT="${2:-}"
ENV="$HOME/miniconda3/envs/vllm0171"
mkdir -p "$HOME/x1"
case "$PLAT" in
  g0m0) MODEL=Qwen/Qwen2.5-7B-Instruct; REV=a09a35458c702b33eeacc393d103063234e8bc28; EXTRA=() ;;
  g0m1) MODEL=mistralai/Mistral-7B-Instruct-v0.3; REV=c170c708c41dac9275d15a8fff4eca08d52bab71
        EXTRA=(--tokenizer-mode mistral --config-format mistral --load-format mistral) ;;
  "") ;;
  *) echo "unknown platform $PLAT (G0 only: g0m0|g0m1)" >&2; exit 2 ;;
esac
case "$ACTION" in
  stop)
    PIDS=$(pgrep -u "$USER" -f "vllm serve" || true)
    [[ -z "$PIDS" ]] && { echo "no vllm serve running"; exit 0; }
    kill -TERM $PIDS
    for _ in $(seq 1 60); do pgrep -u "$USER" -f "vllm serve" >/dev/null || { echo "stopped: $PIDS"; exit 0; }; sleep 2; done
    echo "STILL RUNNING after 120 s: $(pgrep -u "$USER" -f 'vllm serve')" >&2; exit 3 ;;
  status) pgrep -u "$USER" -af "vllm serve" || echo "no vllm serve running"
          curl -s -o /dev/null -w "health %{http_code}\n" http://localhost:8000/health || true ;;
  start)
    [[ -n "$PLAT" ]] || { echo "start needs a platform" >&2; exit 2; }
    if pgrep -u "$USER" -f "vllm serve" >/dev/null; then echo "REFUSED: a vllm serve is already running" >&2; exit 3; fi
    LOG="$HOME/x1/vllm_${PLAT}.log"
    [[ -e "$LOG" ]] && mv "$LOG" "$LOG.$(date +%Y%m%dT%H%M%S)"
    T0=$(date +%s.%N)
    VLLM_SERVER_DEV_MODE=1 CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 VLLM_NO_USAGE_STATS=1 HF_HUB_DISABLE_TELEMETRY=1 \
      setsid nohup "$ENV/bin/python" "$ENV/bin/vllm" serve "$MODEL" --revision "$REV" --host 0.0.0.0 --port 8000 \
      --dtype float16 --max-model-len 4096 --gpu-memory-utilization 0.80 --enable-prefix-caching \
      --enable-prompt-tokens-details --max-num-seqs 256 --max-num-batched-tokens 2048 "${EXTRA[@]}" \
      > "$LOG" 2>&1 < /dev/null &
    for _ in $(seq 1 900); do
      if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null | grep -q 200; then
        T1=$(date +%s.%N)
        printf '{"platform":"%s","t_start":%s,"t_healthy":%s,"startup_s":%s}\n' "$PLAT" "$T0" "$T1" \
          "$(python3 -c "print(round($T1-$T0,1))")" > "$HOME/x1/launch_${PLAT}.json"
        cat "$HOME/x1/launch_${PLAT}.json"; exit 0
      fi
      pgrep -u "$USER" -f "vllm serve" >/dev/null || { echo "SERVER EXITED during startup; tail:" >&2; tail -30 "$LOG" >&2; exit 4; }
      sleep 2
    done
    echo "no healthy server within 1800 s" >&2; exit 5 ;;
  *) echo "usage: start <g0m0|g0m1> | stop | status" >&2; exit 2 ;;
esac
