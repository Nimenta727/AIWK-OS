"""Swift planning, dependency download, git commit: the rest of the cloud agent's toolbox."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "runtime")); sys.path.insert(0, str(HERE / "fixtures"))
import aiws_build_tool as B
import aiws_cloud_agent as A
import aiws_deepseek as D
import aiws_git_tool as G
from aiws_mandate import MandateError, validate_mandate
from fake_deepseek import FakeDeepSeek, KEY, reply, tool_call

FAKE = lambda t: "/usr/bin/" + t
PROXY = {"HTTPS_PROXY": "http://127.0.0.1:3128"}

class Proj(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.root = Path(self.t.name).resolve(); self.p = self.root / "app"; self.p.mkdir()
        self.cache = str(self.root / "cache"); Path(self.cache).mkdir()
        self.scratch = B.Scratch(self.t.name); self.addCleanup(self.scratch.close); self.addCleanup(self.t.cleanup)
    def w(self, rel, text):
        f = self.p / rel; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(text); return f

class Swift(Proj):
    def argv(self, action, target=None, which=FAKE):
        return [s["argv"] for s in B.plan("swift", action, self.p, target, "/o", which, None, self.cache)["steps"]]
    def test_single_file_commands(self):
        self.w("a.swift", 'print("hi")')
        self.assertEqual(self.argv("check", "a.swift")[0], ["/usr/bin/swiftc", "-typecheck", "a.swift"]); self.assertEqual(self.argv("build", "a.swift")[0][1:], ["-o", "/o/a", "a.swift"])
        self.assertEqual(self.argv("run", "a.swift")[1], ["/o/a"])
        with self.assertRaises(B.BuildError): self.argv("test", "a.swift")
    def test_package_commands_never_fetch_packages(self):
        self.w("Package.swift", "// swift-tools-version:5.9"); self.w("Sources/a/main.swift", "print(1)")
        for action, verb in (("check", "build"), ("build", "build"), ("test", "test"), ("run", "run")):
            a = self.argv(action)[0]; self.assertEqual(a[1], verb); self.assertIn("--disable-automatic-resolution", a); self.assertIn("/o/swiftpm", a)
    def test_subfolder_package(self):
        self.w("pkg/Package.swift", "x"); self.assertEqual(self.argv("build", "pkg")[0][3], "pkg")
    def test_toolchain_missing_is_a_clear_error(self):
        self.w("a.swift", "x")
        with self.assertRaises(B.BuildError) as cm: self.argv("build", "a.swift", which=lambda t: None)
        self.assertIn("swiftc is not installed", str(cm.exception))
    def test_wrong_target_is_rejected(self):
        self.w("a.txt", "x")
        with self.assertRaises(B.BuildError): self.argv("build", "a.txt")
    def test_apple_only_modules_get_an_honest_explanation(self):
        out = "main.swift:1:8: error: no such module 'SwiftUI'\nimport SwiftUI"
        res = {"exitCode": 1, "timedOut": False, "seconds": 1.0, "output": out}
        text = B.describe(res, "swift"); self.assertIn("only exists on Apple platforms", text); self.assertIn("SwiftUI", text)
        self.assertNotIn("Apple platforms", B.describe(res, "go")); self.assertNotIn("Apple platforms", B.describe({**res, "exitCode": 0}, "swift"))
        self.assertNotIn("Apple platforms", B.describe({**res, "output": "error: cannot find 'x' in scope"}, "swift"))
    def test_find_tool_looks_in_the_toolchain_folders(self):
        d = Path(self.t.name) / "bin"; d.mkdir(); exe = d / "swift-x"; exe.write_text("#!/bin/sh\n"); exe.chmod(0o755)
        old = B.TOOL_DIRS; B.TOOL_DIRS = (str(d),)
        try: self.assertEqual(B.find_tool("swift-x"), str(exe)); self.assertIsNone(B.find_tool("definitely-not-here"))
        finally: B.TOOL_DIRS = old

class DepsPlanner(Proj):
    def plan(self, language, target=None, env=PROXY, which=FAKE):
        return B.plan_deps(language, self.p, target, "/o", self.cache, which, env)
    def test_refuses_without_the_allowlisting_proxy(self):
        self.w("go.mod", "module x\n")
        for env in ({}, {"HTTP_PROXY": "http://x"}, {"HTTPS_PROXY": ""}):
            with self.assertRaises(B.BuildError) as cm: self.plan("go", env=env)
            self.assertIn("No network route", str(cm.exception))
    def test_each_language_uses_one_fixed_command_and_its_manifest(self):
        self.w("go.mod", "x"); self.assertEqual(self.plan("go")["steps"][0]["argv"], ["/usr/bin/go", "mod", "download"])
        self.w("Cargo.toml", "x"); self.assertEqual(self.plan("rust")["steps"][0]["argv"][1:], ["fetch", "--manifest-path", "Cargo.toml"])
        self.w("package.json", "{}"); a = self.plan("javascript")["steps"][0]["argv"]; self.assertEqual(a[1], "install"); self.assertIn("--ignore-scripts", a)
        self.w("package-lock.json", "{}"); self.assertEqual(self.plan("javascript")["steps"][0]["argv"][1], "ci")
        self.w("requirements.txt", "flask\n"); a = self.plan("python")["steps"][0]["argv"]; self.assertIn("--only-binary=:all:", a); self.assertEqual(a[a.index("--target") + 1], ".aiws-deps")
        self.w("pom.xml", "<project/>"); self.assertEqual(self.plan("java")["steps"][0]["argv"][-1], "dependency:go-offline")
        self.w("a.csproj", "<Project/>"); self.assertEqual(self.plan("csharp")["steps"][0]["argv"][1], "restore")
    def test_registries_are_not_configurable_by_the_caller(self):
        self.w("go.mod", "x"); env = self.plan("go")["env"]; self.assertEqual(env["GOPROXY"], "https://proxy.golang.org"); self.assertTrue(env["GOMODCACHE"].startswith(self.cache))
    def test_languages_without_a_supported_manager_say_so(self):
        for lang in ("c", "cpp", "swift"):
            with self.assertRaises(B.BuildError, msg=lang): self.plan(lang)
    def test_missing_manifest_and_bad_targets(self):
        with self.assertRaises(B.BuildError): self.plan("go")
        self.w("a.py", "x")
        with self.assertRaises(B.BuildError): self.plan("python", "a.py")                  # a file, not the project folder
        for bad in ("../x", "/etc", "-r"):
            with self.assertRaises(B.BuildError): self.plan("go", bad)
    def test_extra_arguments_are_refused(self):
        self.w("go.mod", "x")
        with self.assertRaises(B.BuildError): B.deps_request({"language": "go", "index": "http://evil"}, self.p, self.scratch, FAKE, self.cache, PROXY)
    def test_offline_builds_use_the_same_cache_and_never_the_network(self):
        self.w("go.mod", "x"); env = B.plan("go", "build", self.p, None, "/o", FAKE, None, self.cache)["env"]
        self.assertEqual((env["GOPROXY"], env["GOMODCACHE"]), ("off", self.cache + "/go"))
        self.w("Cargo.toml", "x"); env = B.plan("rust", "build", self.p, ".", "/o", FAKE, None, self.cache)["env"]; self.assertEqual((env["CARGO_NET_OFFLINE"], env["CARGO_HOME"]), ("true", self.cache + "/cargo"))
    def test_online_environment_passes_only_the_proxy(self):
        os.environ["SECRET_TOKEN"] = "t"; self.addCleanup(os.environ.pop, "SECRET_TOKEN", None)
        for k, v in PROXY.items(): os.environ[k] = v; self.addCleanup(os.environ.pop, k, None)
        e = B.base_env("/h", "/o", {}, online=True); self.assertEqual(e["HTTPS_PROXY"], PROXY["HTTPS_PROXY"]); self.assertNotIn("SECRET_TOKEN", e); self.assertNotIn("PIP_NO_INDEX", e)
        self.assertEqual(B.base_env("/h", "/o", {})["PIP_NO_INDEX"], "1"); self.assertNotIn("HTTPS_PROXY", B.base_env("/h", "/o", {}))

@unittest.skipUnless(shutil.which("python3"), "no python")
class RealPipFlow(Proj):
    """A real `pip install` from a local wheel index, then a build that finds the dependency: the whole download-then-offline cycle."""
    def make_index(self):
        d = self.root / "wheels"; d.mkdir(); whl = d / "aiwsdemo-1.0-py3-none-any.whl"
        files = {"aiwsdemo/__init__.py": "VALUE = 42\n", "aiwsdemo-1.0.dist-info/METADATA": "Metadata-Version: 2.1\nName: aiwsdemo\nVersion: 1.0\n",
                 "aiwsdemo-1.0.dist-info/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}
        record = "".join("%s,,\n" % n for n in list(files) + ["aiwsdemo-1.0.dist-info/RECORD"])
        with zipfile.ZipFile(whl, "w") as z:
            for n, c in files.items(): z.writestr(n, c)
            z.writestr("aiwsdemo-1.0.dist-info/RECORD", record)
        return d
    def test_download_then_offline_build_sees_the_dependency(self):
        idx = self.make_index(); self.w("requirements.txt", "aiwsdemo==1.0\n"); self.w("main.py", "import aiwsdemo\nprint('VALUE', aiwsdemo.VALUE)\n")
        _, go = B.deps_request({"language": "python"}, self.p, self.scratch, B.find_tool, self.cache, PROXY, {"PIP_NO_INDEX": "1", "PIP_FIND_LINKS": str(idx)})
        res = go(); self.assertEqual(res["exitCode"], 0, res["output"]); self.assertTrue((self.p / ".aiws-deps" / "aiwsdemo" / "__init__.py").is_file())
        _, run = B.run_request({"language": "python", "action": "run", "target": "main.py"}, self.p, self.scratch, cache=self.cache); out = run()
        self.assertEqual(out["exitCode"], 0, out["output"]); self.assertIn("VALUE 42", out["output"])
    def test_without_the_dependency_the_offline_build_fails_and_does_not_reach_out(self):
        self.w("main.py", "import aiwsdemo\n"); _, run = B.run_request({"language": "python", "action": "run", "target": "main.py"}, self.p, self.scratch, cache=self.cache)
        res = run(); self.assertNotEqual(res["exitCode"], 0); self.assertIn("ModuleNotFoundError", res["output"])
    def test_source_distributions_are_refused_so_no_setup_py_runs(self):
        d = self.root / "sdist"; d.mkdir(); marker = self.root / "ran"
        import tarfile, io
        with tarfile.open(d / "evil-1.0.tar.gz", "w:gz") as tf:
            for name, content in (("evil-1.0/setup.py", "open(%r,'w').write('x')\nfrom setuptools import setup\nsetup(name='evil',version='1.0')\n" % str(marker)), ("evil-1.0/PKG-INFO", "Metadata-Version: 1.0\nName: evil\nVersion: 1.0\n")):
                b = content.encode(); ti = tarfile.TarInfo(name); ti.size = len(b); tf.addfile(ti, io.BytesIO(b))
        self.w("requirements.txt", "evil==1.0\n")
        _, go = B.deps_request({"language": "python"}, self.p, self.scratch, B.find_tool, self.cache, PROXY, {"PIP_NO_INDEX": "1", "PIP_FIND_LINKS": str(d)})
        res = go(); self.assertNotEqual(res["exitCode"], 0); self.assertFalse(marker.exists(), "a setup.py was executed")

def git(cwd, *a, env=None):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, check=True, capture_output=True, text=True, env=env)

@unittest.skipUnless(shutil.which("git"), "no git")
class GitCommit(Proj):
    def setUp(self):
        super().setUp(); git(self.p, "init", "-q"); self.home = self.scratch.get()
    def commit(self, **args):
        command, plan = G.plan_commit(args, self.p); return command, G.commit(plan, self.p, self.home)
    def log(self): return git(self.p, "log", "--format=%s%n%an").stdout.split("\n")
    def test_commits_everything_with_a_default_identity(self):
        self.w("a.txt", "1"); self.w("d/b.txt", "2"); cmd, out = self.commit(message="first commit")
        self.assertIn("committed:", out); self.assertEqual(self.log()[:2], ["first commit", "AIWS Builder"]); self.assertIn("git commit", cmd); self.assertEqual(git(self.p, "status", "--short").stdout, "")
    def test_only_the_listed_paths_are_staged(self):
        self.w("a.txt", "1"); self.w("b.txt", "2"); self.commit(message="m", paths=["a.txt"])
        self.assertEqual(git(self.p, "ls-files").stdout.split(), ["a.txt"]); self.assertIn("b.txt", git(self.p, "status", "--short").stdout)
    def test_a_deleted_file_can_be_committed(self):
        self.w("a.txt", "1"); self.commit(message="add"); (self.p / "a.txt").unlink(); self.commit(message="remove", paths=["a.txt"]); self.assertEqual(git(self.p, "ls-files").stdout, "")
    def test_nothing_to_commit_is_reported_plainly(self):
        self.w("a.txt", "1"); self.commit(message="m"); self.assertIn("nothing to commit", self.commit(message="again")[1])
    def test_a_message_that_looks_like_an_option_is_just_a_message(self):
        self.w("a.txt", "1"); self.commit(message="--amend"); self.assertEqual(self.log()[0], "--amend")
    def test_hooks_from_the_repository_never_run(self):
        marker = self.root / "hook-ran"; hook = self.p / ".git" / "hooks" / "pre-commit"; hook.write_text("#!/bin/sh\ntouch %s\n" % marker); hook.chmod(0o755)
        self.w("a.txt", "1"); self.assertIn("committed:", self.commit(message="m")[1]); self.assertFalse(marker.exists(), "a repository hook ran")
    def test_commands_configured_in_the_repository_do_not_run(self):
        marker = self.root / "cfg-ran"; cfg = self.p / ".git" / "config"
        cfg.write_text(cfg.read_text() + "[core]\n\tfsmonitor = touch %s\n\teditor = touch %s\n[diff]\n\texternal = touch %s\n" % (marker, marker, marker))
        self.w("a.txt", "1"); self.commit(message="m"); self.assertFalse(marker.exists(), "a command from the repository config ran")
    def test_must_be_the_root_of_its_own_repository(self):
        sub = self.p / "inner"; sub.mkdir(); (sub / "a.txt").write_text("1")
        _, plan = G.plan_commit({"message": "m"}, sub); self.assertIn("root of its own git repository", G.commit(plan, sub, self.home))
        plain = self.root / "plain"; plain.mkdir(); _, plan = G.plan_commit({"message": "m"}, plain); self.assertIn("not a git repository", G.commit(plan, plain, self.home))
    def test_inputs_are_validated(self):
        (self.p / "link").symlink_to(self.root)
        for args in ({"message": ""}, {"message": "x" * 501}, {"message": "a\x00b"}, {"message": 5}, {}, {"message": "m", "paths": "a"}, {"message": "m", "paths": ["../x"]}, {"message": "m", "paths": ["-A"]},
                     {"message": "m", "paths": ["/etc/passwd"]}, {"message": "m", "paths": [".git/config"]}, {"message": "m", "paths": ["link"]}, {"message": "m", "paths": ["a"] * 21},
                     {"message": "m", "remote": "origin"}, {"message": "m", "push": True}):
            with self.assertRaises(B.BuildError, msg=args): G.plan_commit(args, self.p)
    def test_there_is_no_way_to_push_or_rewrite_history(self):
        src = (HERE.parent / "runtime" / "aiws_git_tool.py").read_text()
        for word in ('"push"', '"pull"', '"fetch"', '"reset"', '"rebase"', '"checkout"', '"clean"', '"remote"', '"--force"'): self.assertNotIn(word, src)

class InTheAgent(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.proj = Path(self.t.name).resolve() / "app"; self.proj.mkdir(); os.environ["AIWS_WORKSPACE"] = str(self.proj); self.out, self.decisions = [], []
        os.environ["AIWS_DEP_CACHE"] = str(Path(self.t.name) / "cache")
    def tearDown(self):
        os.environ.pop("AIWS_WORKSPACE", None); os.environ.pop("AIWS_DEP_CACHE", None); self.t.cleanup()
    def mandate(self, **kw):
        m = {"projectDir": "app", "allowedTools": ["file.read", "build.run", "deps.install", "git.commit"], "model": "deepseek-flash", "thinking": True, "effort": "high", "maxTurns": 12,
             "tokenBudget": {"input": 10 ** 7, "output": 10 ** 6}, "wallClockMinutes": 5, "needApprovalFor": ["build", "commit", "network", "shell", "outside-project"], "planApproval": False}
        m.update(kw); return m
    def go(self, script, exec_ok=True, **mk):
        fake = FakeDeepSeek(script); self.addCleanup(fake.close); self.fake = fake
        client = D.Client(lambda: KEY, base_url=fake.url, allow_loopback=True, sleep=lambda d: None)
        A.run({"mandate": self.mandate(**mk), "task": "x", "language": "en", "project": str(self.proj), "exec": exec_ok}, self.out.append, lambda: self.decisions.pop(0) if self.decisions else None, client)
    def tool_msgs(self, i=1): return [m["content"] for m in self.fake.requests[i]["body"]["messages"] if m["role"] == "tool"]
    def names(self): return [t["function"]["name"] for t in self.fake.requests[0]["body"]["tools"]]
    def test_toolbox_depends_on_whether_running_programs_is_allowed(self):
        self.go([reply("ok")], exec_ok=False); self.assertEqual({"git__commit"}, {n for n in self.names() if n in ("build__run", "deps__install", "git__commit")})
        self.go([reply("ok")], exec_ok=True); self.assertEqual({"build__run", "deps__install", "git__commit"}, {n for n in self.names() if n in ("build__run", "deps__install", "git__commit")})
    def test_deps_install_always_asks_because_network_approval_cannot_be_switched_off(self):
        (self.proj / "requirements.txt").write_text("x\n"); self.decisions = [{"id": "g1", "approve": False}]
        os.environ["HTTPS_PROXY"] = "http://127.0.0.1:3128"; self.addCleanup(os.environ.pop, "HTTPS_PROXY", None)
        self.go([reply("", [tool_call("deps__install", {"language": "python"})]), reply("ok")])
        g = [o for o in self.out if o["t"] == "gate"][0]; self.assertEqual((g["category"], g["tool"]), ("network", "deps.install")); self.assertIn("pip", g["detail"]); self.assertIn("did not approve", self.tool_msgs()[0])
    def test_deps_install_without_a_proxy_is_an_error_and_asks_nothing(self):
        (self.proj / "requirements.txt").write_text("x\n"); os.environ.pop("HTTPS_PROXY", None); os.environ.pop("https_proxy", None)
        self.go([reply("", [tool_call("deps__install", {"language": "python"})]), reply("ok")]); self.assertIn("No network route", self.tool_msgs()[0]); self.assertEqual([o for o in self.out if o["t"] == "gate"], [])
    @unittest.skipUnless(shutil.which("git"), "no git")
    def test_commit_asks_then_commits_and_refusal_leaves_the_repository_untouched(self):
        git(self.proj, "init", "-q"); (self.proj / "a.txt").write_text("1")
        self.decisions = [{"id": "g1", "approve": False}]
        self.go([reply("", [tool_call("git__commit", {"message": "work"})]), reply("ok")])
        g = [o for o in self.out if o["t"] == "gate"][0]; self.assertEqual((g["category"], g["tool"]), ("commit", "git.commit")); self.assertEqual(git(self.proj, "log", "--oneline").returncode if False else subprocess.run(["git", "log"], cwd=self.proj, capture_output=True).returncode, 128)
        self.out.clear(); self.decisions = [{"id": "g1", "approve": True}]
        self.go([reply("", [tool_call("git__commit", {"message": "work"})]), reply("ok")]); self.assertIn("committed:", self.tool_msgs()[0]); self.assertIn("work", git(self.proj, "log", "--format=%s").stdout)
    def test_sub_agents_get_none_of_the_action_tools(self):
        self.go([reply("", [tool_call("agent__spawn", {"task": "t", "allow_writes": True})]), reply("x"), reply("ok")], allowedTools=["file.read", "build.run", "deps.install", "git.commit", "agent.spawn"])
        child = [t["function"]["name"] for t in self.fake.requests[1]["body"]["tools"]]; self.assertTrue({"build__run", "deps__install", "git__commit"}.isdisjoint(child))
    def test_prompt_rules_appear_only_for_the_tools_that_exist(self):
        self.go([reply("ok")], exec_ok=False); p = self.fake.requests[0]["body"]["messages"][0]["content"]; self.assertIn("git_commit", p); self.assertNotIn("deps_install", p); self.assertNotIn("build_run", p)
        self.go([reply("ok")], exec_ok=True); p = self.fake.requests[0]["body"]["messages"][0]["content"]; self.assertTrue(all(w in p for w in ("git_commit", "deps_install", "build_run")))

class Mandate(unittest.TestCase):
    def test_new_tools_and_categories_are_accepted_and_the_mandatory_ones_stay(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); ws = Path(t.name); (ws / "app").mkdir()
        base = {"provider": "deepseek", "projectDir": "app", "allowedTools": ["file.read", "deps.install", "git.commit"], "maxTurns": 5, "tokenBudget": {"input": 10, "output": 10}, "wallClockMinutes": 5,
                "needApprovalFor": ["commit", "network", "shell", "outside-project"]}
        m = validate_mandate(base, ws); self.assertIn("git.commit", m["allowedTools"]); self.assertIn("commit", m["needApprovalFor"])
        with self.assertRaises(MandateError): validate_mandate({**base, "needApprovalFor": ["commit"]}, ws)
        self.assertTrue({"build.run", "deps.install", "git.commit"} <= set(A.NATIVE_TOOLS))

if __name__ == "__main__":
    unittest.main()
