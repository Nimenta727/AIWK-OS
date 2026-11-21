"""O5: image wiring of the model gate (scripts, packaging, guest smoke). Static checks plus the script<->gate contract."""
from pathlib import Path
import re
import shlex
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
from aiws_model_gate import validate_child_argv

SCRIPTS = [ROOT / "model/aiws-local-model.sh", ROOT / "debian/config/includes.chroot/usr/local/bin/aiws-local-model"]

def exec_argv(text):
    """The argv of the final `exec ...` command (joins line continuations)."""
    joined = text.replace("\\\n", " ")
    line = next(l for l in joined.splitlines() if l.lstrip().startswith("exec "))
    return shlex.split(line.strip())[1:]

class ScriptTests(unittest.TestCase):
    def test_scripts_are_valid_shell(self):
        for s in SCRIPTS:
            r = subprocess.run(["sh", "-n", str(s)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, "%s: %s" % (s, r.stderr))

    def test_both_scripts_start_the_model_through_the_gate_on_the_internal_port(self):
        for s in SCRIPTS:
            argv = exec_argv(s.read_text())
            self.assertEqual(argv[:2], ["python3", "/usr/local/lib/aiws/aiws_model_gate.py"], s)
            self.assertEqual(argv[argv.index("--listen-port") + 1], "18080")
            self.assertEqual(argv[argv.index("--child-port") + 1], "18081")
            child = argv[argv.index("--") + 1:]
            self.assertEqual(Path(child[0]).name, "llama-server")
            # the exact command line the script builds must satisfy the gate's own contract
            validate_child_argv(child, 18081)
            self.assertEqual(child[child.index("--host") + 1], "127.0.0.1")
            self.assertNotEqual(child[child.index("--port") + 1], "18080")           # llama-server never owns the public port

    def test_idle_setting_is_sanitised_in_the_shell(self):
        for s in SCRIPTS:
            text = s.read_text()
            self.assertIn('AIWS_MODEL_IDLE_SECONDS:-300', text)
            self.assertRegex(text, r"\*\[!0-9\]\*\) idle=300")
            self.assertIn('-lt 30', text)
            self.assertIn('-gt 86400', text)

    def test_installed_script_still_verifies_the_model_before_serving(self):
        text = SCRIPTS[1].read_text()
        self.assertLess(text.index("aiws_model_registry.py --verify"), text.index("aiws_model_gate.py"))
        self.assertIn("Model cannot run as guest root", text)

class PackagingTests(unittest.TestCase):
    def test_gate_and_schema_are_packaged(self):
        build = (ROOT / "debian/build.sh").read_text()
        for m in ("aiws_model_gate", "aiws_model_schema"):
            self.assertIn("os/runtime/%s.py" % m, build)
        planner = (ROOT / "runtime/aiws_local_model.py").read_text()
        self.assertIn("from aiws_model_schema import response_format", planner)     # lazy import: must still be shipped

    def test_unit_keeps_its_network_confinement(self):
        unit = (ROOT / "debian/config/includes.chroot/etc/systemd/user/aiws-local-model.service").read_text()
        for line in ("IPAddressDeny=any", "IPAddressAllow=localhost", "RestrictAddressFamilies=AF_INET AF_UNIX", "MemoryMax=5G", "NoNewPrivileges=yes"):
            self.assertIn(line, unit)

class GuestSmokeTests(unittest.TestCase):
    def test_smoke_measures_the_real_server_not_the_gate(self):
        src = (ROOT / "model/ci/guest_inference_smoke.py").read_text()
        self.assertIn("/gate/status", src)
        self.assertIn("childPid", src)
        self.assertNotIn("MainPID", src)                                               # that would now be the gate process
        self.assertIn("lastColdStartSeconds", src)
        compile(src, "guest_inference_smoke.py", "exec")

if __name__ == "__main__":
    unittest.main()
