# 2026-11-20 21:31 · AIWS OS static regex test correction / 正则测试修复

## Change / 变更
Fix regex escaping in `os/verify/test_config.py`: match optional whitespace in guest sysctl key-value lines, rather than matching a literal backslash and letter s. This preserves the static security-baseline test's intended assertion.

## Files / 修改文件
- `os/verify/test_config.py` — correct the test's `\s` regex escape
- `docs/routine/2026-11-20_2131-fix-os-sysctl-regex.md` — this record

## Verification / 验证
Source-level review of the exact before/after line. GitHub Actions static suite and actual ISO boot results must be checked separately; neither is claimed as passed here.

## Limitations / 已知问题
Still no built/tested ISO, compiled custom kernel, Linux Agent host, or validated host isolation. Static regex checks are not security proofs.

## Next / 下一步
Run the static workflow; build and boot under KVM/Hyper-V; test sysctl application at runtime, license inventory and host/guest enforcement.
