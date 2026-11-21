# AIWS OS: Guest OS, kernel, privileged Agent and host isolation / 客户机操作系统、内核与隔离

**2026-11-20 | P0 design plus image recipe, not an audited operating system.**

## 1. Product identity / 产品定位

This is a **standalone Linux guest operating system**, not a Windows launcher. Windows AIWS remains a compatibility host. The target architecture is:

```text
Host (Windows Hyper-V or hardened Linux KVM/libvirt)
  |- hypervisor-enforced: guest disk, CPU/RAM, virtual devices, network policy
  |- no host shares / credential passthrough / management API to guest
  +-- AIWS OS guest (Debian base, custom kernel package later)
       |- Desktop session: XFCE initially; integrated AIWS desktop shell later
       |- Browser: Firefox ESR (web origin isolated from admin control)
       |- IDE/reader: Geany + Git / LSP-based index planned
       |- languages: Python, Node, Java, Rust, Go, C/C++ from Debian main
       |- ordinary-user Agent tasks and worktrees (future Linux adapter)
       |- audited privilege broker (future): capability, approval, expiry, receipts
       +-- explicit interactive guest root: aiws-admin-session (initial manual gate)
```

## 2. What is implemented NOW / 当前代码实际包含

- Debian 13 live-build ISO recipe for an amd64 XFCE guest; single host-independent package list.
- Bundled browser, code editor and multi-language build tool packages.
- Guest runtime sysctls improving symbol/process visibility protection and inotify capacity.
- **Design-only** custom kernel fragment: virtio (block/net/console/RNG/GPU), cgroups, namespaces, overlayfs, AppArmor, Landlock, seccomp and audit. These options have not been validated on a compiled Debian kernel.
- Interactive root shell gate requiring a detected VM, TTY, typed confirmation and sudo; **not** automatically offered to a browser or external Agent.
- Offline-by-default QEMU KVM test launcher: unprivileged host process, no NIC, read-only ISO, no host share or management channel, seccomp option. The host must additionally enforce filesystem, cgroup/CPU/RAM and VM process isolation.
- Static regression tests. No real boot, CI ISO build, security certification or Windows Hyper-V testing yet.

## 3. Privilege design / 权限与安全不冲突的前提

**Highest guest permission is not host permission.** A guest-root Agent could disable guest firewall/sysctls and erase the guest disk. For that reason never rely on security measures controlled by guest root to protect the host.

**Required outside the guest:**
1. Hypervisor updated/patched; QEMU launched unprivileged under host MAC/sandbox (SELinux/AppArmor/sVirt where available); Hyper-V guest integration limited and audited.
2. No host path passthrough (9p/virtiofs/SMB), direct USB/GPU/device passthrough, auto mount, host clipboard injection, shared credential store or host management IPC by default.
3. Default VM network disabled. A future network-enabled mode requires host-enforced egress segmentation, explicit access policy and host/LAN metadata endpoint protections; guest root may not re-enable a disconnected virtual NIC.
4. Per-VM disks and snapshots, immutable base images, backup/restore and isolated non-admin host account.
5. Host-approved *import/export* of exact files via a mediated channel (never write access to an entire host folder). Forensics and execution receipts must also be retained outside guest.
6. Resource quotas (CPU, memory, storage, processes, network), vulnerability updates and adversarial test of VM escape/device emulation boundaries.

**Agent authority phases:** interactive manual guest root is available now; default unattended Agent runs are ordinary user only. Future *guest* privilege broker must bind operation/task/workspace/expiry/approval and record auditable receipts; allow an owner-selected all-guest-admin mode only in a disposable VM, with clear destructive scope. Browser content must never directly call arbitrary privileged host or guest shell APIs.

## 4. Deep kernel coupling / 深度内核耦合

Design kernel packages rather than patching the hypervisor: use pinned Debian kernel source + a reviewed `aiws-kernel.fragment` and Debian packaging; upstream GPL obligations are preserved. Validate each proposed option against supported kernel, compile, boot, fallback kernel, and record `/proc/config.gz` or `/boot/config-*` at runtime. Add measured kernel trace events, cgroup v2 limits and audit correlation with Agent events; **do not** treat ebpf/perf tracing as provider-internal token measurements.

Performance is an evidence problem: measure cold boot, memory pressure, VM exits, disk I/O latency, file-index scans and concurrent Agent throughput before tuning governor, hugepages, swappiness or scheduler. A root Agent cannot be meaningfully restricted by guest sysctl alone.

## 5. Phased system integration / 分阶段实装

| Phase | Deliverable | Verification gate |
| --- | --- | --- |
| P0 current | Debian Live ISO recipe, GUI/tools, guest config, offline launch/tests | Static tests only; actual ISO build and boot pending |
| P1 | Reproducible ISO/VM disk, signed/checksummed artifacts, boot smoke on KVM + Hyper-V | boot/graphics/input/IME/recovery evidence |
| P2 | Port core Agent controller to Linux system daemon; embed React workbench into trusted desktop shell | same task data and API schema, no WPF dependency |
| P3 | Versioned guest-only privileged execution broker + journal/audit + rollback | permission and interruption tests, root/session separation |
| P4 | Pinned custom Debian kernel packages, trace/cgroup integration, safe fallback | kernel ABI/upgrade/boot tests and measurements |
| P5 | Host side boundary validation, segmented online networking, mediated file import/export | VM isolation tests and expert review |
| P6 | Distribution compliance and public release | complete SPDX SBOM, per-package notices and source-offer obligations |

## 6. Licensing / 许可清单

This repository's `LICENSE` file is now Apache-2.0 (changed 2026-11-21; it was MIT before). The migration still owes: confirmation of every contributor, preservation of the prior MIT terms for code that was already distributed under MIT and of adapted MIT-provenance UI (`third_party/t3code/NOTICE.md`), a root NOTICE file, and an SPDX inventory. The Linux kernel remains GPL-2.0-only; Debian userland mixes GPL, LGPL, MPL, Apache, MIT and other licenses; Debian `main` packaging does not eliminate redistribution obligations. We currently bundle **package names** and download from Debian build-time mirrors, not copied proprietary application binaries. Do not claim the generated ISO may be redistributed until the full dependency license/source audit and SBOM are done.

References: [Debian Live Manual](https://live-team.pages.debian.net/live-manual/html/live-manual.en.html), [Debian live-build](https://packages.debian.org/trixie/live-build), [QEMU guest isolation](https://www.qemu.org/docs/master/system/security.html).
