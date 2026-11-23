"""The assistant over HTTP: real workbench server, real stores, scripted model server. CSRF, validation, status codes, plan creation, events."""
import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "verify" / "fixtures"))
import aiws_assistant as AS
import aiws_events as E
import aiws_llm as L
import aiws_local_agent as A
from aiws_workbench import make_server, HOST
from fake_llm import FakeLLM, reply


def act(**kw):
    return reply(json.dumps(kw))


class Rig(unittest.TestCase):
    model_on = True

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = (base / "workspace")
        self.root.mkdir()
        self.root = self.root.resolve()
        ui = base / "ui"
        (ui / "assets").mkdir(parents=True)
        (ui / "index.html").write_text("<html><head></head><body></body></html>")
        env = {"AIWS_WORKSPACE": str(self.root), "XDG_STATE_HOME": str(base / "state"), "AIWS_SKILLS_DIR": str(base / "none"), "AIWS_PLUGINS_DIR": str(ROOT / "plugins"),
               "HOME": str(base / "home")}
        if self.model_on:
            env["AIWS_LOCAL_MODEL_ENABLED"] = "1"
        self.env = patch.dict(os.environ, env)
        self.env.start()
        if not self.model_on:
            os.environ.pop("AIWS_LOCAL_MODEL_ENABLED", None)
        self.patches = [patch("aiws_workbench.load_config", lambda: {"externalEnabled": False, "providers": {}, "extraLocalKeywords": [], "extraExternalKeywords": []}),
                        patch("aiws_workbench.load_builder_config", lambda: {"enabled": False, "envAllow": [], "isolation": {"mode": "none", "user": "x", "proxy": "http://127.0.0.1:3128"}}),
                        patch("aiws_toolplane.protect_guest_workspace", return_value=True)]
        [p.start() for p in self.patches]
        self.fake = FakeLLM().__enter__()
        self.server = make_server(self.root, ui, 0)
        self.app = self.server.application
        llm = L.LocalLLM(self.fake.url, timeout=20)
        self.app.assistant.llm = llm
        self.app.assistant.agent.llm = llm
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        self.app.pool.shutdown(wait=True, cancel_futures=True)
        for _ in range(60):
            if not A.RUN_LOCK.locked():
                break
            time.sleep(0.1)
        time.sleep(0.2)
        self.app.tasks.close(); self.app.events.close(); self.app.mandates.close()
        self.fake.__exit__(None, None, None)
        [p.stop() for p in self.patches]; self.env.stop(); self.temp.cleanup()

    def req(self, method, path, body=None, csrf=True, raw=None):
        c = http.client.HTTPConnection(HOST, self.server.server_port, timeout=15)
        headers = {"Host": HOST + ":" + str(self.server.server_port)}
        data = None
        if method == "POST":
            data = raw if raw is not None else json.dumps(body if body is not None else {}).encode()
            headers.update({"Content-Type": "application/json", "Content-Length": str(len(data))})
            if csrf:
                headers["X-AIWS-CSRF"] = self.app.csrf
        c.request(method, path, body=data, headers=headers)
        r = c.getresponse()
        d = r.read()
        c.close()
        return r.status, json.loads(d)

    def wait_done(self, thread_id, seconds=15):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            _, body = self.req("GET", "/api/v1/assistant/thread?id=" + thread_id)
            if not body["running"] and body["items"] and body["items"][-1]["type"] != "user":
                return body
            time.sleep(0.1)
        self.fail("the turn did not finish")


class Status(Rig):
    def test_status_lists_skills_commands_and_the_router_counters(self):
        s, body = self.req("GET", "/api/v1/assistant/status")
        self.assertEqual(s, 200)
        self.assertTrue(body["enabled"])
        self.assertIn("aiws-log-tools:read-log", [x["id"] for x in body["skills"]])
        self.assertIn("aiws-log-tools:log", [x["id"] for x in body["commands"]])
        self.assertEqual(body["route"]["decisions"], 0)
        self.assertIn("log.digest", body["tools"])
        self.assertEqual(set(body["limits"]), {"maxSteps", "maxCalls", "maxSeconds", "maxTextChars"})
        self.assertEqual(body["model"]["state"], "ready")

    def test_plugins_endpoint_lists_the_first_party_plugins_as_enabled(self):
        s, body = self.req("GET", "/api/v1/assistant/plugins")
        self.assertEqual(s, 200)
        by = {p["name"]: p for p in body["plugins"]}
        self.assertEqual({k: v["status"] for k, v in by.items()}, {"aiws-log-tools": "enabled", "aiws-secret-guard": "enabled"})
        self.assertEqual(by["aiws-log-tools"]["source"], "system")


