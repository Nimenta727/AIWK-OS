"""Guest system tools of the tool plane: system and network status, downloads, git, runtimes, local browser text.

Read-only views of the guest. Dispatched by aiws_toolplane.invoke; not called directly from outside the plane.
"""
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import time
from urllib.parse import urlsplit
from aiws_toolplane import DETECT_TOOLS, _path, _command, _safe_env


def _proc(path, limit=262144):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as stream:
            return stream.read(limit)
    except OSError:
        return ""

def _meminfo():
    wanted = {"MemTotal": "totalBytes", "MemAvailable": "availableBytes",
              "SwapTotal": "swapTotalBytes", "SwapFree": "swapFreeBytes"}
    out = {v: None for v in wanted.values()}
    for line in _proc("/proc/meminfo").splitlines():
        key, _, rest = line.partition(":")
        if key in wanted and rest.split():
            try:
                out[wanted[key]] = int(rest.split()[0]) * 1024
            except ValueError:
                pass
    return out

def _system_info(root, a):
    name = None
    for line in _proc("/etc/os-release", 8192).splitlines():
        if line.startswith("PRETTY_NAME="):
            name = line.split("=", 1)[1].strip().strip('"')[:120]
    try:
        uname = os.uname()
        kernel = {"system": uname.sysname, "release": uname.release, "machine": uname.machine}
    except AttributeError:
        kernel = None
    try:
        uptime = float(_proc("/proc/uptime", 256).split()[0])
    except (IndexError, ValueError):
        uptime = None
    try:
        load = [round(x, 2) for x in os.getloadavg()]
    except (AttributeError, OSError):
        load = None
    try:
        usage = shutil.disk_usage(root)
        disk = {"totalBytes": usage.total, "usedBytes": usage.used, "freeBytes": usage.free}
    except OSError:
        disk = None
    return {"os": name, "kernel": kernel, "uptimeSeconds": uptime, "loadAverage": load,
            "cpuCount": os.cpu_count(), "memory": _meminfo(), "workspaceDisk": disk}

def _net_counters():
    out = {}
    for line in _proc("/proc/net/dev").splitlines()[2:]:
        name, _, rest = line.partition(":")
        fields = rest.split()
        if len(fields) >= 16:
            try:
                out[name.strip()] = {"rxBytes": int(fields[0]), "rxErrors": int(fields[2]),
                                     "txBytes": int(fields[8]), "txErrors": int(fields[10])}
            except ValueError:
                continue
    return out

def _local_ipv4():
    found, last = [], None
    for line in _proc("/proc/net/fib_trie").splitlines():
        text = line.strip()
        if text.startswith("|--"):
            last = text[3:].strip()
        elif text.startswith("/32 host LOCAL") and last and last not in found:
            found.append(last)
    return found[:16]

def _default_route():
    for line in _proc("/proc/net/route").splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 3 and cols[1] == "00000000":
            try:
                raw = bytes.fromhex(cols[2])[::-1]
                return {"interface": cols[0], "gateway": ".".join(str(b) for b in raw)}
            except ValueError:
                continue
    return None

def _socket_summary():
    states = {"01": "established", "0A": "listening", "06": "timeWait"}
    counts = {v: 0 for v in states.values()}
    listening = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        for line in _proc(table).splitlines()[1:]:
            cols = line.split()
            if len(cols) < 4 or cols[3] not in states:
                continue
            counts[states[cols[3]]] += 1
            if cols[3] == "0A":
                try:
                    listening.add(int(cols[1].rsplit(":", 1)[1], 16))
                except (IndexError, ValueError):
                    pass
    return {"tcp": counts, "listeningPorts": sorted(listening)[:32]}

def _network_status(root, a):
    """Reads kernel-exported local state only. Opens no socket and sends no packet."""
    first = _net_counters()
    time.sleep(0.4)
    second = _net_counters()
    names = []
    try:
        names = sorted(os.listdir("/sys/class/net"))[:32]
    except OSError:
        pass
    interfaces = []
    for name in names:
        state = _proc("/sys/class/net/" + name + "/operstate", 32).strip() or "unknown"
        item = {"name": name, "state": state}
        if name in first and name in second:
            item.update(second[name])
            item["rxBytesPerSecond"] = round((second[name]["rxBytes"] - first[name]["rxBytes"]) / 0.4)
            item["txBytesPerSecond"] = round((second[name]["txBytes"] - first[name]["txBytes"]) / 0.4)
        interfaces.append(item)
    dns = [l.split()[1] for l in _proc("/etc/resolv.conf", 8192).splitlines()
           if l.startswith("nameserver") and len(l.split()) > 1][:4]
    return {"interfaces": interfaces, "ipv4Addresses": _local_ipv4(),
            "defaultRoute": _default_route(), "dnsServers": dns,
            "sockets": _socket_summary(), "activeProbe": False}

DOWNLOAD_DIR = "downloads"
PARTIAL_SUFFIXES = (".crdownload", ".part", ".partial", ".download", ".tmp", ".aria2")
SIDECAR = ".progress.json"

def _downloads_dir(root):
    d = _path(root, DOWNLOAD_DIR, allow_missing=True)
    return d if d.is_dir() and not d.is_symlink() else None

def _download_state(directory, name):
    if name.lower().endswith(PARTIAL_SUFFIXES):
        return "partial"
    return "partial" if (directory / (name + ".aria2")).exists() else "complete"

