"""O2 backend: observatory summary, verdict rules, task overview, event endpoints, real local-model usage."""
import http.client
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_observatory as obs
from aiws_tasks import GuestTaskStore
from aiws_local_model import LocalPlanner
from aiws_workbench import make_server, HOST

def session(agent="claude", basis="reported-total", verified=True, status="ok", unrecognized=0, **tok):
    base = {"in": None, "out": None, "cacheRead": None, "cacheWrite": None}
    base.update(tok)
    return {"session": "x", "agent": agent, "status": status, "unrecognizedEvents": unrecognized,
            "tokens": {**base, "basis": basis, "verified": verified, "unknownUsageEvents": 0}}

def overview(**over):
    base = {"tasks": 2, "stages": {"completed": 3}, "needsApproval": [], "failures": [], "recent": [], "activity": []}
    base.update(over)
    return base

class PureTests(unittest.TestCase):
    def test_token_totals_never_guess(self):
        t = obs.token_totals([session(**{"in": 10, "out": 2}), session(basis="none"), session(**{"in": 5, "cacheRead": 7}, verified=False)])
        self.assertEqual((t["in"], t["out"], t["cacheRead"], t["cacheWrite"]), (15, 2, 7, None))
        self.assertEqual((t["knownSessions"], t["unknownSessions"], t["unverifiedSessions"]), (2, 1, 1))
        empty = obs.token_totals([session(basis="none")])
        self.assertEqual((empty["in"], empty["unknownSessions"]), (None, 1))
        self.assertEqual(obs.token_totals([])["in"], None)

    def test_supervisor_and_router_sessions_are_not_counted_as_unknown_usage(self):
        t = obs.token_totals([session("claude", **{"in": 5}), session("supervisor", basis="none"), session("router", basis="none")])
        self.assertEqual((t["in"], t["knownSessions"], t["unknownSessions"]), (5, 1, 0))
        self.assertEqual(set(obs.token_by_agent([session("supervisor", basis="none"), session("local", basis="none")])), {"local"})
        ok = {"valid": True, "events": 1}
        self.assertEqual(obs.verdict(ok, overview(), [session("supervisor", basis="none")])["level"], "green")

    def test_token_by_agent(self):
        by = obs.token_by_agent([session("claude", **{"in": 1}), session("codex", **{"in": 2}), session("claude", **{"in": 3})])
        self.assertEqual((by["claude"]["in"], by["codex"]["in"]), (4, 2))

    def test_verdict_levels(self):
        ok_audit = {"valid": True, "events": 40}
        self.assertEqual(obs.verdict(ok_audit, overview(), [session()])["level"], "green")
        self.assertEqual(obs.verdict({"valid": False, "events": 3}, overview(), [])["level"], "red")
        yellow = [overview(stages={"failed": 1}), overview(needsApproval=[{"x": 1}]), overview()]
        self.assertEqual(obs.verdict(ok_audit, yellow[0], [])["level"], "yellow")
        self.assertEqual(obs.verdict(ok_audit, yellow[1], [])["level"], "yellow")
        self.assertEqual(obs.verdict(ok_audit, yellow[2], [session(basis="none")])["level"], "yellow")      # unknown usage
        self.assertEqual(obs.verdict(ok_audit, yellow[2], [session(status="error")])["level"], "yellow")
        self.assertEqual(obs.verdict(ok_audit, yellow[2], [session(unrecognized=2)])["level"], "yellow")
        red = obs.verdict({"valid": False}, overview(stages={"failed": 5}), [])
        self.assertEqual(red["level"], "red")                                                                # red is never downgraded

    def test_verdict_sentences_are_bounded_bilingual_and_honest(self):
        v = obs.verdict({"valid": True, "events": 9}, overview(), [session(basis="none")])
        self.assertLessEqual(len(v["sentences"]), 3)
        for s in v["sentences"]:
            self.assertTrue(s["zh"] and s["en"])
        self.assertIn("不会被估算", json.dumps(v, ensure_ascii=False))

