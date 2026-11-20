"""Code intelligence tests run offline with no platform SDK, project build or CLI exec."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import json
RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))
import aiws_toolplane as plane
import aiws_mcp

class CodeIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "workspace"
        self.root.mkdir()
        self.env = patch.dict(os.environ, {"AIWS_WORKSPACE": str(self.root)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def put(self, name, contents):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        return path

    def test_csharp_definitions_refs_skip_comments_and_literals(self):
        self.put("App/Models.cs", """namespace Example.Core;
public class TaskModel {
  public string Name { get; set; }
  public void Reload() {}
}
// TaskModel in comment
var unused = "TaskModel in string";
""")
        self.put("App/Use.cs", """using Example.Core;
public class Controller {
  public TaskModel Current;
  public void Update() { TaskModel model; }
}
""")
        sym = plane.invoke("code.symbols", {"query": "TaskModel"})
        self.assertEqual(sym["count"], 1)
        self.assertEqual(sym["symbols"][0]["qualifiedName"], "Example.Core.TaskModel")
        ref = plane.invoke("code.references", {"symbol": "TaskModel"})
        self.assertEqual(len(ref["definitions"]), 1)
        self.assertEqual(len(ref["references"]), 2)
        self.assertEqual({x["path"] for x in ref["references"]}, {"App/Use.cs"})
        self.assertFalse(ref["semanticVerified"])

    def test_swift_struct_functions_and_crossfile_refs(self):
        self.put("App/Sources/ContentView.swift", """import SwiftUI
struct ContentView: View {
  @State private var count = 0
  var body: some View {
    Button("Tap") { update() }
  }
  func update() {}
}
""")
        self.put("App/Sources/App.swift", """import SwiftUI
struct MainApp: App {
  var body: some Scene { WindowGroup { ContentView() } }
}
""")
        symbols = plane.invoke("code.symbols", {"path": "App"})
        self.assertIn("ContentView", {x["name"] for x in symbols["symbols"]})
        self.assertIn("update", {x["name"] for x in symbols["symbols"]})
        refs = plane.invoke("code.references", {"path": "App", "symbol": "ContentView"})
        self.assertTrue(any(x["path"] == "App/Sources/App.swift" for x in refs["references"]))
        apis = plane.invoke("code.platformApis", {"path": "App"})
        self.assertIn("SwiftUI", {x["apiFamily"] for x in apis["usages"]})

    def test_windows_apis_and_msbuild_dependencies_are_static(self):
        self.put("Win/Win.csproj", """<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><TargetFramework>net10.0-windows</TargetFramework><UseWPF>true</UseWPF></PropertyGroup>
<ItemGroup>
<PackageReference Include="System.Text.Json" Version="10.0.0" />
<ProjectReference Include="..\\Common\\Common.csproj" />
<FrameworkReference Include="Microsoft.WindowsDesktop.App.WPF" />
</ItemGroup></Project>""")
        self.put("Win/View.cs", """using System.Windows;
