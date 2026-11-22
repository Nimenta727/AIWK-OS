"""Resident mode of the model gate: loaded at start, never unloaded for idleness, restarted when it dies (SYNTHETIC fake llama)."""
import os
import signal
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_model_gate as base
from aiws_model_gate import GateError, ModelGate

def ready(gate, n=1):
    """Ready = the child answered /health at least n times (coldStarts counts completed starts), not merely 'process exists'."""
    return wait_for(lambda: gate.status()["coldStarts"] >= n and gate.status()["loaded"])

def wait_for(cond, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        if cond(): return True
        time.sleep(0.1)
    return False

class Resident(base.Base):
    idle = 0
    def test_loaded_before_any_request_and_reported_resident(self):
        self.assertTrue(ready(self.gate), "model should load without a request")
        st = self.gate.status(); self.assertTrue(st["resident"]); self.assertEqual(st["requests"], 0)
    def test_never_unloaded_for_idleness(self):
        self.assertTrue(ready(self.gate)); pid = self.gate.status()["childPid"]
        time.sleep(2.5)                                   # a non-resident gate with idle>0.2 would have unloaded by now
        self.assertEqual(self.gate.status()["childPid"], pid); self.assertEqual(self.gate.status()["idleUnloads"], 0)
    def test_first_request_pays_no_cold_start(self):
        self.assertTrue(ready(self.gate)); cold = self.gate.status()["coldStarts"]
        status, _ = self.call("POST", "/v1/chat/completions", base.BODY)
        self.assertEqual(status, 200); self.assertEqual(self.gate.status()["coldStarts"], cold)
    def test_restarted_after_it_dies(self):
        self.assertTrue(ready(self.gate)); pid = self.gate.status()["childPid"]
        os.kill(pid, signal.SIGKILL)
        self.assertTrue(ready(self.gate, 2), "must come back")
        self.assertNotEqual(self.gate.status()["childPid"], pid)
        self.assertGreaterEqual(self.gate.status()["crashes"], 1)
        self.assertEqual(self.call("POST", "/v1/chat/completions", base.BODY)[0], 200)

class Launchers(unittest.TestCase):
    def test_both_guest_launchers_default_to_resident_with_an_opt_out(self):
        root = Path(__file__).resolve().parents[1]
        for rel in ("model/aiws-local-model.sh", "debian/config/includes.chroot/usr/local/bin/aiws-local-model"):
            text = (root / rel).read_text()
            self.assertIn("resident=--resident", text, rel); self.assertIn('AIWS_MODEL_RESIDENT:-1', text, rel); self.assertIn("$resident", text, rel)

class Validation(unittest.TestCase):
    def make(self, idle):
        return ModelGate([base.FAKE, "--host", "127.0.0.1", "--port", "1"], listen_port=0, child_port=1, idle_seconds=idle, allowed_names=("fake_llama.py",))
    def test_zero_is_resident_small_and_negative_are_not_allowed(self):
        g = self.make(0); self.assertTrue(g.resident); g.server.server_close()
        for bad in (0.1, -1, 86401):
            with self.assertRaises(GateError, msg=bad): self.make(bad)
        g = self.make(30); self.assertFalse(g.resident); g.server.server_close()

class CrashLoopIsBounded(unittest.TestCase):
    def test_a_model_that_cannot_start_does_not_spin(self):
        port = base.free_port()
        gate = ModelGate([base.FAKE, "--host", "127.0.0.1", "--port", str(port), "--log", "/nonexistent/dir/x.log"], listen_port=0, child_port=port,
                         idle_seconds=0, start_timeout=3, allowed_names=("fake_llama.py",))
        gate.start()
        try:
            time.sleep(6)
            st = gate.status()
            self.assertLessEqual(st["crashes"], 8, "crash cooldown must cap restart attempts")   # CRASH_LIMIT then COOLDOWN
        finally:
            gate.close()

if __name__ == "__main__":
    unittest.main()
