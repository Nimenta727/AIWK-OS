#!/bin/sh
# Optional AIWS OS offline llama.cpp service. Guest CPU only: this is the fallback path. The product path for the 9B model is the
# host GPU channel (aiws_model_channel.py); on a CPU the 9B answers a routing question in about 10 s and reads a long log in minutes.
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
# Memory guard. MEASURED on 2026-11-22 with llama-server itself (built from llama.cpp a956a85; 4 cores, Q4_K_M, context 8192, one slot):
# 10.2-10.7 GB resident = 5.5-5.8 GB of heap (compute buffers, repacked weights) plus 4.7 GB of mapped weights. The guard therefore asks for
# weights + 5 GiB. The context itself is small because only a quarter of this model's layers keep a KV cache. A guest short of that would be killed by
# the kernel, taking the whole workbench with it, so refuse with a clear message instead. Use the host GPU channel, or give the
# virtual machine more memory. AIWS_MODEL_SKIP_RAM_CHECK=1 turns the check off (for machines that have swap and accept the risk).
weights_bytes=$(stat -L -c %s -- "$model" 2>/dev/null || echo 0)
avail_kib=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
need_kib=$(( weights_bytes / 1024 + 5242880 ))
if [ "${AIWS_MODEL_SKIP_RAM_CHECK:-0}" != "1" ] && [ "$avail_kib" -lt "$need_kib" ]; then
   echo "Not enough free memory for the local model: need about $(( need_kib / 1024 )) MiB, have $(( avail_kib / 1024 )) MiB. Use the host GPU model channel or give this virtual machine more RAM. / 可用内存不足：需要约 $(( need_kib / 1024 )) MiB，现有 $(( avail_kib / 1024 )) MiB。请使用宿主显卡模型通道，或给虚拟机增加内存。" >&2
   exit 75
fi
ctx="${AIWS_MODEL_CTX:-8192}"
case "$ctx" in ''|*[!0-9]*) ctx=8192 ;; esac
if [ "$ctx" -lt 2048 ] || [ "$ctx" -gt 32768 ]; then ctx=8192; fi
req_timeout="${AIWS_MODEL_REQUEST_TIMEOUT:-600}"
case "$req_timeout" in ''|*[!0-9]*) req_timeout=600 ;; esac
if [ "$req_timeout" -lt 30 ] || [ "$req_timeout" -gt 1800 ]; then req_timeout=600; fi
threads="${AIWS_MODEL_THREADS:-$(nproc 2>/dev/null || echo 4)}"
case "$threads" in ''|*[!0-9]*) threads=4 ;; esac
if [ "$threads" -lt 1 ] || [ "$threads" -gt 64 ]; then threads=4; fi
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
exec python3 /usr/local/lib/aiws/aiws_model_gate.py --listen-port 18080 --child-port 18081 --idle-seconds "$idle" --request-timeout "$req_timeout" $resident -- \
  llama-server --model "$model" --alias aiws-local \
  --host 127.0.0.1 --port 18081 --ctx-size "$ctx" --threads "$threads" \
  --gpu-layers 0 --parallel 1
