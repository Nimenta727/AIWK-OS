# 2026-11-21 13:45 — MCP 只读契约回归与 ISO 构建执行位恢复

## What changed / 实际修复

1. Restored the Git executable mode **100755** on
   os/debian/build.sh, accidentally changed to 100644 by the previous
   atomic Git tree update. The real Debian image job failed before the
   build started with "/os/debian/build.sh: Permission denied"; this
   is a packaging error, not an ISO boot result.
2. Added executable-mode guards to os/verify/test_config.py and the
   Debian image workflow before a costly disposable image build.
3. Updated offline code-symbol MCP tests to use a **mock transport**
   for a guest Agent, asserting delegation to the exact tool.read
   arguments. The test now asserts absence of Agent fails closed.
4. Updated cross-platform MCP tests: direct project.scaffold calls
   must now be denied even when its legacy opt-in flag is present.
   Only platform.inspect remains exposed via mocked read-only Agent.
   The low-level source scaffold unit tests remain unchanged, but
   it is not part of the public MCP service contract.

## Evidence / verified before fix

- [OS static failing run](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44865974504):
  101 tests, exactly two failed: test_codeintel.test_mcp_end_to_end_and_optional_schema
  and test_crossplatform.test_mcp_call_and_rejection. Both expected
  the obsolete direct MCP bypass.
- [Debian image failing run](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44865974471):
  builder terminated with shell exit 126 "Permission denied"; NixOS
  evaluation passed but firmware jobs skipped because ISO was not built.
- Python/Windows checks for the previous commit passed; this does not
  substitute for rerunning the corrected OS static and firmware jobs.
- **New commit regression and ISO acceptance pending until new CI completes.**

## Next / 下一步

1. Confirm exact commit passes OS static, Windows checks and Debian build,
   then independently check BIOS and UEFI QEMU ISO firmware/GUI receipts.
2. If image boots fail, use per-firmware serial and El Torito reports to
   isolate BIOS/GRUB vs Linux session/clipboard/Agent failures; do not
   incorrectly mark direct-kernel boot as firmware pass.
3. Add true separate-UID execution worker and OS-enforced confinement,
   then test alternate-tool and same-UID bypass attempts.
4. Continue real 2B held-out model metrics and Windows→Linux audit-history
   mapping without treating source imports as new executable permissions.