class Off(Rig):
    model_on = False

    def test_a_turn_is_refused_cleanly_while_the_model_is_off(self):
        s, body = self.req("GET", "/api/v1/assistant/status")
        self.assertEqual((body["enabled"], body["model"]["state"]), (False, "off"))
        s, body = self.req("POST", "/api/v1/assistant/turn", {"text": "hello"})
        self.assertEqual(s, 503)
        self.assertIn("switched off", body["error"])
        self.assertEqual(self.fake.requests, [])                                   # the model was never contacted


class Turns(Rig):
    def test_csrf_and_payload_validation(self):
        self.assertEqual(self.req("POST", "/api/v1/assistant/turn", {"text": "hi"}, csrf=False)[0], 403)
        for body in ({}, {"text": 5}, {"text": ""}, {"text": "   "}, {"text": "x" * 2001}, {"text": "hi", "extra": 1}, {"text": "hi", "tier": "huge"}, {"text": "hi", "threadId": "nope"},
                     {"text": "hi", "threadId": 7}):
            s, _ = self.req("POST", "/api/v1/assistant/turn", body)
            self.assertEqual(s, 400, body)
        self.assertEqual(self.req("POST", "/api/v1/assistant/turn", raw=b"[1]")[0], 400)
        self.assertEqual(self.req("GET", "/api/v1/assistant/thread?id=../x")[0], 400)
        self.assertEqual(self.req("GET", "/api/v1/assistant/thread?id=aaaaaaaaaaaaaaaa")[0], 404)       # well formed but unknown

    def test_a_turn_runs_in_the_background_and_the_thread_shows_every_step(self):
        (self.root / "notes.txt").write_text("hello from notes")
        self.fake.push(act(type="call", tool="file.read", args={"path": "notes.txt"}), act(type="final", text="It says hello."))
        s, body = self.req("POST", "/api/v1/assistant/turn", {"text": "read notes.txt"})
        self.assertEqual((s, body["started"]), (202, True))
        thread = self.wait_done(body["threadId"])
        self.assertEqual([i["type"] for i in thread["items"]], ["user", "step", "observation", "step", "final"])
        self.assertTrue(all("prompt" not in i for i in thread["items"]))             # the large prompt is not shipped to the page
        obs = thread["items"][2]
        self.assertEqual((obs["tool"], obs["status"]), ("file.read", "ok"))
        self.assertIn("hello from notes", obs["text"])                                # the real tool plane read the real file
        self.assertEqual(thread["items"][-1]["text"], "It says hello.")
        self.assertEqual(self.req("GET", "/api/v1/assistant/threads")[1]["threads"][0]["title"], "read notes.txt")
        s, again = self.req("POST", "/api/v1/assistant/turn", {"text": "and now?", "threadId": body["threadId"]})
        self.fake.push(act(type="final", text="Nothing else."))
        self.assertEqual(s, 202)
        self.assertEqual(again["threadId"], body["threadId"])

    def test_a_second_turn_while_one_runs_is_refused_with_409(self):
        self.fake.push(reply(json.dumps({"type": "final", "text": "slow"}), delay=1.2))
        s, body = self.req("POST", "/api/v1/assistant/turn", {"text": "first"})
        self.assertEqual(s, 202)
        time.sleep(0.4)
        s, err = self.req("POST", "/api/v1/assistant/turn", {"text": "second"})
        self.assertEqual(s, 409)
        self.assertIn("another request", err["error"])
        self.wait_done(body["threadId"])

    def test_a_proposal_becomes_a_task_in_the_plan_review_area_and_nothing_is_moved(self):
        (self.root / "report.pdf").write_bytes(b"%PDF-1.4 test")
        steps = [{"tool": "file.move", "arguments": {"path": "report.pdf", "to": "docs/report.pdf"}, "reason": "tidy up"}]
        self.fake.push(act(type="call", tool="file.stat", args={"path": "report.pdf"}), act(type="propose", steps=steps, reason="Move the report"))
        s, body = self.req("POST", "/api/v1/assistant/turn", {"text": "move report.pdf into docs"})
        thread = self.wait_done(body["threadId"])
        for _ in range(30):                                                          # the plan item is appended right after the turn ends
            thread = self.req("GET", "/api/v1/assistant/thread?id=" + body["threadId"])[1]
            if thread["items"][-1]["type"] == "plan":
                break
            time.sleep(0.1)
        kinds = [i["type"] for i in thread["items"]]
        self.assertEqual(kinds[-2:], ["proposed", "plan"], kinds)
        proposed, plan = thread["items"][-2], thread["items"][-1]
        self.assertEqual(proposed["sources"], [{"tool": "file.stat", "path": "report.pdf"}])
        self.assertTrue((self.root / "report.pdf").exists())                         # not moved: it waits for approval
        self.assertFalse((self.root / "docs").exists())
        _, plans = self.req("GET", "/api/v1/plans")
        local = [p for p in plans["plans"] if p["source"] == "local"]
        self.assertTrue(any(p["id"] == plan["taskId"] for p in local), (plan, [p["id"] for p in local]))
        step = next(p for p in local if p["id"] == plan["taskId"])["steps"][-1]
        self.assertEqual((step["tool"], step["risk"], step["needsApproval"]), ("file.move", "medium", True))

    def test_turns_are_visible_in_the_observatory_as_the_local_agent(self):
        self.fake.push(act(type="call", tool="file.stat", args={"path": "x.txt"}), act(type="final", text="done"))
        s, body = self.req("POST", "/api/v1/assistant/turn", {"text": "stat x.txt"})
        self.wait_done(body["threadId"])
        time.sleep(0.3)
        rows = [r for r in self.app.events.sessions(50) if r["agent"] == "local" and r["session"].startswith("assistant-")]
        self.assertTrue(rows, self.app.events.sessions(50))
        events = self.app.events.events(rows[0]["session"], after=0, limit=50)
        self.assertEqual([e["kind"] for e in events][:1], ["start"])
        self.assertIn("tool", [e["kind"] for e in events])
        self.assertEqual(events[-1]["kind"], "end")
        self.assertEqual(events[-1]["detail"], "final")


