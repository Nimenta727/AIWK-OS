"""Cross-platform Windows/macOS source authoring contract. No SDK or compiler is needed."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))
import aiws_toolplane as plane
import aiws_mcp

class CrossPlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "work"
        self.root.mkdir()
        self.workspace = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root)}, clear=False)
        self.workspace.start()

    def tearDown(self):
        self.workspace.stop()
        self.temp.cleanup()

    def test_api_catalog_exposes_scoped_platform_operations(self):
        by_name = {t["name"]: t for t in plane.catalog()}
        self.assertIn("platform.inspect", by_name)
        self.assertIn("project.scaffold", by_name)
        self.assertEqual(by_name["project.scaffold"]["inputSchema"]["required"], ["name", "template"])
        self.assertEqual(by_name["platform.inspect"]["inputSchema"]["required"], [])

    def test_windows_project_created_as_source_only(self):
        with patch.dict(os.environ, {"AIWS_ALLOW_SCAFFOLD": "1"}):
            result = plane.invoke("project.scaffold", {"name": "HelloWin", "template": "windows-wpf"})
        self.assertFalse(result["compiled"])
        xml = ET.fromstring((self.root/"HelloWin"/"HelloWin.csproj").read_text())
        self.assertEqual(xml.tag, "Project")
        self.assertIn("net10.0-windows", (self.root/"HelloWin"/"HelloWin.csproj").read_text())
        analysis = plane.invoke("platform.inspect", {"path": "HelloWin"})
        self.assertIn("windows", [x["platform"] for x in analysis["platformCandidates"]])
        self.assertGreaterEqual(len(result["createdFiles"]), 6)
        self.assertEqual(analysis["operation"], "source-inspection-only")
        self.assertEqual(result["executed"], False)

    def test_macos_project_created_with_swiftui_and_xcodegen_config(self):
        with patch.dict(os.environ, {"AIWS_ALLOW_SCAFFOLD": "1"}):
            result = plane.invoke("project.scaffold", {"name": "HelloMac", "template": "macos-swiftui"})
        self.assertFalse(result["compiled"])
        self.assertIn("platform: macOS", (self.root/"HelloMac"/"project.yml").read_text())
        self.assertIn("import SwiftUI", (self.root/"HelloMac"/"Sources"/"HelloMacApp.swift").read_text())
        self.assertFalse((self.root/"HelloMac"/"HelloMac.xcodeproj").exists())
        report = plane.invoke("platform.inspect", {"path": "HelloMac"})
        self.assertIn("swift", [x["platform"] for x in report["platformCandidates"]])
        self.assertIn("Xcode", (self.root/"HelloMac"/"README.md").read_text())

    def test_no_overwrite_or_path_escape(self):
        with patch.dict(os.environ, {"AIWS_ALLOW_SCAFFOLD": "1"}):
            for invalid in ("../x", ".ssh", "my-project", "a/b", "a\\b", "éx", ""):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    plane.invoke("project.scaffold", {"name": invalid, "template": "windows-wpf"})
            with self.assertRaises(ValueError):
                plane.invoke("project.scaffold", {"name": "Hello", "template": "unknown"})
            project = self.root/"Existing"
            project.mkdir()
            (project/"sentinel").write_text("keep")
            with self.assertRaises(FileExistsError):
                plane.invoke("project.scaffold", {"name": "Existing", "template": "macos-swiftui"})
            self.assertEqual((project/"sentinel").read_text(), "keep")

    def test_generation_needs_explicit_guest_opt_in(self):
        with patch.dict(os.environ, {"AIWS_ALLOW_SCAFFOLD": ""}):
            with self.assertRaises(PermissionError):
                plane.invoke("project.scaffold", {"name": "Nope", "template": "windows-wpf"})
        self.assertFalse((self.root/"Nope").exists())

    def test_platform_inspect_handles_existing_project_without_execution(self):
        project = self.root/"External"
        project.mkdir()
        (project/"Studio.sln").write_text("Microsoft Visual Studio Solution File")
        (project/"xcodeproj").mkdir()
        (project/"App.swift").write_text("import SwiftUI")
        (project/"main.py").write_text("pass")
        out = plane.invoke("platform.inspect", {"path": "External"})
        candidates = {x["platform"] for x in out["platformCandidates"]}
        self.assertTrue({"windows", "swift", "cross-platform"}.issubset(candidates))
        self.assertFalse(out["compiled"])

    def test_mcp_read_only_platform_inspection_and_scaffold_rejection(self):
        # Opt-in environment flags must never grant a direct public MCP write.
        with patch.dict(os.environ, {"AIWS_ALLOW_SCAFFOLD": "1"}):
            rejected = aiws_mcp.handle({"jsonrpc": "2.0", "id": 4,
                                        "method": "tools/call",
                                        "params": {"name": "project.scaffold",
                                                   "arguments": {"name": "FromAgent",
                                                                 "template": "macos-swiftui"}}})
        self.assertTrue(rejected["result"]["isError"])
        self.assertFalse((self.root / "FromAgent").exists())
        denied = aiws_mcp.handle({"jsonrpc": "2.0", "id": 5,
                                  "method": "tools/call",
                                  "params": {"name": "project.scaffold",
                                             "arguments": {"name": "../outside",
                                                           "template": "windows-wpf"}}})
        self.assertTrue(denied["result"]["isError"])
        (self.root / "Example.swift").write_text("import SwiftUI")
        with patch.object(aiws_mcp, "AgentClient") as agent:
            agent.return_value.request.side_effect = lambda op, req: plane.invoke(
                req["tool"], req["arguments"])
            checked = aiws_mcp.handle({"jsonrpc": "2.0", "id": 6,
                                       "method": "tools/call",
                                       "params": {"name": "platform.inspect",
                                                  "arguments": {"path": "."}}})
            agent.return_value.request.assert_called_once_with(
                "tool.read", {"tool": "platform.inspect", "arguments": {"path": "."}})
        self.assertFalse(checked["result"]["isError"])
        self.assertFalse(json.loads(checked["result"]["content"][0]["text"])["compiled"])

if __name__ == "__main__":
    unittest.main()
