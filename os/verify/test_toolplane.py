"""Offline tests of the exact AIWS OS tool API, no privileged execution."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))
import aiws_toolplane as plane
import aiws_mcp

class ToolPlaneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aiws-tool-test-")
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

    def test_catalog_and_mcp_protocol(self):
        names = {x["name"] for x in plane.catalog()}
        self.assertTrue({"file.read", "file.replace", "code.search",
                         "git.inspect", "runtime.test", "browser.snapshot"}.issubset(names))
        message = aiws_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        mcp_names={item["name"] for item in message["result"]["tools"]}
        self.assertTrue(mcp_names.issubset(names))
        self.assertIn("file.read", mcp_names)
        self.assertIn("code.symbols", mcp_names)
        self.assertNotIn("file.replace", mcp_names)
        self.assertNotIn("runtime.test", mcp_names)
        self.assertNotIn("project.scaffold", mcp_names)
        init = aiws_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "initialize"})
        self.assertIn("serverInfo", init["result"])

    def test_mcp_cannot_bypass_approval_with_mutating_tools(self):
        response = aiws_mcp.handle({"jsonrpc": "2.0", "id": 17,
            "method": "tools/call", "params": {"name": "file.replace",
                "arguments": {"path": "escape.txt", "text": "bypass",
                              "expectedSha256": ""}}})
        self.assertTrue(response["result"]["isError"])
        self.assertFalse((self.root / "escape.txt").exists())

    def test_file_read_write_sha_precondition(self):
        first = plane.invoke("file.replace",
                             {"path": "demo.py", "text": "print('hi')\n", "expectedSha256": ""})
        read = plane.invoke("file.read", {"path": "demo.py"})
        self.assertEqual(read["sha256"], first["sha256"])
        with self.assertRaisesRegex(ValueError, "Conflict"):
            plane.invoke("file.replace",
                         {"path": "demo.py", "text": "bad", "expectedSha256": "0" * 64})
        after = plane.invoke("file.replace",
                             {"path": "demo.py", "text": "pass\n", "expectedSha256": first["sha256"]})
        self.assertEqual(after["sha256"], hashlib.sha256(b"pass\n").hexdigest())

    def test_reject_escape_symlink_git_and_root(self):
        (self.root / "outside").symlink_to(Path(self.temp.name), target_is_directory=True)
        for path in ("../secret", "/etc/passwd", "outside/nonexistent",
                     ".git/config", ".ssh/id_rsa"):
            with self.assertRaises((ValueError, FileNotFoundError)):
                plane.invoke("file.read", {"path": path})
        with patch.dict(os.environ, {"AIWS_WORKSPACE": "/"}):
            with self.assertRaises(ValueError):
                plane.invoke("runtime.detect", {})

    def test_tree_search_and_html_reader(self):
        (self.root / "demo.txt").write_text("alpha beta\nbeta\n", encoding="utf-8")
        (self.root / "test.html").write_text("<h1>Title</h1><script>secret()</script><p>Hello</p>", encoding="utf-8")
        listing = plane.invoke("workspace.tree", {})
        self.assertIn("demo.txt", listing["files"])
        search = plane.invoke("code.search", {"query": "beta"})
        self.assertEqual(len([x for x in search["matches"] if x["path"] == "demo.txt"]), 2)
        body = plane.invoke("browser.local_text", {"path": "test.html"})["text"]
        self.assertIn("Title", body)
        self.assertNotIn("secret()", body)

    def test_browser_opt_in_and_fixed_execution_profiles(self):
        with patch.dict(os.environ, {"AIWS_BROWSER_ALLOWED_ORIGINS": "", "AIWS_ALLOW_EXEC": ""}):
            with self.assertRaises(PermissionError):
                plane.invoke("browser.snapshot", {"url": "https://example.com"})
            with self.assertRaises(PermissionError):
                plane.invoke("runtime.test", {"language": "python"})
        with self.assertRaises(ValueError):
            plane.invoke("runtime.test", {"language": "unrestricted-shell"})
        with self.assertRaises(ValueError):
            plane.invoke("file.replace",
                         {"path": "abc", "text": "foo", "expectedSha256": "", "extra": "unsafe"})

    def test_stdio_jsonrpc_is_machine_readable(self):
        runner = RUNTIME / "aiws_mcp.py"
        process = subprocess.run([sys.executable, str(runner)],
                                 input='{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n',
                                 text=True, capture_output=True, check=True, timeout=10)
        self.assertIn("tools", __import__("json").loads(process.stdout)["result"])
        self.assertEqual(process.stderr, "")

if __name__ == "__main__":
    unittest.main()