class OverviewTests(unittest.TestCase):
    def test_task_overview(self):
        with tempfile.TemporaryDirectory() as t:
            store = GuestTaskStore(Path(t) / "s")
            try:
                self.assertEqual(store.overview(), {"tasks": 0, "stages": {}, "needsApproval": [], "failures": [], "recent": [], "activity": []})
                stages = [{"key": "a", "label": "read", "tool": "system.info", "arguments": {}, "dependsOn": []},
                          {"key": "b", "label": "mkdir", "tool": "file.mkdir", "arguments": {"path": "d"}, "dependsOn": ["a"]},
                          {"key": "c", "label": "mkdir2", "tool": "file.mkdir", "arguments": {"path": "e"}, "dependsOn": []}]
                doc = store.create("demo", "", stages)
                o = store.overview()
                self.assertEqual((o["tasks"], o["stages"]), (1, {"pending": 3}))
                ready = {x["stageKey"]: x["ready"] for x in o["needsApproval"]}
                self.assertEqual(ready, {"b": False, "c": True})          # b still waits for its read stage
                tid = doc["task"]["id"]
                store.dispatch(tid, "a"); store.started(tid, "a"); store.finished(tid, "a", {"ok": 1})
                self.assertTrue(next(x for x in store.overview()["needsApproval"] if x["stageKey"] == "b")["ready"])
                store.approve(tid, "c"); store.dispatch(tid, "c"); store.started(tid, "c"); store.finished(tid, "c", error="boom")
                o = store.overview()
                self.assertEqual(o["failures"][0]["error"], "boom")
                self.assertNotIn("c", [x["stageKey"] for x in o["needsApproval"]])
                self.assertTrue(o["activity"] and o["recent"][0]["stages"])
                self.assertLessEqual(len(o["activity"]), 12)
            finally:
                store.close()

