"""Cross-platform source project authoring for AIWS OS (no Windows/macOS emulation).

This guest-user module creates *source* templates. It never invokes Apple SDKs,
Windows build tools, package downloads, signing, privileged services, or host APIs.
"""
from pathlib import Path
import os
import re

WINDOWS_SUFFIXES = {".sln", ".slnx", ".csproj", ".vcxproj", ".props", ".targets",
                    ".resx", ".rc", ".xaml", ".manifest", ".def"}
MACOS_SUFFIXES = {".swift", ".m", ".mm", ".metal", ".storyboard", ".xib",
                  ".plist", ".entitlements", ".pbxproj"}
COMMON_SUFFIXES = {".py", ".go", ".rs", ".js", ".jsx", ".ts", ".tsx",
                   ".cpp", ".c", ".h", ".hpp", ".json", ".yaml", ".yml", ".md"}
SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "bin", "obj",
        "target", "build", "dist", ".vs", "DerivedData"}
MAX_FILES = 450

def inspect_project(root: Path, relative: str, resolve_path):
    """Identify source/project conventions from names only, without running build tools."""
    folder = resolve_path(root, relative)
    if not folder.is_dir():
        raise ValueError("platform.inspect expects an existing source directory")
    files = []
    kinds = set()
    truncated = False
    for base, dirs, names in os.walk(folder, followlinks=False):
        # xcodeproj/xcworkspace are directories; report them without traversing.
        project_dirs = [d for d in dirs if d.endswith((".xcodeproj", ".xcworkspace", ".xcassets"))]
        for d in sorted(project_dirs):
            if (Path(base) / d).is_symlink():
                continue
            p = (Path(base) / d).relative_to(root).as_posix()
            if len(files) >= MAX_FILES:
                truncated = True
                break
            files.append({"path": p, "kind": "macos-project-directory"})
            kinds.add("macos")
        dirs[:] = sorted(d for d in dirs if d not in SKIP
                          and not d.endswith((".xcodeproj", ".xcworkspace", ".xcassets"))
                          and not (Path(base) / d).is_symlink())
        if truncated:
            break
        for name in sorted(names):
            p = Path(base) / name
            if p.is_symlink() or not p.is_file():
                continue
            suffix = p.suffix.lower()
            if name == "Package.swift":
                kind = "swift-package"  # Swift packages are not always Apple-only.
                kinds.add("swift")
            elif suffix in WINDOWS_SUFFIXES:
                kind = "windows-source"
                kinds.add("windows")
            elif suffix in MACOS_SUFFIXES:
                kind = "macos-source"
                kinds.add("macos" if suffix != ".swift" else "swift")
            elif suffix in COMMON_SUFFIXES:
                kind = "shared-source"
                kinds.add("shared")
            else:
                continue
            if len(files) >= MAX_FILES:
                truncated = True
                break
            files.append({"path": p.relative_to(root).as_posix(), "kind": kind})
        if truncated:
            break
    platforms = []
    if "windows" in kinds:
        platforms.append({"platform": "windows", "confidence": "source-conventions",
                          "note": "Windows project/source files found; Windows runtime not available in Linux."})
    if "macos" in kinds:
        platforms.append({"platform": "macos", "confidence": "source-conventions",
                          "note": "Apple project/source files found; Xcode and Apple SDK are not bundled."})
    if "swift" in kinds:
        platforms.append({"platform": "swift", "confidence": "language-only",
                          "note": "Swift also targets Linux; Swift files alone do not prove macOS."})
    if "shared" in kinds:
        platforms.append({"platform": "cross-platform", "confidence": "language-only",
                          "note": "Shared-language files do not guarantee portable APIs."})
    return {"path": relative, "platformCandidates": platforms,
            "files": files, "truncated": truncated, "operation": "source-inspection-only",
            "compiled": False}

