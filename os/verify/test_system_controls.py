"""System controls: closed command set, validated tokens, no shell, no secret on argv, power needs confirmation."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_system as S

XRANDR = """Screen 0: minimum 320 x 200, current 1920 x 1080
Virtual-1 connected primary 1920x1080+0+0 (normal left inverted) 0mm x 0mm
   1920x1080     60.00*+
   1280x720      60.00
   640x480       60.00
HDMI-1 disconnected (normal left inverted)
"""
WIFI = "Home\\:5G:80:WPA2:*\nCafe:45:WPA2:\nOpen:30::\nHome\\:5G:60:WPA2:\n:10:WPA2:\n"

class Fake:
    def __init__(self, outputs=None, missing=()):
        self.calls, self.outputs, self.missing = [], outputs or {}, set(missing)
    def run(self, argv, stdin=None, timeout=8):
        self.calls.append((list(argv), stdin))
        return self.outputs.get(tuple(argv), (0, "", ""))
    def which(self, name):
        return None if name in self.missing else "/usr/bin/" + name
    def ctl(self):
        return S.SystemControls(run=self.run, which=self.which)

class DisplayTests(unittest.TestCase):
    def fake(self):
        return Fake({("xrandr", "--query"): (0, XRANDR, "")})
    def test_only_connected_outputs_and_current_mode(self):
        out = self.fake().ctl().display_status()["outputs"]
        self.assertEqual([o["name"] for o in out], ["Virtual-1"])
        self.assertEqual(out[0]["current"], "1920x1080")
        self.assertIn("1280x720", out[0]["modes"])
    def test_set_only_advertised_modes(self):
        f = self.fake(); c = f.ctl()
        self.assertEqual(c.display_set("Virtual-1", "1280x720")["mode"], "1280x720")
        self.assertEqual(f.calls[-1][0], ["xrandr", "--output", "Virtual-1", "--mode", "1280x720"])
        for out, mode in (("Virtual-1", "3840x2160"), ("HDMI-1", "1280x720"), ("--help", "1280x720"),
                          ("Virtual-1", "1280x720; reboot"), ("Virtual-1", "")):
            with self.assertRaises(S.SystemError_):
                c.display_set(out, mode)
        self.assertEqual(sum(1 for a, _ in f.calls if "--mode" in a), 1)   # rejected requests ran nothing

class ImeTests(unittest.TestCase):
    def test_status_reports_missing_and_running(self):
        self.assertFalse(Fake(missing=["fcitx5-remote"]).ctl().ime_status()["installed"])
        f = Fake({("fcitx5-remote",): (0, "2\n", ""), ("fcitx5-remote", "-n"): (0, "pinyin\n", "")})
        st = f.ctl().ime_status()
        self.assertTrue(st["running"] and st["composing"]); self.assertEqual(st["active"], "pinyin")
    def test_not_running_when_daemon_absent(self):
        self.assertFalse(Fake({("fcitx5-remote",): (1, "", "")}).ctl().ime_status()["running"])
    def test_set_validates_name(self):
        f = Fake(); c = f.ctl()
        c.ime_set("pinyin"); self.assertEqual(f.calls[0][0], ["fcitx5-remote", "-s", "pinyin"])
        for bad in ("", "-x", "a b", "a;b", "x" * 60, None):
            with self.assertRaises(S.SystemError_):
                c.ime_set(bad)

class NetworkTests(unittest.TestCase):
    def fake(self):
        return Fake({("nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"):
                     (0, "wlan0:wifi:connected:Home\neth0:ethernet:unavailable:\nlo:loopback:unmanaged:\n", ""),
                     ("nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "device", "wifi", "list"): (0, WIFI, "")})
    def test_parse_dedupes_sorts_and_unescapes(self):
        rows = S.SystemControls.parse_wifi(WIFI)
        self.assertEqual([r["ssid"] for r in rows], ["Home:5G", "Cafe", "Open"])
        self.assertTrue(rows[0]["inUse"] and rows[1]["secured"] and not rows[2]["secured"])
    def test_status_lists_only_real_devices(self):
        st = self.fake().ctl().network_status()
        self.assertEqual([d["device"] for d in st["devices"]], ["wlan0", "eth0"])
    def test_password_goes_to_stdin_never_argv(self):
        f = self.fake(); c = f.ctl()
        c.network_connect("Cafe", "hunter2hunter2")
        argv, stdin = f.calls[-1]
        self.assertNotIn("hunter2hunter2", " ".join(argv)); self.assertEqual(stdin, "hunter2hunter2\n")
        self.assertIn("--ask", argv)
    def test_rejects_unscanned_option_like_and_bad_passwords(self):
        c = self.fake().ctl()
        for ssid, pw in (("Unknown", None), ("-x", None), ("Cafe\n", None), ("", None), ("Cafe", "short"), ("Cafe", "a" * 64),
                         ("Cafe", "bad\npassword1")):
            with self.assertRaises(S.SystemError_, msg=(ssid, pw)):
                c.network_connect(ssid, pw)

class PowerTests(unittest.TestCase):
    def test_requires_confirmation_and_known_action(self):
        f = Fake(); c = f.ctl()
        for action, confirm in (("poweroff", None), ("poweroff", "yes"), ("halt", S.CONFIRM), ("; reboot", S.CONFIRM)):
            with self.assertRaises(S.SystemError_):
                c.power(action, confirm)
        self.assertEqual(f.calls, [])
        self.assertTrue(c.power("reboot", S.CONFIRM)["accepted"])
        self.assertEqual(f.calls[-1][0], ["systemctl", "reboot"])

class FailureTests(unittest.TestCase):
    def test_missing_binary_and_nonzero_exit_are_clean_errors(self):
        with self.assertRaises(S.SystemError_):
            Fake(missing=["xrandr"]).ctl().display_status()
        with self.assertRaises(S.SystemError_):
            Fake({("xrandr", "--query"): (1, "", "Can't open display")}).ctl().display_status()
    def test_status_never_raises(self):
        st = Fake(missing=["xrandr", "fcitx5-remote", "nmcli"]).ctl().status()
        self.assertIn("error", st["display"]); self.assertFalse(st["input"]["installed"]); self.assertFalse(st["network"]["installed"])

if __name__ == "__main__":
    unittest.main()


# ---- HTTP layer ----
import http.client, json, os, tempfile, threading, time
from unittest.mock import patch
from aiws_workbench import make_server, HOST

class SystemApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); base = Path(self.temp.name)
        self.root = (base / "workspace"); self.root.mkdir(); self.root = self.root.resolve()
        ui = base / "ui"; (ui / "assets").mkdir(parents=True); (ui / "index.html").write_text("<html><head></head><body></body></html>")
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root), "XDG_STATE_HOME": str(base / "state")}); self.env.start()
        self.cfgs = [patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {}, "extraLocalKeywords": [], "extraExternalKeywords": []}),
                     patch("aiws_workbench.load_builder_config", lambda: {"enabled": False, "envAllow": [], "isolation": {"mode": "none", "user": "x", "proxy": "http://127.0.0.1:3128"}})]
        [p.start() for p in self.cfgs]
        self.server = make_server(self.root, ui, 0)
        self.fake = Fake({("xrandr", "--query"): (0, XRANDR, "")})
        self.server.application.system = self.fake.ctl()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.hdr = {"X-AIWS-CSRF": json.loads(self.raw("GET", "/api/v1/session")[1])["csrf"]}
    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        a = self.server.application; a.pool.shutdown(wait=True, cancel_futures=True); time.sleep(0.2)
        a.tasks.close(); a.events.close(); a.mandates.close()
        [p.stop() for p in self.cfgs]; self.env.stop(); self.temp.cleanup()
    def raw(self, method, path, payload=None, headers=None):
        c = http.client.HTTPConnection(HOST, self.server.server_port, timeout=10)
        h = {"Host": HOST + ":" + str(self.server.server_port), **(headers or {})}
        body = None
        if payload is not None:
            body = json.dumps(payload); h["Content-Type"] = "application/json"
        c.request(method, path, body=body, headers=h); r = c.getresponse(); data = r.read(); c.close()
        return r.status, data
    def test_status_is_readable_and_never_raises(self):
        status, data = self.raw("GET", "/api/v1/system")
        self.assertEqual(status, 200); self.assertEqual(json.loads(data)["display"]["outputs"][0]["name"], "Virtual-1")
    def test_mutations_need_csrf_and_exact_fields(self):
        self.assertEqual(self.raw("POST", "/api/v1/system/display", {"output": "Virtual-1", "mode": "1280x720"})[0], 403)
        self.assertEqual(self.raw("POST", "/api/v1/system/display", {"output": "Virtual-1", "mode": "1280x720", "x": 1}, self.hdr)[0], 400)
        self.assertEqual(self.raw("POST", "/api/v1/system/nothing", {"a": 1}, self.hdr)[0], 404)
    def test_power_without_confirmation_runs_nothing(self):
        status, _ = self.raw("POST", "/api/v1/system/power", {"action": "poweroff"}, self.hdr)
        self.assertGreaterEqual(status, 400)
        self.assertFalse([c for c, _ in self.fake.calls if c[0] == "systemctl"])
    def test_display_change_goes_through(self):
        status, data = self.raw("POST", "/api/v1/system/display", {"output": "Virtual-1", "mode": "1280x720"}, self.hdr)
        self.assertEqual(status, 202, data); self.assertEqual(json.loads(data)["mode"], "1280x720")
