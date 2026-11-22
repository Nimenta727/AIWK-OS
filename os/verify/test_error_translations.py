"""Every message the user-facing modules can raise or reply with must have a Chinese translation in workbench/src/model/errors.mjs.
(English UI shows the original; Chinese UI would otherwise silently show English.) New messages in the modules written for the
shell must be translated outright; for older modules a coverage floor stops it from getting worse."""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = (ROOT.parent / "workbench/src/model/errors.mjs").read_text(encoding="utf-8")

def static_messages(module):
    out = set()
    for n in ast.walk(ast.parse((ROOT / "runtime" / (module + ".py")).read_text())):
        if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call) and n.exc.args:
            a = n.exc.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                out.add(a.value)
    return out

def covered(msg):
    # exact entries are written as '...' or "..." literals in the table; escape for the quoting style used there
    return any(q + msg.replace("\\", "\\\\").replace(q, "\\" + q) + q in TABLE for q in ("'", '"'))

class Coverage(unittest.TestCase):
    def test_http_layer_literals_are_all_translated(self):
        src = (ROOT / "runtime/aiws_workbench.py").read_text()
        missing = [m for m in set(re.findall(r'"error": ?"([^"]{3,120})"', src)) if not covered(m)]
        self.assertEqual(missing, [], "add these to workbench/src/model/errors.mjs")
    def test_shell_modules_are_fully_translated(self):
        for mod in ("aiws_system", "aiws_changes", "aiws_capabilities"):
            missing = [m for m in static_messages(mod) if not covered(m) and not re.search(r"[%{]", m)]
            # messages that embed a value are covered by PATTERNS; checked by the translator tests in the frontend
            self.assertEqual([m for m in missing if m not in ("Memory must be 1–", "Skill is larger than ")], [], mod)
    def test_overall_coverage_floor(self):
        total = ok = 0
        for mod in ("aiws_workbench", "aiws_mandate", "aiws_supervisor", "aiws_tasks", "aiws_apps", "aiws_model_router", "aiws_system", "aiws_changes", "aiws_capabilities"):
            for m in static_messages(mod):
                total += 1; ok += covered(m)
        self.assertGreaterEqual(ok / total, 0.78, "translated %d of %d user-reachable messages" % (ok, total))

class NoEnglishOnlyChrome(unittest.TestCase):
    """Built-in labels/tooltips in the new UI must go through tr()/useTr(), not be hard-coded in one language."""
    def test_aria_title_placeholder_literals(self):
        bad = []
        for p in list((ROOT.parent / "workbench/src/app").glob("*.tsx")) + list((ROOT.parent / "workbench/src/ui").glob("*.tsx")):
            for i, line in enumerate(p.read_text().splitlines(), 1):
                for m in re.finditer(r'(aria-label|title|placeholder|label)="([^"{}]*[A-Za-z一-鿿][^"{}]*)"', line):
                    if m.group(2) in ("Wi-Fi", "app", "AIWS", "AIWS Code", "git push"):
                        continue
                    bad.append("%s:%d %s=%r" % (p.name, i, m.group(1), m.group(2)))
        self.assertEqual(bad, [])

if __name__ == "__main__":
    unittest.main()
