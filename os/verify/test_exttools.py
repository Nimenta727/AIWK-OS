"""Declarative external read-only tools: argv construction, confinement, bounds, and the sqlite authorizer."""
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import aiws_exttools as X
import aiws_toolplane as T

class Proc:
    returncode = 0; stdout = "out"; stderr = ""

class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root), "SECRET_TOKEN": "leak"}); self.env.start()
        self.p = patch("aiws_toolplane.protect_guest_workspace", return_value=True); self.p.start()
        self.seen = []

    def tearDown(self):
        self.p.stop(); self.env.stop(); self.temp.cleanup()

    def run_tool(self, name, args):
        def runner(argv, **kw):
            self.seen.append((argv, kw)); return Proc()
        return X.run(name, args, self.root, T._path, T._safe_env(), which=lambda n: "/usr/bin/" + n, runner=runner)

class CatalogTests(unittest.TestCase):
    def test_tools_are_in_the_catalog_as_read_tools_with_correct_required(self):
        cat = {t["name"]: t for t in T.catalog()}
        for name in X.EXT:
            self.assertIn(name, cat); self.assertIn(name, T.READ_TOOLS)
        self.assertEqual(cat["ext.rg"]["inputSchema"]["required"], ["pattern"])
        self.assertEqual(cat["ext.sqlite"]["inputSchema"]["required"], ["path", "query"])
        self.assertEqual(cat["ext.gitlog"]["inputSchema"]["required"], [])

    def test_no_external_tool_can_write_or_launch(self):
        self.assertFalse(set(X.EXT) & T.FILE_WRITE_TOOLS); self.assertFalse(set(X.EXT) & T.APP_LAUNCH_TOOLS)

class ArgvTests(Base):
    def test_values_are_single_argv_elements_after_a_separator(self):
        (self.root / "src").mkdir()
        self.run_tool("ext.rg", {"pattern": "--files; rm -rf /", "path": "src"})
        argv, kw = self.seen[0]
        self.assertEqual(argv[0], "/usr/bin/rg")
        self.assertIn("-e", argv); self.assertEqual(argv[argv.index("-e") + 1], "--files; rm -rf /")   # a value, never an option
        self.assertEqual(argv[-2:], ["--", "src"])
        self.assertFalse(kw.get("shell")); self.assertNotIn("SECRET_TOKEN", kw["env"])
        self.assertEqual(kw["cwd"], str(self.root)); self.assertLessEqual(kw["timeout"], 30)

    def test_defaults_and_optional_path_for_git_log(self):
        self.run_tool("ext.gitlog", {})
        self.assertEqual(self.seen[0][0][-2:], ["--max-count", "20"])         # no pathspec: the "--" and placeholder are dropped
        self.run_tool("ext.gitlog", {"count": "5"})
        self.assertIn("5", self.seen[1][0])

    def test_jq_filter_cannot_become_an_option(self):
        (self.root / "d.json").write_text("{}")
        with self.assertRaises(X.ExtToolError):
            self.run_tool("ext.jq", {"filter": "-n", "path": "d.json"})
        self.run_tool("ext.jq", {"filter": ".a", "path": "d.json"})
        self.assertEqual(self.seen[0][0][-3:], ["--", ".a", "d.json"])

    def test_bad_arguments_never_reach_the_program(self):
        (self.root / "f.txt").write_text("x")
        bad = [("ext.rg", {}), ("ext.rg", {"pattern": ""}), ("ext.rg", {"pattern": "a\x00b"}), ("ext.rg", {"pattern": "x" * 300}),
               ("ext.rg", {"pattern": "x", "path": "../etc"}), ("ext.rg", {"pattern": "x", "path": "/etc"}),
               ("ext.rg", {"pattern": "x", "extra": "--pre=sh"}), ("ext.rg", {"pattern": 5}),
               ("ext.gitlog", {"count": "0"}), ("ext.gitlog", {"count": "51"}), ("ext.gitlog", {"count": "-1"}),
               ("ext.jq", {"filter": ".", "path": "missing.json"}), ("ext.jq", {"filter": ".", "path": "."}),
               ("nope", {})]
        for name, args in bad:
            with self.assertRaises((X.ExtToolError, ValueError, FileNotFoundError), msg=(name, args)):
                self.run_tool(name, args)
        self.assertEqual(self.seen, [])

    def test_symlinks_and_protected_dirs_are_refused(self):
        (self.root / "t.json").write_text("{}"); (self.root / "l.json").symlink_to(self.root / "t.json")
        for path in ("l.json", ".git/config"):
            with self.assertRaises(ValueError):
                self.run_tool("ext.jq", {"filter": ".", "path": path})

    def test_missing_program_is_a_clear_error_and_output_is_capped(self):
        with self.assertRaises(FileNotFoundError):
            X.run("ext.rg", {"pattern": "x"}, self.root, T._path, {}, which=lambda n: None)
        class Big(Proc):
            stdout = "a" * (X.OUT_LIMIT + 10)
        out = X.run("ext.rg", {"pattern": "x"}, self.root, T._path, {}, which=lambda n: "/b/" + n, runner=lambda *a, **k: Big())
        self.assertEqual((len(out["stdout"]), out["truncated"]), (X.OUT_LIMIT, True))

