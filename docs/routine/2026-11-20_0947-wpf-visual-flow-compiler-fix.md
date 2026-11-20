# 2026-11-20 09:47 +0800 — Fix WPF inspector layout for V0.6 call-flow

## Change summary

- Windows CI exposed `MC3089`: `ScrollViewer` accepts one content child, whereas the new inspector added a second sibling `StackPanel`.
- Wrapped step inspector and call-flow inspector in one `Grid`; visibility toggles retain the existing right-side panel behavior.
- Duplicate-launch warning now requires evidence of a prior CLI launch, rather than triggering merely because the user copied the same prompt before its first run.
- Adjusted duplicate-preparation counter so a warning event does not double-count the associated copied prompt.

## Files modified

- `desktop/AIWorkstation.Desktop/MainWindow.xaml`
- `desktop/AIWorkstation.Desktop/MainWindow.xaml.cs`
- `desktop/AIWorkstation.Core/CallFlow.cs`
- `docs/routine/2026-11-20_0947-wpf-visual-flow-compiler-fix.md`

## Verification

- XAML XML parser and local event-handler scan passed after fix.
- Full native Windows CI compile and smoke tests pending the follow-up commit.

## Next steps

1. Push fix, verify WPF compile, core tests and EXE artifact in GitHub Actions.
2. Open the binary in a test Hyper-V guest to check scrolling, node inspection and import usability.
3. Add supported provider event streaming where available, without claiming arbitrary subscription API access.


---

## 双语归档概要 / Bilingual archive synopsis (2026-11-20)

- **中文：** 历史主题：2026-11-20 09:47 +0800 — Fix WPF inspector layout for V0.6 call-flow。保留本文当时的修改事实、测试结论和后续计划，不代表现行发行版重新验证。
- **English:** Historical entry on **fix**. The original implementation notes, verification outcomes and next steps remain intact; no fresh release verification is implied.
- [历史索引 / Chronology](README.md) · [当前版本 / Current release](../../README.md)