def _download_list(root, a):
    directory = _downloads_dir(root)
    items = []
    if directory is not None:
        for entry in directory.iterdir():
            if entry.is_symlink() or not entry.is_file() or entry.name.endswith(SIDECAR) \
                    or entry.name.startswith("."):
                continue
            st = entry.stat()
            items.append({"path": DOWNLOAD_DIR + "/" + entry.name[:200],
                          "state": _download_state(directory, entry.name),
                          "sizeBytes": st.st_size, "mtime": int(st.st_mtime)})
        items.sort(key=lambda x: (-x["mtime"], x["path"]))
    return {"directory": DOWNLOAD_DIR, "downloads": items[:200],
            "partialCount": sum(1 for x in items if x["state"] == "partial"),
            "canDownload": False}

def _download_progress(root, a):
    value = a["path"]
    if not isinstance(value, str) or Path(value).parts[:1] != (DOWNLOAD_DIR,) or len(Path(value).parts) != 2:
        raise ValueError("Path must be a file directly inside downloads/")
    p = _path(root, value)
    if p.is_symlink() or not p.is_file() or p.name.endswith(SIDECAR):
        raise ValueError("Not a regular download file")
    state = _download_state(p.parent, p.name)
    size = p.stat().st_size
    result = {"path": value, "state": state, "sizeBytes": size, "mtime": int(p.stat().st_mtime),
              "bytesPerSecond": None, "totalBytes": None, "percent": None, "etaSeconds": None}
    sidecar = p.parent / (p.name + SIDECAR)
    if sidecar.is_file() and not sidecar.is_symlink() and sidecar.stat().st_size <= 4096:
        try:
            total = json.loads(sidecar.read_text(encoding="utf-8")).get("totalBytes")
            if isinstance(total, int) and not isinstance(total, bool) and total > 0:
                result["totalBytes"] = total
        except (ValueError, OSError, AttributeError):
            pass
    if state == "partial":
        time.sleep(0.5)
        later = p.stat().st_size if p.exists() else size
        result["bytesPerSecond"] = max(0, round((later - size) / 0.5))
        size = later
        result["sizeBytes"] = later
    if result["totalBytes"]:
        result["percent"] = min(100.0, round(size * 100.0 / result["totalBytes"], 1))
        if state == "partial" and result["bytesPerSecond"]:
            result["etaSeconds"] = max(0, math.ceil((result["totalBytes"] - size) / result["bytesPerSecond"]))
    elif state == "complete":
        result["percent"] = 100.0
    return result

def _tools_list(root, a):
    import aiws_apps
    return {"apps": aiws_apps.listing(), "runtime": {name: shutil.which(name) for name in DETECT_TOOLS}}

def _git(root, a):
    if a.get("view", "status") not in ("status", "diff"):
        raise ValueError("Only git status and diff are available")
    if not shutil.which("git"):
        raise ValueError("Git not installed")
    args = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
            "-c", "diff.external=", "-c", "protocol.ext.allow=never"]
    if a.get("view", "status") == "status":
        args += ["status", "--short", "--untracked-files=normal"]
    else:
        args += ["diff", "--no-ext-diff", "--no-textconv", "--"]
    return _command(root, args)

LANGUAGES = {
    "python": ["python3", "-m", "unittest", "discover"],
    "node": ["npm", "test", "--if-present"],
    "go": ["go", "test", "./..."],
    "rust": ["cargo", "test", "--offline"],
    "java": ["mvn", "-o", "test"],
    "cpp": ["cmake", "--build", "build"],
}

def _runtime(root, a):
    if a.get("language") not in LANGUAGES:
        raise ValueError("Unrecognized language test profile")
    if os.environ.get("AIWS_ALLOW_EXEC") != "1":
        raise PermissionError("Execution disabled; owner must explicitly enable AIWS_ALLOW_EXEC=1 in guest session")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise PermissionError("Agent test execution must not run as guest root")
    args = LANGUAGES[a["language"]]
    if not shutil.which(args[0]):
        raise FileNotFoundError("Tool not installed: " + args[0])
    return _command(root, args, timeout=90)

class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignore = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.ignore += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.ignore:
            self.ignore -= 1
    def handle_data(self, data):
        if not self.ignore and data.strip():
            self.parts.append(data.strip())

def _extract(html):
    parser = _Text()
    parser.feed(html[:256000])
    return "\n".join(parser.parts)[:16000]

def _browser(root, a):
    url = a["url"]
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("Invalid URL")
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("Only explicitly allowlisted HTTP(S) origins are supported")
    origin = parsed.scheme + "://" + parsed.netloc.lower()
    allow = {x.strip().lower() for x in os.environ.get("AIWS_BROWSER_ALLOWED_ORIGINS", "").split(",") if x.strip()}
    if origin not in allow:
        raise PermissionError("Browser disabled for this origin; host network must be separately controlled")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise PermissionError("Headless browser must run as an ordinary guest user with sandbox enabled")
    if not shutil.which("chromium") or not shutil.which("chromedriver"):
        raise FileNotFoundError("Debian chromium/chromium-driver are required")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
    except ImportError as error:
        raise RuntimeError("Debian python3-selenium is required") from error
    options = Options()
    options.binary_location = shutil.which("chromium")
    options.add_argument("--headless=new")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-background-networking")
    with tempfile.TemporaryDirectory(prefix="aiws-browser-") as profile:
        options.add_argument("--user-data-dir=" + profile)
        service = Service(executable_path=shutil.which("chromedriver"), env=_safe_env())
        driver = webdriver.Chrome(service=service, options=options)
        try:
            driver.set_page_load_timeout(15)
            driver.get(url)
            final = urlsplit(driver.current_url)
            final_origin = final.scheme + "://" + final.netloc.lower()
            if final_origin not in allow:
                raise PermissionError("Redirected outside allowed origins; host egress rules are required")
            return {"url": driver.current_url, "title": driver.title[:300],
                    "text": _extract(driver.page_source), "source": "headless-chromium-dom"}
        finally:
            driver.quit()