@unittest.skipUnless(shutil.which("rg") and shutil.which("jq"), "ripgrep and jq not installed here")
class RealProgramTests(Base):
    def test_rg_and_jq_really_run_without_a_shell(self):
        (self.root / "a.txt").write_text("alpha\nbeta needle\n"); (self.root / "d.json").write_text('{"k":[1,2,3]}')
        r = X.run("ext.rg", {"pattern": "needle"}, self.root, T._path, T._safe_env())
        self.assertIn("a.txt:2:beta needle", r["stdout"])
        j = X.run("ext.jq", {"filter": ".k | add", "path": "d.json"}, self.root, T._path, T._safe_env())
        self.assertEqual(j["stdout"].strip(), "6")

class SqliteTests(Base):
    def setUp(self):
        super().setUp()
        db = sqlite3.connect(self.root / "d.sqlite")
        db.execute("create table t(a, b)"); db.executemany("insert into t values(?,?)", [(i, "x%d" % i) for i in range(150)])
        db.commit(); db.close()

    def q(self, sql):
        return X.run("ext.sqlite", {"path": "d.sqlite", "query": sql}, self.root, T._path, {})

    def test_select_works_and_is_capped_at_100_rows(self):
        out = self.q("select a, b from t where a < 3 order by a")
        self.assertEqual((out["columns"], out["rows"]), (["a", "b"], [[0, "x0"], [1, "x1"], [2, "x2"]]))
        big = self.q("select * from t")
        self.assertEqual((len(big["rows"]), big["truncated"]), (100, True))
        self.assertEqual(self.q("with c(n) as (select 1) select n from c")["rows"], [[1]])

    def test_nothing_that_writes_or_escapes_is_accepted(self):
        before = (self.root / "d.sqlite").read_bytes()
        for sql in ("insert into t values(1,2)", "delete from t", "drop table t", "update t set a=1", "pragma writable_schema=1",
                    "attach database 'x.db' as x", "select 1; select 2", "select 1; drop table t", "create table z(a)",
                    "vacuum", "with c as (select 1) delete from t", "select load_extension('x')", ".shell id", ""):
            with self.assertRaises(X.ExtToolError, msg=sql):
                self.q(sql)
        self.assertEqual((self.root / "d.sqlite").read_bytes(), before)
        self.assertFalse(list(self.root.glob("*.db")))

    def test_not_a_database_and_wrong_paths(self):
        (self.root / "n.sqlite").write_text("plain text")
        with self.assertRaises(X.ExtToolError):
            X.run("ext.sqlite", {"path": "n.sqlite", "query": "select 1 from sqlite_master"}, self.root, T._path, {})
        with self.assertRaises(ValueError):
            X.run("ext.sqlite", {"path": "../d.sqlite", "query": "select 1"}, self.root, T._path, {})

    def test_blobs_are_summarised_not_dumped(self):
        db = sqlite3.connect(self.root / "d.sqlite"); db.execute("create table b(x)"); db.execute("insert into b values(zeroblob(5000))"); db.commit(); db.close()
        self.assertEqual(self.q("select x from b")["rows"], [["<5000 bytes>"]])

if __name__ == "__main__":
    unittest.main()
