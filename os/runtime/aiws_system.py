"""System controls of the AIWS shell: display, input method, network, power.

With no desktop panel, these are the only way a user (or the local model) changes the machine, so the surface is
deliberately small and closed:
  * every command is a FIXED argv template; request values are only ever validated tokens substituted into it
    (never a shell string, never an option-looking argument);
  * read operations (`status`) never change anything;
  * `power` needs the literal confirmation token, and `network.connect` never accepts a password on the command
    line (it is passed on stdin to a helper that reads it, so it is not visible in the process list).
All executions go through an injectable `run` so tests never touch the real system.
"""
import re
import shutil
import subprocess

MODE_RE = re.compile(r"^[0-9]{3,5}x[0-9]{3,5}$")
OUTPUT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,31}$")
IM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,47}$")
SSID_MAX = 32
POWER_ACTIONS = {"poweroff": ["systemctl", "poweroff"], "reboot": ["systemctl", "reboot"]}
CONFIRM = "I-CONFIRM"
TIMEOUT = 8


class SystemError_(Exception):
    """Raised for a rejected or failed system operation; the message is safe to show."""


def _default_run(argv, stdin=None, timeout=TIMEOUT):
    proc = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout, shell=False,
                          stdin=None if stdin is not None else subprocess.DEVNULL)
    return proc.returncode, proc.stdout, proc.stderr


class SystemControls:
    def __init__(self, run=None, which=None):
        self._run = run or _default_run
        self._which = which or shutil.which

    # ---- helpers ----
    def _exec(self, argv, stdin=None):
        if not self._which(argv[0]):
            raise SystemError_(argv[0] + " is not available in this image")
        try:
            code, out, err = self._run(argv, stdin=stdin)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SystemError_("Command failed: " + type(exc).__name__)
        if code != 0:
            raise SystemError_((err or out or "command failed").strip().splitlines()[0][:160] if (err or out) else "command failed")
        return out

    # ---- display ----
    @staticmethod
    def parse_xrandr(text):
        outputs, current = [], None
        for line in text.splitlines():
            m = re.match(r"^(\S+) (connected|disconnected)", line)
            if m:
                current = {"name": m.group(1), "connected": m.group(2) == "connected", "modes": [], "current": None}
                outputs.append(current)
                continue
            m = re.match(r"^\s+(\d{3,5}x\d{3,5})\s+(.*)$", line)
            if m and current is not None:
                current["modes"].append(m.group(1))
                if "*" in m.group(2):
                    current["current"] = m.group(1)
        return [o for o in outputs if o["connected"]]

    def display_status(self):
        return {"outputs": self.parse_xrandr(self._exec(["xrandr", "--query"]))}

    def display_set(self, output, mode):
        if not OUTPUT_RE.fullmatch(output or "") or not MODE_RE.fullmatch(mode or ""):
            raise SystemError_("Invalid output or mode")
        known = {o["name"]: o for o in self.display_status()["outputs"]}
        if output not in known or mode not in known[output]["modes"]:
            raise SystemError_("That output/mode is not offered by the display")   # only advertised modes
        self._exec(["xrandr", "--output", output, "--mode", mode])
        return {"output": output, "mode": mode}

    # ---- input method (fcitx5) ----
    def ime_status(self):
        installed = bool(self._which("fcitx5-remote"))
        if not installed:
            return {"installed": False, "running": False, "active": None, "groups": []}
        try:
            code, out, _ = self._run(["fcitx5-remote"])
        except (OSError, subprocess.TimeoutExpired):
            return {"installed": True, "running": False, "active": None, "groups": []}
        state = out.strip()
        running = code == 0 and state in ("0", "1", "2")
        active = None
        if running:
            try:
                _, name, _ = self._run(["fcitx5-remote", "-n"])
                active = name.strip()[:48] or None
            except (OSError, subprocess.TimeoutExpired):
                pass
        return {"installed": True, "running": running, "active": active,
                "composing": state == "2" if running else False, "groups": []}

    def ime_set(self, name):
        if not IM_RE.fullmatch(name or ""):
            raise SystemError_("Invalid input method name")
        self._exec(["fcitx5-remote", "-s", name])
        return self.ime_status()

    # ---- network (NetworkManager) ----
    @staticmethod
    def parse_wifi(text):
        rows, seen = [], set()
        for line in text.splitlines():
            parts = re.split(r"(?<!\\):", line)
            if len(parts) < 4:
                continue
            ssid = parts[0].replace("\\:", ":")
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            rows.append({"ssid": ssid[:SSID_MAX], "signal": int(parts[1]) if parts[1].isdigit() else None,
                         "secured": parts[2] not in ("", "--"), "inUse": parts[3] == "*"})
        rows.sort(key=lambda r: (not r["inUse"], -(r["signal"] or 0)))
        return rows[:30]

    def network_status(self):
        if not self._which("nmcli"):
            return {"installed": False, "devices": [], "wifi": []}
        devices = []
        try:
            code, out, _ = self._run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
            for line in out.splitlines() if code == 0 else []:
                p = line.split(":")
                if len(p) >= 4 and p[1] in ("ethernet", "wifi"):
                    devices.append({"device": p[0], "type": p[1], "state": p[2], "connection": p[3] or None})
        except (OSError, subprocess.TimeoutExpired):
            pass
        wifi = []
        if any(d["type"] == "wifi" for d in devices):
            try:
                code, out, _ = self._run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "device", "wifi", "list"])
                wifi = self.parse_wifi(out) if code == 0 else []
            except (OSError, subprocess.TimeoutExpired):
                pass
        return {"installed": True, "devices": devices, "wifi": wifi}

    def network_connect(self, ssid, password=None):
        if not isinstance(ssid, str) or not 1 <= len(ssid.encode("utf-8")) <= SSID_MAX or ssid.startswith("-") \
                or any(ord(c) < 32 for c in ssid):
            raise SystemError_("Invalid network name")
        if password is not None and (not isinstance(password, str) or not 8 <= len(password) <= 63
                                     or any(ord(c) < 32 for c in password)):
            raise SystemError_("Wi-Fi password must be 8–63 printable characters")
        if ssid not in {r["ssid"] for r in self.network_status()["wifi"]}:
            raise SystemError_("That network was not seen in the last scan")
        argv = ["nmcli", "--ask", "device", "wifi", "connect", ssid] if password else ["nmcli", "device", "wifi", "connect", ssid]
        self._exec(argv, stdin=(password + "\n") if password else None)   # --ask reads the secret from stdin
        return {"connected": ssid}

    # ---- power ----
    def power(self, action, confirm):
        if action not in POWER_ACTIONS:
            raise SystemError_("Unknown power action")
        if confirm != CONFIRM:
            raise SystemError_("Confirmation required")
        self._exec(POWER_ACTIONS[action])
        return {"action": action, "accepted": True}

    # ---- summary used by the shell ----
    def status(self):
        out = {}
        for key, fn in (("display", self.display_status), ("input", self.ime_status), ("network", self.network_status)):
            try:
                out[key] = fn()
            except SystemError_ as exc:
                out[key] = {"error": str(exc)[:160]}
        return out