using Microsoft.UI.Xaml;
using System.Runtime.InteropServices;
public class Viewer { [DllImport("user32.dll")] public static extern void Show(); }
""")
        result = plane.invoke("code.dependencies", {"path": "Win"})
        self.assertEqual({x["kind"] for x in result["items"]},
                         {"PackageReference", "ProjectReference", "FrameworkReference"})
        self.assertEqual(result["projects"][0]["properties"]["UseWPF"], "true")
        self.assertFalse(result["evaluated"])
        api = plane.invoke("code.platformApis", {"path": "Win"})
        self.assertTrue({"WPF", "WinUI", "interop", "Win32 interop"}.issubset(
            {x["apiFamily"] for x in api["usages"]}))

    def test_swift_package_and_resolved_pins_are_not_executed(self):
        self.put("App/Package.swift", """// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "App", dependencies: [
  .package(url: "https://example.org/a.git", from: "1.2.3"),
  .product(name: "A", package: "a")
])""")
        self.put("App/Package.resolved", json.dumps(
            {"pins": [{"identity": "a", "state": {"version": "1.2.4"}}]}))
        d = plane.invoke("code.dependencies", {"path": "App"})
        self.assertTrue({"SwiftPackage", "SwiftProduct", "SwiftResolvedPin"}.issubset(
            {x["kind"] for x in d["items"]}))
        self.assertFalse(d["evaluated"])

    def test_invalid_xml_gracefully_reported_and_symlinks_not_followed(self):
        self.put("Project/Broken.csproj", "<Project><ItemGroup>")
        outside = Path(self.tmp.name) / "external"
        outside.mkdir()
        (outside / "Danger.cs").write_text("public class External {}")
        (self.root / "Project" / "alias").symlink_to(outside, target_is_directory=True)
        dep = plane.invoke("code.dependencies", {"path": "Project"})
        self.assertIn("invalid-xml", {x["reason"] for x in dep["issues"]})
        symbols = plane.invoke("code.symbols", {"path": "Project"})
        self.assertEqual(symbols["count"], 0)
        with self.assertRaises(ValueError):
            plane.invoke("code.symbols", {"path": "Project/alias"})

    def test_duplicate_name_is_ambiguous_not_semantically_resolved(self):
        self.put("One.cs", "public class Shared {}")
        self.put("Two.cs", "internal class Shared {}")
        self.put("Use.cs", "public class Uses { public Shared data; }")
        refs = plane.invoke("code.references", {"symbol": "Shared"})
        self.assertEqual(len(refs["definitions"]), 2)
        self.assertTrue(refs["ambiguous"])
        self.assertTrue(refs["references"])

    def test_limits_do_not_claim_complete_results(self):
        self.put("large.cs", "public class Huge { }\n" * 16000)
        result = plane.invoke("code.symbols", {})
        self.assertTrue(result["issues"])
        self.assertEqual(result["count"], 0)

    def test_xaml_class_binding_and_wpf_markup_evidence(self):
        self.put("Win/MainWindow.xaml", """<Window x:Class="Sample.MainWindow"
            xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
            xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
            <Button Content="Hello"/>
            </Window>""")
        self.put("Win/MainWindow.xaml.cs", "namespace Sample; public partial class MainWindow {}")
        references = plane.invoke("code.references", {"path": "Win", "symbol": "MainWindow"})
        self.assertTrue(any(x["path"] == "Win/MainWindow.xaml" and
                            x["confidence"] == "declarative-class-binding" for x in references["references"]))
        usages = plane.invoke("code.platformApis", {"path": "Win"})
        self.assertIn("WPF XAML", {u["apiFamily"] for u in usages["usages"]})

    def test_dtd_and_entities_in_project_manifest_are_rejected(self):
        self.put("Win/Hazard.csproj", """<!DOCTYPE Project [<!ENTITY x "EXPANDED">]>
<Project><ItemGroup><PackageReference Include="&x;"/></ItemGroup></Project>""")
        result = plane.invoke("code.dependencies", {"path": "Win"})
        self.assertIn("xml-dtd-rejected", {i["reason"] for i in result["issues"]})
        self.assertEqual(result["items"], [])

    def test_mcp_end_to_end_and_optional_schema(self):
        self.put("Example.swift", "struct Demo {}\n")
        tools = {x["name"]: x for x in plane.catalog()}
        self.assertEqual(tools["code.references"]["inputSchema"]["required"], ["symbol"])
        for name in ("code.symbols", "code.dependencies", "code.platformApis"):
            self.assertEqual(tools[name]["inputSchema"]["required"], [])
        reply = aiws_mcp.handle({"jsonrpc": "2.0", "id": 33, "method": "tools/call",
                                 "params": {"name": "code.symbols", "arguments": {"query": "Demo"}}})
        self.assertFalse(reply["result"]["isError"])
        self.assertEqual(json.loads(reply["result"]["content"][0]["text"])["count"], 1)

if __name__ == "__main__":
    unittest.main()