class MockLlama(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"ok"}')
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        body = {"choices": [{"message": {"content": json.dumps({"tool": "system.info", "arguments": {}, "reason": "check"})}}],
                "usage": {"prompt_tokens": 321, "completion_tokens": 17}}
        data = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "workspace"; self.root.mkdir()
        self.ui = base / "ui"; (self.ui / "assets").mkdir(parents=True)
        (self.ui / "index.html").write_text("<html><head></head><body></body></html>")
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root), "XDG_STATE_HOME": str(base / "state")})
        self.env.start()
        self.cfg = patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {"claude": True, "codex": True},
                                                                "extraLocalKeywords": [], "extraExternalKeywords": []})
        self.cfg.start()
        self.bcfg = patch("aiws_workbench.load_builder_config", lambda: {"enabled": False, "envAllow": []})
        self.bcfg.start()
        self.start_server()

    def start_server(self):
        self.server = make_server(self.root, self.ui, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.hdr = {"X-AIWS-CSRF": self.req("GET", "/api/v1/session")[1]["csrf"]}

    def stop_server(self):
        self.server.shutdown(); self.thread.join(timeout=3); self.server.server_close()
        self.server.application.pool.shutdown(wait=True, cancel_futures=True)
        time.sleep(0.2)
        self.server.application.tasks.close()
        self.server.application.events.close()

    def tearDown(self):
        self.stop_server()
        self.cfg.stop(); self.bcfg.stop(); self.env.stop(); self.temp.cleanup()

    def req(self, method, path, payload=None, headers=None):
        conn = http.client.HTTPConnection(HOST, self.server.server_port, timeout=5)
        hdr = {"Host": HOST + ":" + str(self.server.server_port)}
        hdr.update(headers or {})
        if payload is not None:
            payload = json.dumps(payload); hdr["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=hdr)
        r = conn.getresponse(); body = json.loads(r.read()); conn.close()
        return r.status, body

    def test_empty_summary_shape(self):
        status, s = self.req("GET", "/api/v1/observatory")
        self.assertEqual(status, 200)
        self.assertFalse(s["demo"])
        self.assertEqual(s["verdict"]["level"], "green")
        self.assertEqual(s["tasks"]["tasks"], 0)
        self.assertIsNone(s["tokens"]["total"]["in"])
        self.assertEqual(s["status"]["builder"]["state"], "disabled")
        self.assertIsNone(s["tokens"]["budget"])
        self.assertFalse(s["status"]["router"]["externalEnabled"])

    def test_real_local_usage_is_captured_and_instruction_text_is_not(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), MockLlama)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            self.server.application.model = LocalPlanner(enabled=True, port=httpd.server_port)
            status, doc = self.req("POST", "/api/v1/model/plan", {"instruction": "看看系统信息 UNIQUE-PRIVATE-WORDS"}, self.hdr)
            self.assertEqual(status, 202, doc)
            time.sleep(0.5)
            s = self.req("GET", "/api/v1/observatory")[1]
            local = next(x for x in s["sessions"] if x["agent"] == "local")
            self.assertEqual((local["tokens"]["in"], local["tokens"]["out"], local["tokens"]["basis"]), (321, 17, "sum-of-reported"))
            self.assertTrue(any(x["agent"] == "router" for x in s["sessions"]))
            blob = (Path(self.temp.name) / "state/aiws-observatory/events.sqlite3").read_bytes()
            self.assertNotIn(b"UNIQUE-PRIVATE-WORDS", blob)
        finally:
            httpd.shutdown(); httpd.server_close()

    def test_unknown_usage_when_model_reports_none(self):
        plan = LocalPlanner.validate({"tool": "system.info", "arguments": {}, "reason": "check"})
        with patch.object(self.server.application.model, "suggest", return_value=plan):
            self.req("POST", "/api/v1/model/plan", {"instruction": "看看系统信息"}, self.hdr)
        s = self.req("GET", "/api/v1/observatory")[1]
        local = next(x for x in s["sessions"] if x["agent"] == "local")
        self.assertEqual((local["tokens"]["in"], local["tokens"]["basis"]), (None, "none"))
        self.assertEqual(s["verdict"]["level"], "yellow")          # unknown usage lowers the light, honestly

    def test_event_store_failure_never_breaks_a_request(self):
        plan = LocalPlanner.validate({"tool": "system.info", "arguments": {}, "reason": "check"})
        with patch.object(self.server.application.model, "suggest", return_value=plan), \
                patch.object(self.server.application.events, "append", side_effect=sqlite3.OperationalError("disk full")):
            status, doc = self.req("POST", "/api/v1/model/plan", {"instruction": "看看系统信息"}, self.hdr)
        self.assertEqual(status, 202, doc)

    def test_needs_approval_inbox_and_activity(self):
        stage = {"key": "mk", "label": "make folder", "tool": "file.mkdir", "arguments": {"path": "docs"}, "dependsOn": []}
        status, doc = self.req("POST", "/api/v1/tasks", {"title": "folder", "goal": "", "stages": [stage]}, self.hdr)
        tid = doc["task"]["id"]
        s = self.req("GET", "/api/v1/observatory")[1]
        self.assertEqual([x["stageKey"] for x in s["tasks"]["needsApproval"]], ["mk"])
        self.assertEqual(s["verdict"]["level"], "yellow")
        base = "/api/v1/tasks/" + tid + "/stages/mk/"
        self.req("POST", base + "approve", {}, self.hdr); self.req("POST", base + "dispatch", {}, self.hdr)
        for _ in range(100):
            s = self.req("GET", "/api/v1/observatory")[1]
            if s["tasks"]["stages"].get("completed"):
                break
            time.sleep(0.05)
        self.assertEqual(s["tasks"]["needsApproval"], [])
        self.assertTrue(any("stage.completed" in x["label"] for x in s["recent"]))
        self.assertEqual(s["verdict"]["level"], "green")

    def test_events_endpoint_validation(self):
        for bad in ("/api/v1/observatory/events", "/api/v1/observatory/events?session=bad%20id",
                    "/api/v1/observatory/events?session=" + "a" * 70, "/api/v1/observatory/events?session=ok&after=x",
                    "/api/v1/observatory/events?session=ok&after=-1"):
            self.assertEqual(self.req("GET", bad)[0], 400, bad)
        self.assertEqual(self.req("GET", "/api/v1/observatory/events?session=none")[1]["events"], [])

    def test_demo_seeding_is_opt_in_and_labelled(self):
        self.stop_server()
        with patch.dict(os.environ, {"AIWS_OBSERVATORY_DEMO": "1"}):
            self.start_server()
        s = self.req("GET", "/api/v1/observatory")[1]
        self.assertTrue(s["demo"])
        names = {x["session"] for x in s["sessions"]}
        self.assertTrue({"demo-claude", "demo-codex", "demo-codex-failed"} <= names)
        events = self.req("GET", "/api/v1/observatory/events?session=demo-claude")[1]["events"]
        self.assertTrue(events)
        self.assertNotIn("SENTINEL", json.dumps(events))

    def test_endpoints_are_read_only(self):
        self.assertEqual(self.req("POST", "/api/v1/observatory", {}, self.hdr)[0], 404)

class AgentOverviewTests(unittest.TestCase):
    def test_overview_over_agent_ipc(self):
        import socket
        if not hasattr(socket, "SO_PEERCRED"):
            self.skipTest("Linux peer credentials required")
        sys.path.insert(0, str(ROOT / "verify"))
        import test_agent_service as tas
        case = tas.StandaloneAgentTests("test_new_local_read_tools_pass_agent_and_broker")
        case.setUp()
        try:
            case.client.request("task.create", {"title": "t", "goal": "", "stages": [
                {"key": "a", "label": "a", "tool": "file.mkdir", "arguments": {"path": "x"}, "dependsOn": []}]})
            o = case.client.request("task.overview")
            self.assertEqual((o["tasks"], len(o["needsApproval"])), (1, 1))
        finally:
            case.tearDown()

if __name__ == "__main__":
    unittest.main()