def _windows(name: str):
    return {
        f"{name}.csproj": f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows</TargetFramework>
    <UseWPF>true</UseWPF>
    <EnableWindowsTargeting>true</EnableWindowsTargeting>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
""",
        "App.xaml": f"""<Application x:Class="{name}.App"
             xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
             xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
             StartupUri="MainWindow.xaml">
  <Application.Resources/>
</Application>
""",
        "App.xaml.cs": f"""namespace {name};

public partial class App : System.Windows.Application
{{
}}
""",
        "MainWindow.xaml": f"""<Window x:Class="{name}.MainWindow"
        xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="{name}" Width="960" Height="640">
  <Grid>
    <TextBlock Text="{name}: edit on AIWS OS, run on Windows"
               HorizontalAlignment="Center" VerticalAlignment="Center"/>
  </Grid>
</Window>
""",
        "MainWindow.xaml.cs": f"""using System.Windows;

namespace {name};

public partial class MainWindow : Window
{{
    public MainWindow()
    {{
        InitializeComponent();
    }}
}}
""",
        "README.md": f"""# {name} — Windows WPF source project

Created as UTF-8 source files by AIWS OS on Linux.
Edit C#, XAML, MSBuild properties and resources inside the VM.
Build and run on a Windows machine with a supported .NET SDK:
\`dotnet build {name}.csproj\`

The project is NOT compiled, installed or tested by the AIWS OS generator.
The Windows desktop APIs and WPF runtime are not available in Linux.
""",
        ".gitignore": "bin/\nobj/\n.vs/\n",
    }

def _macos(name: str):
    return {
        "project.yml": f"""name: {name}
options:
  bundleIdPrefix: org.aiws
targets:
  {name}:
    type: application
    platform: macOS
    deploymentTarget: "14.0"
    sources:
      - Sources
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: org.aiws.{name}
        GENERATE_INFOPLIST_FILE: YES
        SWIFT_VERSION: "5.0"
""",
        f"Sources/{name}App.swift": f"""import SwiftUI

@main
struct {name}App: App {{
    var body: some Scene {{
        WindowGroup {{
            ContentView()
        }}
    }}
}}
""",
        "Sources/ContentView.swift": f"""import SwiftUI

struct ContentView: View {{
    var body: some View {{
        VStack(spacing: 16) {{
            Text("{name}")
                .font(.title)
            Text("Source edited in AIWS OS on Linux")
                .foregroundStyle(.secondary)
        }}
        .padding()
    }}
}}
""",
        "README.md": f"""# {name} — macOS SwiftUI source project

Created as UTF-8 source files by AIWS OS on Linux.
Write Swift, SwiftUI, entitlements, plist and project configuration in the VM.

To create an Xcode project on a Mac, install an appropriate version of
[XcodeGen](https://github.com/yonaskolb/XcodeGen) yourself and run:
\`xcodegen generate\`
Then open \`{name}.xcodeproj\` in Xcode for build, codesign and testing.
Or create a new macOS App in Xcode and import the Sources folder.

The included project.yml is an XcodeGen recipe, NOT a generated .xcodeproj.
No Xcode, Apple frameworks, licensed SDK binaries or signing materials are
downloaded, copied, bundled or run by AIWS OS.
""",
        ".gitignore": ".DS_Store\nDerivedData/\n*.xcuserstate\n*.xcuserdata/\n",
    }

def scaffold_project(root: Path, args):
    """Create a brand-new source directory with exclusive mkdir; never overwrite."""
    if os.environ.get("AIWS_ALLOW_SCAFFOLD") != "1":
        raise PermissionError("Project generation requires AIWS_ALLOW_SCAFFOLD=1 in the guest session")
    name = args["name"]
    template = args["template"]
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", name):
        raise ValueError("Project name: ASCII letter followed by letters, digits or _, max 40")
    if template not in ("windows-wpf", "macos-swiftui"):
        raise ValueError("Template must be windows-wpf or macos-swiftui")
    if not root.is_dir():
        raise ValueError("Guest workspace not found")
    target = root / name
    # Exclusive directory creation: pre-existing names (including symlinks) fail.
    target.mkdir(mode=0o700, exist_ok=False)
    files = _windows(name) if template == "windows-wpf" else _macos(name)
    created = []
    try:
        for relative, content in files.items():
            p = target / relative
            p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with p.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
            created.append(p.relative_to(root).as_posix())
    except OSError:
        # No recursive delete: if interrupted, leave the new partial directory
        # for inspection rather than deleting any unexpected user modifications.
        raise
    return {"project": name, "template": template, "createdFiles": created,
            "compiled": False, "executed": False,
            "note": ("Sources for Windows WPF; use Windows for native build and verification."
                     if template == "windows-wpf" else
                     "Sources and XcodeGen recipe for macOS SwiftUI; use Xcode on Mac for native build.")}
