# 2026-11-20 00:20 +08:00 — Windows-native desktop build validated

## What changed

- Updated the project README to link to a successful native Windows CI build and distinguish downloadable EXE from source ZIP.
- Recorded Windows CI results and the SHA-256 hash of the shipped `WindowsAIWorkstation.exe`.

## Verification

- GitHub Actions run https://github.com/Nimenta727/Windows-AI-Workstation/actions/runs/44564333810 was **successful** for commit `e73848a6d741b53a4bec374b32444b7ab4e6704b`.
- Windows WPF GUI compilation succeeded; .NET core workflow smoke tests passed; Windows self-contained `win-x64` publish and artifact upload succeeded.
- Downloaded Actions artifact, extracted the nested ZIP, validated ZIP CRC and confirmed the EXE PE32+ x86-64 Windows GUI header.
- EXE SHA-256: `f07796889253998efdee13ea914e0331079022df99aa69faee2fdbaf31980691`.
- The EXE is unsigned; no claim is made that it has been launched in the user's actual Hyper-V Windows VM.

## Next steps

1. Open the native EXE in a Windows 11 Hyper-V guest as a non-admin user and review the real layout, DPI scaling, keyboard navigation and file picker.
2. Verify official Claude Code and Codex CLI interactive launch, workspace isolation and task handoff in that guest.
3. Implement a genuine freeform workflow DAG (branches, connections, retries) and an embedded terminal with supported agent protocols.
4. Add optional native companion integrations and a signed installer/secure update mechanism.