class Routing(Rig):
    def test_route_records_the_decision_and_overrides_are_counted(self):
        self.fake.push(reply('{"tier":"flash"}'))
        s, d = self.req("POST", "/api/v1/assistant/route", {"text": "fix the failing test"})
        self.assertEqual((s, d["tier"], d["cloud"]["model"]), (202, "flash", "deepseek-flash"))
        self.assertEqual(self.req("GET", "/api/v1/assistant/status")[1]["route"]["decisions"], 1)
        s, stats = self.req("POST", "/api/v1/assistant/route/override", {"from": "flash", "to": "pro"})
        self.assertEqual((s, stats["overrides"], stats["overrideMatrix"]), (202, 1, {"flash>pro": 1}))
        for bad in ({"from": "flash", "to": "flash"}, {"from": "x", "to": "pro"}, {"from": "flash"}, {"from": "flash", "to": "pro", "x": 1}):
            self.assertEqual(self.req("POST", "/api/v1/assistant/route/override", bad)[0], 400, bad)
        for bad in ({}, {"text": 3}, {"text": ""}, {"text": "x", "y": 1}):
            self.assertEqual(self.req("POST", "/api/v1/assistant/route", bad)[0], 400, bad)

    def test_a_turn_that_completes_on_the_machine_is_counted_only_for_local_routes(self):
        self.fake.push(act(type="final", text="ok"), act(type="final", text="ok"))
        for tier in ("local", "flash"):
            s, body = self.req("POST", "/api/v1/assistant/turn", {"text": "hello", "tier": tier})
            self.wait_done(body["threadId"])
            time.sleep(0.3)
        self.assertEqual(self.req("GET", "/api/v1/assistant/status")[1]["route"]["localCompleted"], 1)


