# 2026-11-20 02:03 UTC — V0.7 Windows native execution-base verification

## What changed

Follow-up verification record for the V0.7 code-review repair commit `cefed22591f3809ab2c40ce2de9bd7b6b70212ce`. The repair was documented in `2026-11-20_0200-execution-base-review-hardening.md`; this note adds actual Windows CI evidence, not new code behavior.

## Verified checks

- [Native Windows Desktop EXE — Actions run 44657658528](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44657658528): **success**.
- Windows WPF compilation: **success**.
- Native core smoke tests (`dotnet run --project desktop/AIWorkstation.Core.SmokeTests/...`): **success**.
- Publish self-contained Windows x64 single-file executable: **success**.
- CI artifact upload: **success**, artifact `WindowsAIWorkstation-Native-win-x64` (ID `14594326644`).
- [Python & Windows checks — Actions run 44657658522](https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44657658522): **success**.
- Linux local legacy Python suite: **38 passing tests**.
- Extracted PE executable SHA-256: `1ec24275e938e5dd9eb7c7e63b64c50074abe1103f0fe020d1e8586726bf1f24`.

## Remaining caveats

- **No GUI acceptance test has been performed inside the user's actual Hyper-V Windows VM.** The Windows-hosted CI runner is not a substitute for local CLI authentication and desktop permissions tests.
- WPF CLI launching still starts independent official interactive programs; it does not supply provider API keys or observe every private provider-side request.
- Workspace preflight validation does not sandbox external CLI processes. Hyper-V checkpoint and a least-privilege Windows user remain recommended.
- This is an unsigned EXE; use the trusted build artifact and verify its SHA-256 before first execution.

## Next steps

1. Run the acceptance checklist in `docs/EXECUTION_BASE_REVIEW_V07.md` inside the Hyper-V guest.
2. Prioritize a truly policy-enforced Windows tool broker and explicit process/session lifecycle tracking before unattended operation.
3. Move WPF handlers into testable MVVM use-case services and evaluate transactional SQLite migration with explicit versioned backup/rollback.
4. Expand provider event adapters only where officially supported; do not bypass subscription authentication boundaries.


---

## 双语归档概要 / Bilingual archive synopsis (2026-11-20)

- **中文：** 历史主题：2026-11-20 02:03 UTC — V0.7 Windows native execution-base verification。保留本文当时的修改事实、测试结论和后续计划，不代表现行发行版重新验证。
- **English:** Historical entry on **verified**. The original implementation notes, verification outcomes and next steps remain intact; no fresh release verification is implied.
- [历史索引 / Chronology](README.md) · [当前版本 / Current release](../../README.md)
