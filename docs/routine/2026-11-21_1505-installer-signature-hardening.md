# 2026-11-21 15:05 — Installer preflight signature hardening

## Changed
- Reject installation candidates carrying existing filesystem, partition table, partition UUID, filesystem UUID, or any mountpoint signatures.
- Request these fields explicitly from lsblk; do not assume missing child partitions means a blank disk.
- Rename the report field to `candidateUnpartitionedDisks` to avoid representing candidates as safe/empty.
- Add negative contract tests for each signature and synchronize installer safety documentation.

## Verification
- Source and unit tests committed; CI on this SHA is pending.
- Previous SHA `cd62ba96` passed OS static contracts and Python/Windows checks; its real Debian image/VM acceptance was still running at review time.
- No disk writes, no installation or recovery implemented. A signature-free device can still contain important data.

## Next steps
1. Run disposable qcow2 + OVMF boot integration and preserve real CI artifacts.
2. Add a read-only interactive disk authorization design and only then implement a VM-only installation path.
3. Verify ISO-independent boot, persisted /home, failed-update rollback and separate-UID worker.
