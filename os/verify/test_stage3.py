"""Stage 3: local-only system/network/download read tools, model tool grading, multi-step plans."""
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME))
import aiws_toolplane as plane
import aiws_tasks
import aiws_local_model as lm
from aiws_local_model import LocalPlanner, LocalModelError, stages_from_proposal
from aiws_permission_broker import DIRECT_READ
from aiws_workbench import make_server, HOST

def step(tool, reason="r", **args):
    return {"tool": tool, "arguments": args, "reason": reason}

class LocalReadToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aiws-stage3-")
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.old = os.environ.get("AIWS_WORKSPACE")
        os.environ["AIWS_WORKSPACE"] = str(self.root)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("AIWS_WORKSPACE", None)
        else:
            os.environ["AIWS_WORKSPACE"] = self.old
        self.temp.cleanup()

    def inv(self, name, **a):
        return plane.invoke(name, a)

    def test_classification_is_single_sourced_and_read_only(self):
        new = {"system.info", "network.status", "download.list", "download.progress"}
        self.assertTrue(new <= plane.READ_TOOLS)
        self.assertTrue(new <= DIRECT_READ)
        self.assertTrue(new <= aiws_tasks.TOOLS)
        self.assertFalse(new & aiws_tasks.WRITE_TOOLS)
        self.assertTrue(new <= lm.READ_TOOLS)
        # nothing network-capable or executing is ever offered to the model
        for bad in ("browser.snapshot", "runtime.test", "project.scaffold", "file.replace"):
            self.assertNotIn(bad, lm.READ_TOOLS | lm.MODEL_WRITE_TOOLS)
        self.assertFalse(lm.READ_TOOLS & plane.FILE_WRITE_TOOLS)

    def test_system_info(self):
        info = self.inv("system.info")
        self.assertIn("memory", info)
        self.assertIsInstance(info["memory"]["totalBytes"], int)
        self.assertGreater(info["workspaceDisk"]["totalBytes"], 0)
        self.assertEqual(set(info["kernel"]), {"system", "release", "machine"})

    def test_network_status_opens_no_socket_and_sends_nothing(self):
        def forbidden(*a, **k):
            raise AssertionError("network.status must not create sockets")
        with patch.object(socket, "socket", forbidden), \
                patch.object(socket, "create_connection", forbidden), \
                patch.object(socket, "getaddrinfo", forbidden):
            status = self.inv("network.status")
        self.assertFalse(status["activeProbe"])
        self.assertIn("lo", [i["name"] for i in status["interfaces"]])
        self.assertIn("tcp", status["sockets"])

    def test_network_parsers(self):
        files = {
            "/proc/net/route": "Iface\tDestination\tGateway\tFlags\neth0\t00000000\t0102A8C0\t0003\neth0\t0002A8C0\t00000000\t0001\n",
            "/proc/net/fib_trie": "Local:\n  +-- 10.0.2.0/24 2 0 2\n     |-- 10.0.2.15\n        /32 host LOCAL\n     |-- 10.0.2.255\n        /32 link BROADCAST\n  +-- 127.0.0.0/8 2 0 2\n     |-- 127.0.0.1\n        /32 host LOCAL\n",
            "/etc/resolv.conf": "# c\nnameserver 10.0.2.3\nsearch lan\n",
            "/proc/net/tcp": "  sl  local_address rem_address   st\n   0: 0100007F:1F90 00000000:0000 0A\n   1: 0F02000A:C350 22020A0A:01BB 01\n",
            "/proc/net/tcp6": "  sl  local_address rem_address   st\n",
        }
        with patch.object(plane, "_proc", lambda path, limit=0: files.get(path, "")):
            self.assertEqual(plane._default_route(), {"interface": "eth0", "gateway": "192.168.2.1"})
            self.assertEqual(plane._local_ipv4(), ["10.0.2.15", "127.0.0.1"])
            s = plane._socket_summary()
            self.assertEqual(s["tcp"]["established"], 1)
            self.assertEqual(s["listeningPorts"], [8080])
            self.assertEqual(plane._network_status(self.root, {})["dnsServers"], ["10.0.2.3"])

    def test_download_list_and_states(self):
        self.assertEqual(self.inv("download.list")["downloads"], [])
        d = self.root / "downloads"
        d.mkdir()
        (d / "done.iso").write_bytes(b"x" * 10)
        (d / "big.bin.part").write_bytes(b"y" * 5)
        (d / "tool.zip").write_bytes(b"z")
        (d / "tool.zip.aria2").write_bytes(b"c")
        (d / "done.iso.progress.json").write_text('{"totalBytes": 10}')
        (d / ".hidden").write_text("h")
        os.symlink("/etc/passwd", d / "link")
        out = self.inv("download.list")
        states = {x["path"]: x["state"] for x in out["downloads"]}
        self.assertEqual(states["downloads/done.iso"], "complete")
        self.assertEqual(states["downloads/big.bin.part"], "partial")
        self.assertEqual(states["downloads/tool.zip"], "partial")       # aria2 control file marks it
        self.assertNotIn("downloads/done.iso.progress.json", states)
        self.assertNotIn("downloads/.hidden", states)
        self.assertNotIn("downloads/link", states)
        self.assertFalse(out["canDownload"])
        self.assertEqual(out["partialCount"], 3)

    def test_download_progress_growth_percent_and_eta(self):
        d = self.root / "downloads"
        d.mkdir()
        part = d / "a.iso.part"
        part.write_bytes(b"x" * 100)
        (d / "a.iso.part.progress.json").write_text('{"totalBytes": 1000}')
        def grow(seconds):                       # the external downloader writes while we sample
            with part.open("ab") as f:
                f.write(b"y" * 50)
        with patch.object(plane.time, "sleep", grow):
            p = self.inv("download.progress", path="downloads/a.iso.part")
        self.assertEqual(p["state"], "partial")
        self.assertEqual(p["sizeBytes"], 150)
        self.assertEqual(p["bytesPerSecond"], 100)
        self.assertEqual(p["percent"], 15.0)
        self.assertEqual(p["etaSeconds"], 9)
        (d / "ok.bin").write_bytes(b"1234")
        done = self.inv("download.progress", path="downloads/ok.bin")
        self.assertEqual((done["state"], done["percent"]), ("complete", 100.0))

    def test_download_progress_rejects_other_paths(self):
        (self.root / "downloads").mkdir()
        (self.root / "secret.txt").write_text("s")
        for bad in ("secret.txt", "downloads/../secret.txt", "downloads/sub/x", "downloads", "/etc/passwd"):
            with self.assertRaises((ValueError, PermissionError, FileNotFoundError)):
                self.inv("download.progress", path=bad)

    def test_model_unit_is_network_denied_and_loopback_only(self):
        unit = (ROOT / "debian/config/includes.chroot/etc/systemd/user/aiws-local-model.service").read_text()
        self.assertIn("IPAddressDeny=any", unit)
        self.assertIn("IPAddressAllow=localhost", unit)
        script = (ROOT / "model/aiws-local-model.sh").read_text()
        self.assertIn("--host 127.0.0.1", script)
        self.assertEqual(lm.HOST, "127.0.0.1")

