# 2026-11-21 14:20 — README / docs / codebase structure cleanup

## Summary / 改动

- Replaced the accumulated, contradictory root README with a concise
  bilingual product entry for **Windows WPF** and **Linux AIWS OS**.
  Removed stale claims that the OS has no Agent/Broker, that the current
  Shell is Chromium kiosk-only, and that images have never been built.
  Current status distinguishes code, CI and physical acceptance.
- Rebuilt `docs/README.md` as a topic-oriented current documentation
  index, separating active engineering contracts from historical versions.
- Added `docs/CODEBASE_MAP.md`: actual directories, runtime ownership,
  trust boundaries, data flows, CI responsibilities and safe refactor rules.
- Added `docs/HISTORY.md` linking to the exact pre-cleanup Git commit
  and original README, so old prose is retained in Git history rather
  than duplicated in the current root README.
- Replaced outdated `os/README.md` with a current Debian/NixOS,
  Shell/Agent/Broker, model and firmware-oriented build guide.
- Added focused module guides at `desktop/README.md`,
  `os/runtime/README.md`, `os/debian/README.md`,
  and `os/model/README.md`.
- Updated routine index to point to this entry. Preserved historical
  design files at their existing paths to avoid breaking cross-document
  links; marked them historical in docs/HISTORY.md instead of claiming
  they describe current behavior.

## Files / 影响文件

README.md; docs/{README.md,CODEBASE_MAP.md,HISTORY.md};
os/{README.md,runtime/README.md,debian/README.md,model/README.md};
desktop/README.md; docs/routine/{README.md,
2026-11-21_1420-readme-docs-codebase-structure.md}.

## Verification / 验证

- Read actual Git tree, existing README/docs and runtime source modules.
- Verified current repository canonical name is
  Nimenta727/AIWK-OS (renamed from Windows-AI-Workstation).
- Verified root LICENSE currently says MIT; no license was silently changed.
- Verified preceding code SHA ffc39eaf29e4755ec5fb65a0a6d260d1d00f24e6
  has successful OS static and Python/Windows checks; Debian firmware
  acceptance was still in progress when reviewed.
- This is a **documentation-only** structure cleanup; no production
  source file paths, systemd units, runtime imports or build scripts
  were moved. Markdown link and full CI acceptance for this commit
  must be checked after publication.

## Known limits / 限制

- Historical versioned technical documents remain in the working tree
  for existing links; their original claims are not current guarantees.
- No Git history rewrite, forced push, release or third-party relicensing.
- No claim of hardware boot, mandatory OS sandbox or accepted 2B inference.

## Next / 下一步

1. Run a repository-wide internal Markdown link audit and migrate any
   obsolete historical pages only after their inbound references are fixed.
2. Review Debian ISO firmware matrix results and fix real failures,
   recording separate BIOS/UEFI evidence.
3. Refactor Python runtime package boundaries only with synchronized
   live-build paths, unit files, tests and real QEMU acceptance.
4. Continue independent Permission Broker worker-UID/LSM isolation,
   real 2B guest held-out evaluation and Windows→Linux history mapping.
