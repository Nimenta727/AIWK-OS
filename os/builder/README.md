# Builder lane isolation (step O4)

Runs the official CLI as an **unprivileged sandbox user** whose only network path is a **domain-allowlist proxy**.
Everything here is **off by default**: set `{"enabled": true, "isolation": {"mode": "user"}}` in `~/.config/aiws/builder.json`.

## What the image contains
| File | Purpose |
| --- | --- |
| `usr/lib/sysusers.d/aiws-builder.conf` | no-login accounts `aiws-builder` (runs the CLI) and `aiws-egress` (runs the proxy) |
| `etc/aiws/builder-firewall.nft` | nftables: UID `aiws-builder` may reach **only** `127.0.0.1:3128`; everything else (internet, workbench, local model, DNS, IPv6) is dropped |
| `etc/systemd/system/aiws-builder-firewall.service` | loads the rules; writes `/run/aiws/builder-firewall.ok` only after success (the supervisor refuses to run without it) |
| `etc/systemd/system/aiws-egress-proxy.service` | hardened proxy (`runtime/aiws_egress_proxy.py`): CONNECT-only, port 443, allowlisted names, public addresses only |
| `etc/aiws/egress-allow.conf` | the domain allowlist (minimal, **unverified** starting point) |
| `etc/sudoers.d/aiws-builder` | the workbench user may run commands **only as** `aiws-builder` |
| `usr/local/sbin/aiws-builder-selftest` | root-run acceptance check for all of the above |

## How a run is isolated
1. The supervisor checks the firewall marker, then grants ACLs: traverse (`--x`) on the parent folders, read-write on **one** project folder, read-only on its `.git`.
2. It starts `sudo -n -u aiws-builder -- env -i <minimal env incl. HTTPS_PROXY> <cli ...>`; no shell is involved.
3. Pause/resume/kill are `sudo -u aiws-builder kill -STOP|-CONT|-TERM|-KILL -1` (one run at a time, so "all of that user's processes" is exactly the run).
4. ACLs are revoked when the run ends.

## One-time setup (not automated, not verified)
* Install the official CLI **system-wide** (e.g. under `/usr/local`) so the sandbox user can execute it.
* Log in **as the sandbox user** (its home is `/var/lib/aiws-builder/home`); your own login is never shared with it. Check the CLI vendor's current terms for programmatic use first.
* Run `sudo aiws-builder-selftest` (add `--online` to make the real-internet check mandatory).

## What is and is not proven
* **Proven here (tests):** the ruleset is valid nftables; in a throw-away network namespace a non-root UID under the rule reaches only the proxy port and root is unaffected; sudoers syntax; the proxy's policy (see `test_egress_proxy.py`); the supervisor's isolation wiring with a fake `sudo`.
* **NOT proven:** anything on a real guest image (users, ACL behaviour on the real filesystem, systemd ordering, the real CLI's needs, IPv6, the allowlist contents). `aiws-builder-selftest` is the acceptance step and has not been run on a real guest.
* **Limits by design:** the proxy limits *where* traffic goes, not *what* is sent. On the experimental live image the default `user` account already has passwordless root (live-config), so this boundary protects the host guest **from the CLI process**, not from a compromised workbench user (milestone M3).
