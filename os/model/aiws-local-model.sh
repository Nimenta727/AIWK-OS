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
exec llama-server --model "$model" --alias aiws-local \
  --host 127.0.0.1 --port 18080 --ctx-size 4096 \
  --gpu-layers 0 --parallel 1