class Plugins(Rig):
    def test_enable_needs_the_shown_hash_and_disable_takes_effect_at_once(self):
        user = Path(os.environ["XDG_STATE_HOME"]) / "aiws" / "assistant" / "plugins" / "mine"
        (user / "skills" / "my-skill").mkdir(parents=True)
        (user / "skills" / "my-skill" / "SKILL.md").write_text("---\nname: my-skill\ndescription: Does my thing\n---\n1. do it\n")
        s, body = self.req("GET", "/api/v1/assistant/plugins")
        mine = next(p for p in body["plugins"] if p["name"] == "mine")
        self.assertEqual(mine["status"], "disabled")
        self.assertNotIn("mine:my-skill", [x["id"] for x in self.req("GET", "/api/v1/assistant/status")[1]["skills"]])
        for bad in ({"name": "mine", "treeSha256": "0" * 64}, {"name": "mine"}, {"name": "nope", "treeSha256": "0" * 64}, {"treeSha256": "x"}, {"name": 5}):
            self.assertEqual(self.req("POST", "/api/v1/assistant/plugins/enable", bad)[0], 400, bad)
        s, r = self.req("POST", "/api/v1/assistant/plugins/enable", {"name": "mine", "treeSha256": mine["treeSha256"]})
        self.assertEqual((s, r["status"]), (202, "enabled"))
        self.assertIn("mine:my-skill", [x["id"] for x in self.req("GET", "/api/v1/assistant/status")[1]["skills"]])
        s, r = self.req("POST", "/api/v1/assistant/plugins/disable", {"name": "mine"})
        self.assertEqual((s, r["status"]), (202, "disabled"))
        self.assertNotIn("mine:my-skill", [x["id"] for x in self.req("GET", "/api/v1/assistant/status")[1]["skills"]])
        self.assertEqual(self.req("POST", "/api/v1/assistant/plugins/disable", {"name": "mine", "x": 1})[0], 400)
        self.assertEqual(self.req("POST", "/api/v1/assistant/plugins/enable", {"name": "mine", "treeSha256": mine["treeSha256"]}, csrf=False)[0], 403)

    def test_the_secret_guard_blocks_a_dotenv_read_through_the_whole_stack(self):
        (self.root / ".env").write_text("TOKEN=hunter2")
        self.fake.push(act(type="call", tool="file.read", args={"path": ".env"}), act(type="final", text="I could not open it."))
        s, body = self.req("POST", "/api/v1/assistant/turn", {"text": "read .env"})
        thread = self.wait_done(body["threadId"])
        obs = next(i for i in thread["items"] if i["type"] == "observation")
        self.assertEqual(obs["status"], "blocked")
        self.assertNotIn("hunter2", json.dumps(thread))


class Mapping(unittest.TestCase):
    def test_every_agent_event_maps_to_a_valid_observatory_event(self):
        events = [{"kind": "start", "thread": "t"}, {"kind": "tool", "tool": "file.read", "status": "ok"}, {"kind": "tool", "tool": "file.read", "status": "blocked"},
                  {"kind": "tool", "tool": "bad name!", "status": "ok"}, {"kind": "skill", "skill": "aiws-log-tools:read-log"},
                  {"kind": "end", "outcome": "final", "metrics": {"calls": 2, "doneMs": 1500, "usage": {"promptTokens": 100, "completionTokens": 9, "cacheN": 40}}},
                  {"kind": "end", "outcome": "error", "metrics": {"usage": {}}}]
        for ev in events:
            kind, fields = AS.observatory_events(ev)
            made = E.make_event(1000.0, "local", "assistant-20261122", kind, **fields)
            self.assertEqual(made["kind"], kind)
        self.assertEqual(AS.observatory_events(events[2])[1]["status"], "denied")
        self.assertEqual(AS.observatory_events(events[3])[1]["tool"], "unknown")
        end = AS.observatory_events(events[5])[1]
        self.assertEqual((end["tokens"]["in"], end["tokens"]["out"], end["tokens"]["cacheRead"], end["tokens"]["source"]), (100, 9, 40, "reported"))
        self.assertEqual(AS.observatory_events(events[6])[1]["tokens"], {"source": "unknown", "scope": "turn"})     # unknown stays unknown
        self.assertIsNone(AS.observatory_events({"kind": "whatever"}))


if __name__ == "__main__":
    unittest.main()
