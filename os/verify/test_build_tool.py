"""The restricted build/test/run tool: fixed commands only, validated targets, real toolchains where available, sandbox properties."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "runtime")); sys.path.insert(0, str(HERE / "fixtures"))
import aiws_build_tool as B
import aiws_cloud_agent as A
import aiws_deepseek as D
from fake_deepseek import FakeDeepSeek, KEY, reply, tool_call

FAKE_WHICH = lambda t: "/usr/bin/" + t
def have(*tools): return all(shutil.which(t) for t in tools)

class Proj(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.p = Path(self.t.name).resolve() / "app"; self.p.mkdir()
        self.scratch = B.Scratch(self.t.name); self.addCleanup(self.scratch.close); self.addCleanup(self.t.cleanup)
    def w(self, rel, text):
        f = self.p / rel; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(text); return f
    def run_tool(self, language, action, target=None, scale=1.0):
        command, go = B.run_request({"language": language, "action": action, **({"target": target} if target else {})}, self.p, self.scratch, timeout_scale=scale)
        return command, go()

class Targets(Proj):
    def test_valid_and_invalid_targets(self):
        self.w("a.py", "x=1"); (self.p / "sub").mkdir()
        self.assertEqual(B.check_target(self.p, None)[0], "."); self.assertEqual(B.check_target(self.p, "a.py")[0], "a.py"); self.assertEqual(B.check_target(self.p, "sub")[0], "sub")
        (self.p / "link").symlink_to(self.p / "sub"); (self.p / ".git").mkdir()
        for bad in ("../x", "/etc/passwd", "~/x", "-rf", "--version", "a\nb", "a\\b", "x" * 300, "missing.py", "link", "link/x", ".git", ".git/config", "sub/../../x", 5, "a\x00b"):
            with self.assertRaises(B.BuildError, msg=repr(bad)): B.check_target(self.p, bad)
    def test_wrong_extension_is_rejected(self):
        self.w("a.txt", "x")
        for lang in ("c", "cpp", "go", "python", "rust", "java", "javascript", "csharp"):
            with self.assertRaises(B.BuildError, msg=lang): B.plan(lang, "build", self.p, "a.txt", "/o", FAKE_WHICH)

class Planner(Proj):
    def argv(self, language, action, target=None, which=FAKE_WHICH, has=lambda n: False):
        return [s["argv"] for s in B.plan(language, action, self.p, target, "/o", which, has)["steps"]]
    def test_no_command_contains_shell_syntax_or_free_text(self):
        for f in ("a.c", "a.cpp", "a.go", "a.py", "a.rs", "A.java", "a.js", "a.cs"): self.w(f, "x")
        cases = [("c", "a.c"), ("cpp", "a.cpp"), ("go", "a.go"), ("python", "a.py"), ("rust", "a.rs"), ("java", "A.java"), ("javascript", "a.js"), ("csharp", "a.cs")]
        for lang, tgt in cases:
            for action in B.ACTIONS:
                try: plan = B.plan(lang, action, self.p, tgt, "/o", FAKE_WHICH, lambda n: False)
                except B.BuildError: continue
                for st in plan["steps"]:
                    self.assertTrue(all(isinstance(a, str) for a in st["argv"]))
                    self.assertNotIn(st["argv"][0].rsplit("/", 1)[-1], ("sh", "bash", "dash", "zsh", "env", "sudo", "su", "curl", "wget", "rm"))
                    for a in st["argv"]: self.assertNotIn(a, ("-c", "-exec"), (lang, action))
    def test_c_cpp_single_file_cmake_and_make(self):
        self.w("a.c", "int main(){}"); self.assertEqual(self.argv("c", "check", "a.c")[0][1:], ["-std=c17", "-Wall", "-Wextra", "-fsyntax-only", "a.c"])
        self.assertEqual(self.argv("c", "run", "a.c")[1], ["/o/a"]); self.assertEqual(self.argv("c", "build", "a.c")[0][-3:], ["-o", "/o/a", "a.c"])
        with self.assertRaises(B.BuildError): self.argv("c", "test", "a.c")
        self.w("b.cpp", "int main(){}"); self.assertIn("-std=c++20", self.argv("cpp", "build", "b.cpp")[0])
        self.w("proj/CMakeLists.txt", "x"); st = self.argv("cpp", "test", "proj"); self.assertEqual(len(st), 3); self.assertEqual(st[2][0:2], ["/usr/bin/ctest", "--test-dir"])
        self.w("m/Makefile", "all:\n"); self.assertEqual(self.argv("c", "test", "m")[0], ["/usr/bin/make", "-C", "m", "test"])
        (self.p / "empty").mkdir()
        with self.assertRaises(B.BuildError): self.argv("c", "build", "empty")
    def test_go_python_node(self):
        self.w("main.go", "package main"); plan = B.plan("go", "test", self.p, None, "/o", FAKE_WHICH, lambda n: False)
        self.assertEqual(plan["steps"][0]["argv"], ["/usr/bin/go", "test", "./..."]); self.assertEqual((plan["env"]["GOPROXY"], plan["env"]["GOTOOLCHAIN"]), ("off", "local"))
        self.assertEqual(self.argv("go", "run", "main.go")[0], ["/usr/bin/go", "run", "main.go"])
        self.w("t.py", "x"); self.assertEqual(self.argv("python", "check", "t.py")[0][1:], ["-m", "py_compile", "t.py"]); self.assertEqual(self.argv("python", "run", "t.py")[0][1:], ["t.py"])
        self.assertIn("unittest", self.argv("python", "test", None)[0]); self.assertIn("pytest", self.argv("python", "test", None, has=lambda n: n == "pytest")[0])
        self.w("n.js", "x"); self.assertEqual(self.argv("javascript", "check", "n.js")[0][1:], ["--check", "n.js"]); self.assertEqual(self.argv("javascript", "test", None)[0][1:], ["--test"])
        self.w("pj/package.json", '{"scripts":{"test":"node t.js"}}'); self.assertEqual(self.argv("javascript", "test", "pj")[0][1:3], ["test", "--offline"])
    def test_rust_java_csharp(self):
        self.w("c/Cargo.toml", "[package]"); self.assertEqual(self.argv("rust", "build", "c")[0][1:], ["build", "--manifest-path", "c/Cargo.toml", "--offline"])
        self.w("r.rs", "fn main(){}"); self.assertEqual(self.argv("rust", "run", "r.rs")[1], ["/o/r"])
        self.w("p/Main.java", "package a.b;\nclass Main{}"); self.assertEqual(self.argv("java", "run", "p/Main.java")[1][-1], "a.b.Main"); self.w("H.java", "class H{}"); self.assertEqual(self.argv("java", "run", "H.java")[1][-1], "H")
        self.w("mv/pom.xml", "<project/>"); self.assertEqual(self.argv("java", "test", "mv")[0][1:3], ["-o", "-q"])
        self.w("x.cs", "class X{}"); with_mcs = lambda t: "/usr/bin/" + t if t in ("mcs", "mono") else None
        self.assertEqual(self.argv("csharp", "run", "x.cs", which=with_mcs)[1], ["/usr/bin/mono", "/o/x.exe"])
        self.w("dn/a.csproj", "<Project/>"); st = self.argv("csharp", "build", "dn", which=lambda t: "/usr/bin/dotnet" if t == "dotnet" else None)[0]; self.assertIn("-p:UseSharedCompilation=false", st)
        with self.assertRaises(B.BuildError) as cm: self.argv("csharp", "build", "x.cs", which=lambda t: None)
        self.assertIn("No C# compiler", str(cm.exception))
    def test_missing_toolchain_is_a_clear_error(self):
        self.w("a.c", "x")
        with self.assertRaises(B.BuildError) as cm: B.plan("c", "build", self.p, "a.c", "/o", lambda t: None, lambda n: False)
        self.assertIn("not installed", str(cm.exception))
    def test_unknown_and_extra_arguments_are_refused(self):
        for args in ({"language": "perl", "action": "run"}, {"language": "c", "action": "install"}, {"language": "c", "action": "build", "args": "-x"}, {"language": "c", "action": "build", "cmd": "ls"}, "ls"):
            with self.assertRaises(B.BuildError, msg=args): B.run_request(args, self.p, self.scratch, FAKE_WHICH)

@unittest.skipUnless(have("cc"), "no C compiler")
class RealC(Proj):
    def test_build_run_and_errors(self):
        self.w("hello.c", '#include <stdio.h>\nint main(void){puts("hello c");return 0;}\n')
        cmd, res = self.run_tool("c", "run", "hello.c"); self.assertEqual(res["exitCode"], 0); self.assertIn("hello c", res["output"]); self.assertIn("&&", cmd)
        self.w("bad.c", "int main(){ return x; }\n"); _, res = self.run_tool("c", "build", "bad.c")
        self.assertNotEqual(res["exitCode"], 0); self.assertIn("error", res["output"]); self.assertIn("bad.c", res["output"])
    def test_a_program_that_fails_reports_its_exit_code(self):
        self.w("f.c", "int main(void){return 7;}\n"); self.assertEqual(self.run_tool("c", "run", "f.c")[1]["exitCode"], 7)

@unittest.skipUnless(have("c++"), "no C++ compiler")
class RealCpp(Proj):
    def test_run(self):
        self.w("h.cpp", '#include <iostream>\nint main(){ std::cout << "hello cpp\\n"; }\n'); self.assertIn("hello cpp", self.run_tool("cpp", "run", "h.cpp")[1]["output"])
    @unittest.skipUnless(have("cmake", "make"), "no cmake")
    def test_cmake_project_builds_and_tests_in_the_scratch_not_the_project(self):
        self.w("c/CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\nproject(t CXX)\nenable_testing()\nadd_executable(t main.cpp)\nadd_test(NAME ok COMMAND t)\n"); self.w("c/main.cpp", "int main(){return 0;}\n")
        _, res = self.run_tool("cpp", "test", "c"); self.assertEqual(res["exitCode"], 0, res["output"]); self.assertFalse((self.p / "c" / "build").exists())
        self.assertEqual(sorted(x.name for x in (self.p / "c").iterdir()), ["CMakeLists.txt", "main.cpp"])    # nothing generated inside the project

@unittest.skipUnless(have("go"), "no Go")
class RealGo(Proj):
    def test_module_build_vet_test_run(self):
        self.w("go.mod", "module example.com/h\n\ngo 1.20\n"); self.w("main.go", 'package main\nimport "fmt"\nfunc main(){ fmt.Println("hello go") }\nfunc Add(a, b int) int { return a + b }\n')
        self.w("main_test.go", 'package main\nimport "testing"\nfunc TestAdd(t *testing.T){ if Add(1,2)!=3 { t.Fatal("bad") } }\n')
        for action in ("check", "build", "test"): self.assertEqual(self.run_tool("go", action)[1]["exitCode"], 0, action)
        self.assertIn("hello go", self.run_tool("go", "run", "main.go")[1]["output"])
    def test_failing_test_is_reported_not_hidden(self):
        self.w("go.mod", "module example.com/h\n\ngo 1.20\n"); self.w("a.go", "package main\nfunc main(){}\n"); self.w("a_test.go", 'package main\nimport "testing"\nfunc TestX(t *testing.T){ t.Fatal("boom") }\n')
        _, res = self.run_tool("go", "test"); self.assertNotEqual(res["exitCode"], 0); self.assertIn("boom", res["output"])
    def test_network_is_not_attempted(self):
        self.w("go.mod", "module example.com/h\n\ngo 1.20\n\nrequire example.invalid/nothing v1.0.0\n"); self.w("a.go", 'package main\nimport _ "example.invalid/nothing"\nfunc main(){}\n')
        t0 = time.time(); _, res = self.run_tool("go", "build"); self.assertNotEqual(res["exitCode"], 0); self.assertLess(time.time() - t0, 30)

class RealPython(Proj):
    def test_check_run_and_unittest(self):
        self.w("h.py", "print('hello py')\n"); self.assertIn("hello py", self.run_tool("python", "run", "h.py")[1]["output"]); self.assertEqual(self.run_tool("python", "check", "h.py")[1]["exitCode"], 0)
        self.w("bad.py", "def f(:\n"); res = self.run_tool("python", "check", "bad.py")[1]; self.assertNotEqual(res["exitCode"], 0); self.assertIn("SyntaxError", res["output"])
        self.w("test_a.py", "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): self.assertEqual(1, 1)\n    def test_bad(self): self.assertEqual(1, 2)\n")
        res = self.run_tool("python", "test")[1]; self.assertNotEqual(res["exitCode"], 0); self.assertIn("test_bad", res["output"])
    def test_pycache_does_not_pollute_the_project(self):
        self.w("h.py", "print(1)\n"); self.run_tool("python", "check", "h.py"); self.assertFalse((self.p / "__pycache__").exists())

@unittest.skipUnless(have("rustc"), "no rustc")
class RealRust(Proj):
    def test_single_file_run_and_test(self):
        self.w("h.rs", 'fn main(){ println!("hello rust"); }\n#[cfg(test)]\nmod t { #[test] fn ok(){ assert_eq!(1+1,2); } }\n')
        self.assertIn("hello rust", self.run_tool("rust", "run", "h.rs")[1]["output"]); self.assertEqual(self.run_tool("rust", "test", "h.rs")[1]["exitCode"], 0)
    @unittest.skipUnless(have("cargo"), "no cargo")
    def test_cargo_project_offline(self):
        self.w("c/Cargo.toml", '[package]\nname = "c"\nversion = "0.1.0"\nedition = "2021"\n'); self.w("c/src/main.rs", 'fn main(){ println!("hello cargo"); }\n')
        self.assertIn("hello cargo", self.run_tool("rust", "run", "c")[1]["output"]); self.assertFalse((self.p / "c" / "target").exists())
        self.w("e/Cargo.toml", '[package]\nname = "e"\nversion = "0.1.0"\nedition = "2021"\n'); self.w("e/src/main.rs", "fn main(){ let x: i32 = \"s\"; }\n")
        res = self.run_tool("rust", "build", "e")[1]; self.assertNotEqual(res["exitCode"], 0); self.assertIn("mismatched types", res["output"])

@unittest.skipUnless(have("javac", "java"), "no JDK")
class RealJava(Proj):
    def test_default_and_packaged_main(self):
        self.w("Hello.java", 'public class Hello { public static void main(String[] a){ System.out.println("hello java"); } }\n'); self.assertIn("hello java", self.run_tool("java", "run", "Hello.java")[1]["output"])
        self.w("p/Main.java", 'package a.b;\npublic class Main { public static void main(String[] a){ System.out.println("hello pkg"); } }\n'); self.assertIn("hello pkg", self.run_tool("java", "run", "p/Main.java")[1]["output"])
        self.w("Bad.java", "class Bad { int x = ; }\n"); res = self.run_tool("java", "build", "Bad.java")[1]; self.assertNotEqual(res["exitCode"], 0); self.assertIn("Bad.java", res["output"])

@unittest.skipUnless(have("node"), "no Node")
class RealNode(Proj):
    def test_check_run_and_builtin_test_runner(self):
        self.w("h.js", "console.log('hello js')\n"); self.assertIn("hello js", self.run_tool("javascript", "run", "h.js")[1]["output"]); self.assertEqual(self.run_tool("javascript", "check", "h.js")[1]["exitCode"], 0)
        self.w("bad.js", "function (\n"); self.assertNotEqual(self.run_tool("javascript", "check", "bad.js")[1]["exitCode"], 0)
        self.w("a.test.js", "const t=require('node:test');const a=require('node:assert');t('ok',()=>a.strictEqual(1,1));t('bad',()=>a.strictEqual(1,2));")
        res = self.run_tool("javascript", "test")[1]; self.assertNotEqual(res["exitCode"], 0); self.assertIn("bad", res["output"])

class Sandbox(Proj):
    """Properties of the executor itself, independent of any language."""
    def steps(self, *argvs): return [{"argv": a, "label": " ".join(a)} for a in argvs]
    def test_timeout_kills_the_whole_process_group_including_grandchildren(self):
        marker = self.p / "pid"; script = "import subprocess,sys,time; p=subprocess.Popen(['sleep','60']); open(sys.argv[1],'w').write(str(p.pid)); time.sleep(60)"
        res = B.execute(self.steps([sys.executable, "-c", script, str(marker)]), str(self.p), B.base_env(self.scratch.get() + "/home", self.scratch.get(), {}), 2, scratch=self.scratch.get() + "/tmp")
        self.assertTrue(res["timedOut"]); pid = int(marker.read_text()); time.sleep(0.3)
        try: os.kill(pid, 0); alive = Path("/proc/%d/stat" % pid).read_text().split(")")[1].split()[0] != "Z"
        except (ProcessLookupError, OSError): alive = False
        self.assertFalse(alive, "a grandchild survived the timeout")
    def test_huge_output_is_bounded_with_head_and_tail(self):
        res = B.execute(self.steps([sys.executable, "-c", "import sys\nsys.stdout.write('HEAD' + 'x'*6000000 + 'TAIL')"]), str(self.p), B.base_env(self.scratch.get() + "/home", self.scratch.get(), {}), 30, scratch=self.scratch.get() + "/tmp")
        self.assertEqual(res["exitCode"], 0); self.assertLessEqual(len(res["output"]), 2 * B.MAX_OUT + 100); self.assertTrue(res["output"].startswith("HEAD")); self.assertTrue(res["output"].endswith("TAIL")); self.assertIn("omitted", res["output"])
    def test_the_environment_is_minimal_and_secrets_are_not_inherited(self):
        os.environ["DEEPSEEK_API_KEY"] = KEY; os.environ["SOME_TOKEN"] = "t0ken"; self.addCleanup(os.environ.pop, "DEEPSEEK_API_KEY", None); self.addCleanup(os.environ.pop, "SOME_TOKEN", None)
        self.w("e.py", "import os, json; print(json.dumps(dict(os.environ)), os.getcwd())"); _, res = self.run_tool("python", "run", "e.py")
        self.assertNotIn(KEY, res["output"]); self.assertNotIn("t0ken", res["output"]); self.assertIn(str(self.p), res["output"]); self.assertIn("aiws-build-", res["output"])   # HOME/TMPDIR point into the scratch
    def test_stdin_is_closed_so_a_program_cannot_wait_for_input(self):
        self.w("i.py", "import sys; print(repr(sys.stdin.read()))"); self.assertIn("''", self.run_tool("python", "run", "i.py", scale=1)[1]["output"])
    def test_a_missing_program_is_reported_not_raised(self):
        res = B.execute(self.steps(["/nonexistent/prog"]), str(self.p), {}, 5); self.assertIsNone(res["exitCode"]); self.assertIn("could not start", res["output"])
    def test_steps_stop_at_the_first_failure(self):
        res = B.execute(self.steps([sys.executable, "-c", "raise SystemExit(3)"], [sys.executable, "-c", "print('never')"]), str(self.p), B.base_env(self.scratch.get() + "/home", self.scratch.get(), {}), 20, scratch=self.scratch.get() + "/tmp")
        self.assertEqual(res["exitCode"], 3); self.assertNotIn("never", res["output"])
    def test_a_runaway_cpu_loop_is_stopped(self):
        self.w("l.py", "while True: pass\n"); res = self.run_tool("python", "run", "l.py", scale=0.03)[1]; self.assertTrue(res["timedOut"])
    def test_scratch_is_private_and_removed(self):
        s = B.Scratch(self.t.name); d = s.get(); self.assertEqual(os.stat(d).st_mode & 0o777, 0o700); self.assertTrue(os.path.isdir(d + "/home")); s.close(); self.assertFalse(os.path.exists(d))

class InTheAgent(unittest.TestCase):
    """The tool as the model sees it: gated, optional, never offered to sub-agents or when execution is not allowed."""
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.proj = Path(self.t.name).resolve() / "app"; self.proj.mkdir(); (self.proj / "h.py").write_text("print('hi from model code')\n")
        os.environ["AIWS_WORKSPACE"] = str(self.proj); self.out, self.decisions = [], []
    def tearDown(self):
        os.environ.pop("AIWS_WORKSPACE", None); self.t.cleanup()
    def mandate(self, **kw):
        m = {"projectDir": "app", "allowedTools": ["file.read", "build.run", "agent.spawn"], "model": "deepseek-flash", "thinking": True, "effort": "high", "maxTurns": 12,
             "tokenBudget": {"input": 10 ** 7, "output": 10 ** 6}, "wallClockMinutes": 5, "needApprovalFor": ["build", "network", "shell", "outside-project"], "planApproval": False}
        m.update(kw); return m
    def go(self, script, exec_ok=True, **mk):
        fake = FakeDeepSeek(script); self.addCleanup(fake.close); self.fake = fake
        client = D.Client(lambda: KEY, base_url=fake.url, allow_loopback=True, sleep=lambda d: None)
        def read(): return self.decisions.pop(0) if self.decisions else None
        A.run({"mandate": self.mandate(**mk), "task": "check it", "language": "en", "project": str(self.proj), "exec": exec_ok}, self.out.append, read, client)
    def tool_msgs(self, i=1): return [m["content"] for m in self.fake.requests[i]["body"]["messages"] if m["role"] == "tool"]
    def test_every_build_asks_first_and_shows_the_exact_command(self):
        self.decisions = [{"id": "g1", "approve": True}]
        self.go([reply("", [tool_call("build__run", {"language": "python", "action": "run", "target": "h.py"})]), reply("it works")])
        gate = [o for o in self.out if o["t"] == "gate"][0]; self.assertEqual((gate["category"], gate["tool"]), ("build", "build.run")); self.assertIn("h.py", gate["detail"])
        self.assertIn("exit code 0", self.tool_msgs()[0]); self.assertIn("hi from model code", self.tool_msgs()[0])
        ev = [e for e in self.out if e["t"] == "event" and e.get("tool") == "build.run"]; self.assertEqual([e["status"] for e in ev], ["pending", "ok"]); self.assertEqual(ev[0]["ctx"][0]["kind"], "command")
    def test_refusal_means_the_program_never_ran(self):
        marker = self.proj / "ran"; (self.proj / "h.py").write_text("open('ran','w').write('x')\n"); self.decisions = [{"id": "g1", "approve": False}]
        self.go([reply("", [tool_call("build__run", {"language": "python", "action": "run", "target": "h.py"})]), reply("ok")])
        self.assertFalse(marker.exists()); self.assertIn("did not approve", self.tool_msgs()[0])
    def test_the_user_can_choose_not_to_be_asked(self):
        self.go([reply("", [tool_call("build__run", {"language": "python", "action": "run", "target": "h.py"})]), reply("ok")], needApprovalFor=["network", "shell", "outside-project"])
        self.assertEqual([o for o in self.out if o["t"] == "gate"], []); self.assertIn("exit code 0", self.tool_msgs()[0])
    def test_not_offered_at_all_when_execution_is_not_allowed(self):
        self.go([reply("ok")], exec_ok=False); body = self.fake.requests[0]["body"]
        self.assertNotIn("build__run", [t["function"]["name"] for t in body["tools"]]); self.assertNotIn("build_run", body["messages"][0]["content"])
    def test_the_prompt_mentions_it_only_when_it_exists(self):
        self.go([reply("ok")]); self.assertIn("build_run", self.fake.requests[0]["body"]["messages"][0]["content"])
    def test_sub_agents_never_get_it(self):
        self.go([reply("", [tool_call("agent__spawn", {"task": "t", "allow_writes": True})]), reply("x"), reply("ok")])
        self.assertNotIn("build__run", [t["function"]["name"] for t in self.fake.requests[1]["body"]["tools"]])
    def test_bad_requests_come_back_as_errors_not_crashes(self):
        self.decisions = []
        self.go([reply("", [tool_call("build__run", {"language": "python", "action": "run", "target": "../../etc/passwd"}), tool_call("build__run", {"language": "cobol", "action": "run"}),
                            tool_call("build__run", {"language": "python", "action": "run", "target": "h.py", "args": "--evil"})]), reply("ok")])
        msgs = self.tool_msgs(); self.assertEqual(len(msgs), 3); self.assertTrue(all(m.startswith("error:") for m in msgs)); self.assertEqual([o for o in self.out if o["t"] == "gate"], [])
    def test_scratch_is_removed_after_the_run(self):
        import glob; before = set(glob.glob("/var/tmp/aiws-build-*"))
        self.decisions = [{"id": "g1", "approve": True}]
        self.go([reply("", [tool_call("build__run", {"language": "python", "action": "check", "target": "h.py"})]), reply("ok")]); self.assertEqual(set(glob.glob("/var/tmp/aiws-build-*")), before)
    def test_the_key_never_reaches_the_program(self):
        (self.proj / "h.py").write_text("import os; print([k for k in os.environ])\n"); self.decisions = [{"id": "g1", "approve": True}]
        os.environ["DEEPSEEK_API_KEY"] = KEY; self.addCleanup(os.environ.pop, "DEEPSEEK_API_KEY", None)
        self.go([reply("", [tool_call("build__run", {"language": "python", "action": "run", "target": "h.py"})]), reply("ok")])
        self.assertNotIn("DEEPSEEK", self.tool_msgs()[0]); self.assertNotIn(KEY, json.dumps(self.out))

if __name__ == "__main__":
    unittest.main()
