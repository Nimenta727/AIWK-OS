#!/bin/sh
# Optional AIWS OS offline llama.cpp service: guest CPU only.
set -eu
if [ "$(id -u)" -eq 0 ]; then echo 'Model cannot run as guest root' >&2; exit 1; fi
if [ ! -f /etc/aiws/guest-managed ] ||
   [ "$(cat /etc/aiws/guest-managed)" != "AIWS_GUEST_ONLY_VERSION=1" ]; then
   echo 'Not an AIWS guest system' >&2; exit 1
fi
if ! systemd-detect-virt --vm --quiet; then
   echo 'Model requires a dedicated virtual machine' >&2; exit 1
fi
model="$HOME/.local/share/aiws/models/aiws-local.gguf"
if [ -L "$model" ] || [ ! -f "$model" ]; then
   echo 'No regular guest-local GGUF weights found' >&2; exit 1
fi
if ! command -v llama-server >/dev/null 2>&1; then
   echo 'llama-server is unavailable inside this guest' >&2; exit 1
fi
# Never access host GPU; model API is strictly loopback inside guest.
# The small gate owns the public model port (18080): it starts llama-server on the internal loopback port 18081
# only when a real request arrives and stops it again after an idle period, so an unused model costs no RAM.
idle="${AIWS_MODEL_IDLE_SECONDS:-300}"
case "$idle" in ''|*[!0-9]*) idle=300 ;; esac
if [ "$idle" -lt 30 ] || [ "$idle" -gt 86400 ]; then idle=300; fi
# Resident by default: the model is loaded at start-up, is not unloaded for being idle, and is restarted if it dies.
# Set AIWS_MODEL_RESIDENT=0 on a machine short of RAM to get the old lazy-start / idle-unload behaviour back.
resident=--resident
[ "${AIWS_MODEL_RESIDENT:-1}" = "0" ] && resident=
exec python3 /usr/local/lib/aiws/aiws_model_gate.py --listen-port 18080 --child-port 18081 --idle-seconds "$idle" $resident -- \
  llama-server --model "$model" --alias aiws-local \
  --host 127.0.0.1 --port 18081 --ctx-size 4096 \
  --gpu-layers 0 --parallel 1