class ModelGradingTests(unittest.TestCase):
    def test_write_proposals_are_graded_and_need_approval(self):
        for tool, args in (("file.mkdir", {"path": "d"}), ("file.copy", {"path": "a", "to": "b"}),
                           ("file.move", {"path": "a", "to": "b"}), ("file.trash", {"path": "a"}),
                           ("file.restore", {"trashId": "a" * 32})):
            v = LocalPlanner.validate(step(tool, **args))
            self.assertEqual((v["grade"], v["requiresApproval"], v["executed"]), ("write", True, False))
        r = LocalPlanner.validate(step("system.info"))
        self.assertEqual((r["grade"], r["requiresApproval"]), ("read", False))

    def test_model_cannot_supply_fingerprints_contents_or_permanent_delete(self):
        bad = [step("file.move", path="a", to="b", expectedSha256="0" * 64),
               step("file.replace", path="a", text="x", expectedSha256=""),
               step("file.delete", path="a"), step("file.remove", path="a"), step("download.start", url="https://x"),
               step("file.move", path="a"), step("file.move", path="/etc/x", to="b"),
               step("file.move", path="a", to="../b"), step("file.move", path="a", to=".git/x"),
               step("file.trash", path=".aiws-trash/x"), step("file.restore", trashId="../x"),
               step("network.status", host="example.com"), step("browser.snapshot", url="https://example.com")]
        for item in bad:
            with self.assertRaises(LocalModelError, msg=item):
                LocalPlanner.validate(item)

    def test_plan_validation(self):
        ok = {"steps": [step("system.info"), step("file.mkdir", path="d")], "reason": "go"}
        v = LocalPlanner.validate_any(ok)
        self.assertEqual((v["tool"], v["grade"], v["requiresApproval"]), ("plan", "write", True))
        self.assertEqual(LocalPlanner.validate_any({"steps": [step("system.info")], "reason": "x"})["grade"], "read")
        for bad in ({"steps": [], "reason": "x"},
                    {"steps": [step("system.info")] * 9, "reason": "x"},
                    {"steps": [step("refuse")], "reason": "x"},
                    {"steps": [step("system.info")], "reason": "x", "extra": 1},
                    {"steps": "nope", "reason": "x"}):
            with self.assertRaises(LocalModelError):
                LocalPlanner.validate_any(bad)
        self.assertEqual(LocalPlanner.validate_any(step("refuse"))["tool"], "refuse")

    def test_canonical_roundtrip_regression(self):
        """The Agent revalidates raw model shape; the validated dict itself is NOT valid input."""
        for raw in (step("file.stat", path="a"), {"steps": [step("system.info"), step("file.trash", path="a")], "reason": "x"}):
            checked = LocalPlanner.validate_any(raw)
            self.assertEqual(LocalPlanner.canonical(checked), raw)
            self.assertEqual(LocalPlanner.validate_any(LocalPlanner.canonical(checked))["tool"], checked["tool"])
        with self.assertRaises(LocalModelError):
            LocalPlanner.validate(LocalPlanner.validate(step("file.stat", path="a")))

    def test_stage_building_computes_fingerprints_and_chains(self):
        shas = {"a.txt": "a" * 64, "b.txt": "b" * 64}
        plan = LocalPlanner.validate_any({"steps": [
            step("system.info"), step("file.mkdir", path="docs"),
            step("file.move", path="a.txt", to="docs/a.txt"), step("file.trash", path="b.txt")], "reason": "tidy"})
        stages = stages_from_proposal(plan, lambda p: {"sha256": shas[p]})
        self.assertEqual([s["key"] for s in stages], ["step1", "step2", "step3", "step4"])
        self.assertEqual([s["dependsOn"] for s in stages], [[], ["step1"], ["step2"], ["step3"]])
        self.assertEqual(stages[2]["arguments"]["expectedSha256"], "a" * 64)
        self.assertEqual(stages[3]["arguments"]["expectedSha256"], "b" * 64)
        self.assertNotIn("expectedSha256", stages[1]["arguments"])
        single = stages_from_proposal(LocalPlanner.validate(step("system.info")), None)
        self.assertEqual(single[0]["key"], "inspect")

    def test_stage_building_refuses_stale_or_missing_sources(self):
        stat = lambda p: {"sha256": "c" * 64}
        for steps in ([step("file.move", path="a", to="b"), step("file.trash", path="a")],
                      [step("file.move", path="a", to="b"), step("file.move", path="b", to="c")],
                      [step("file.mkdir", path="d"), step("file.move", path="d/x", to="y")],
                      [step("file.move", path="dir", to="z"), step("file.trash", path="dir/inner")]):
            plan = LocalPlanner.validate_any({"steps": steps, "reason": "x"})
            with self.assertRaises(LocalModelError, msg=steps):
                stages_from_proposal(plan, stat)
        def missing(p):
            raise FileNotFoundError(p)
        with self.assertRaises(LocalModelError):
            stages_from_proposal(LocalPlanner.validate(step("file.trash", path="gone")), missing)
        # copy does not change its source, so the source may be used again afterwards
        ok = LocalPlanner.validate_any({"steps": [step("file.copy", path="a", to="b"), step("file.trash", path="a")], "reason": "x"})
        self.assertEqual(len(stages_from_proposal(ok, stat)), 2)

class WorkbenchPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "workspace"
        self.root.mkdir()
        self.ui = base / "ui"
        (self.ui / "assets").mkdir(parents=True)
        (self.ui / "index.html").write_text("<html><head></head><body></body></html>")
        (self.root / "a.txt").write_text("alpha")
        (self.root / "b.txt").write_text("beta")
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root), "XDG_STATE_HOME": str(base / "state")})
        self.env.start()
        self.server = make_server(self.root, self.ui, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.server.application.pool.shutdown(wait=True, cancel_futures=True)
        time.sleep(0.2)
        self.server.application.tasks.close()
        self.env.stop()
        self.temp.cleanup()

    def req(self, method, path, payload=None, headers=None):
        conn = http.client.HTTPConnection(HOST, self.server.server_port, timeout=5)
        hdr = {"Host": HOST + ":" + str(self.server.server_port)}
        hdr.update(headers or {})
        if payload is not None:
            payload = json.dumps(payload)
            hdr["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=hdr)
        r = conn.getresponse()
        body = json.loads(r.read())
        conn.close()
        return r.status, body

    def wait(self, tid, key, states=("completed", "failed")):
        for _ in range(300):
            s = next(x for x in self.req("GET", "/api/v1/tasks/" + tid)[1]["stages"] if x["stage_key"] == key)
            if s["state"] in states:
                return s
            time.sleep(0.02)
        self.fail("timeout " + key)

    def test_multistep_plan_reads_run_writes_wait_for_approval(self):
        hdr = {"X-AIWS-CSRF": self.req("GET", "/api/v1/session")[1]["csrf"]}
        plan = LocalPlanner.validate_any({"steps": [
            step("system.info", "check disk"), step("file.mkdir", "make folder", path="docs"),
            step("file.move", "file it", path="a.txt", to="docs/a.txt"),
            step("file.trash", "drop b", path="b.txt")], "reason": "tidy workspace"})
        with patch.object(self.server.application.model, "suggest", return_value=plan):
            status, doc = self.req("POST", "/api/v1/model/plan", {"instruction": "tidy"}, hdr)
        self.assertEqual(status, 202, doc)
        tid = doc["task"]["id"]
        self.assertEqual([s["tool"] for s in doc["stages"]], ["system.info", "file.mkdir", "file.move", "file.trash"])
        self.assertEqual(self.wait(tid, "step1")["state"], "completed")      # read-only: automatic
        time.sleep(0.4)
        self.assertEqual(self.wait(tid, "step2", ("pending", "queued", "running", "completed"))["state"], "pending")
        self.assertFalse((self.root / "docs").exists())                      # write waits for approval
        move = next(s for s in self.req("GET", "/api/v1/tasks/" + tid)[1]["stages"] if s["stage_key"] == "step3")
        import hashlib
        self.assertEqual(move["arguments"]["expectedSha256"], hashlib.sha256(b"alpha").hexdigest())
        base = "/api/v1/tasks/" + tid + "/stages/"
        self.assertEqual(self.req("POST", base + "step3/dispatch", {}, hdr)[0], 400)   # deps + approval
        for key in ("step2", "step3", "step4"):
            self.assertEqual(self.req("POST", base + key + "/approve", {}, hdr)[0], 202)
            self.assertEqual(self.req("POST", base + key + "/dispatch", {}, hdr)[0], 202)
            self.assertEqual(self.wait(tid, key)["state"], "completed", key)
        self.assertEqual((self.root / "docs/a.txt").read_text(), "alpha")
        self.assertFalse((self.root / "b.txt").exists())
        self.assertEqual([i["original"] for i in plane.invoke("file.trashList", {})["items"]], ["b.txt"])

    def test_plan_with_missing_source_is_refused_without_creating_a_task(self):
        hdr = {"X-AIWS-CSRF": self.req("GET", "/api/v1/session")[1]["csrf"]}
        plan = LocalPlanner.validate_any({"steps": [step("file.trash", path="nope.txt")], "reason": "x"})
        with patch.object(self.server.application.model, "suggest", return_value=plan):
            status, doc = self.req("POST", "/api/v1/model/plan", {"instruction": "x"}, hdr)
        self.assertEqual(status, 400, doc)
        self.assertEqual(self.req("GET", "/api/v1/tasks")[1]["tasks"], [])

    def test_context_lists_folders_for_the_model(self):
        (self.root / "docs").mkdir()
        ctx = self.server.application.local_guest_context()
        self.assertIn("docs/", ctx["guestFiles"])
        LocalPlanner.context_message(ctx)   # still valid bounded context

class ModelPlannerEndToEnd(unittest.TestCase):
    def test_planner_returns_validated_plan_from_mock_model(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        answer = {"steps": [step("download.list"), step("file.move", path="downloads/a.iso", to="isos/a.iso")], "reason": "sort downloads"}
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                data = json.dumps({"choices": [{"message": {"content": json.dumps(answer)}}]}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            result = LocalPlanner(enabled=True, port=httpd.server_port).suggest("sort my downloads")
        finally:
            httpd.shutdown(); httpd.server_close()
        self.assertEqual((result["tool"], len(result["steps"]), result["grade"]), ("plan", 2, "write"))
        self.assertFalse(result["executed"])

if __name__ == "__main__":
    unittest.main()
