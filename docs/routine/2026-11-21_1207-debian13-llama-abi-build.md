# 2026-11-21 12:07 — Build llama.cpp against exact Debian 13 guest glibc ABI

## Verified root cause
GitHub real Qwen3.5-2B run 44851840543 verified model download/checksum and container file permissions, but the new ldd diagnostic reported:
    /usr/local/bin/llama-server: /lib/x86_64-linux-gnu/libm.so.6: version GLIBC_2.43 not found
The binary had been compiled on a newer Ubuntu runner and was loaded in a Debian 13 trixie runtime with an older glibc. Hence no inference occurred.

## Changes
- Add os/model/ci/Dockerfile.builder using debian:trixie-slim to build the EXACT pinned upstream llama.cpp source commit for the target Debian 13 runtime ABI, without GPU backend.
- Modify .github/workflows/aiws-real-model.yml: clone+pin source, compile inside Debian builder Docker image, extract llama-server binary, check exact SHA, then run existing non-root isolated Debian 13 offline inference and ldd checks, followed by optional full guest ISO/QEMU inference.
- Keep model source SHA256 and no-network runtime unchanged. This fixes a binary compatibility failure, not a model-quality assertion.
- Update docs/routine/README.md.

## Acceptance
The rerun must show successful real llama-server /health, actual structured response, and measured CPU/RSS latency. A successful container is not a replacement for actual QEMU Linux guest inference. EFI A/B fallback still requires its own real firmware receipt.
