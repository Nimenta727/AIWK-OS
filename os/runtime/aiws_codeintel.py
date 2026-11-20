"""AIWS OS read-only cross-platform code intelligence (stdlib, no builds or SDK execution).

Static evidence, not compiler semantics: definitions are syntactic candidates and
references are unresolved identifier occurrences. Roslyn/SourceKit-LSP are future adapters.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

MAX_FILES = 320
MAX_BYTES = 192 * 1024
MAX_RESULTS = 120
SKIP = {".git", ".svn", ".hg", "node_modules", ".venv", "venv", "__pycache__",
        "bin", "obj", "target", "build", "dist", "DerivedData", ".vs", ".idea"}
CODE = {".cs": "csharp", ".swift": "swift"}
MANIFEST = {".csproj", ".fsproj", ".vbproj", ".props", ".targets", ".xaml", ".yml", ".yaml"}
CS_TYPE = re.compile(r"\b(class|struct|interface|enum|record)\s+(?:(?:class|struct)\s+)?([A-Za-z_]\w*)")
CS_METHOD = re.compile(r"\b(?:public|private|protected|internal)\s+(?:(?:static|virtual|override|async|sealed|new|partial|abstract|extern)\s+)*(?:[A-Za-z_][\w<>,.?\[\]]*\s+)+([A-Za-z_]\w*)\s*\(")
SWIFT_TYPE = re.compile(r"\b(class|struct|enum|protocol|actor|extension|typealias)\s+([A-Za-z_]\w*)")
SWIFT_MEMBER = re.compile(r"\b(func|var|let)\s+([A-Za-z_]\w*)")
IDENT = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*\b")
SWIFT_UI = {"View", "App", "WindowGroup", "Text", "Button", "List", "NavigationStack",
            "NavigationView", "VStack", "HStack", "ZStack", "Form", "State",
            "Binding", "ObservedObject", "StateObject", "Environment", "EnvironmentObject"}
CS_PLATFORMS = (
    ("System.Windows", "WPF"), ("Microsoft.UI.Xaml", "WinUI"),
    ("Windows.UI.Xaml", "UWP XAML"), ("Windows.Win32", "Windows API"),
    ("System.Runtime.InteropServices", "interop"),
)
SWIFT_PLATFORMS = (("SwiftUI", "SwiftUI"), ("AppKit", "AppKit"), ("UIKit", "UIKit"),
                   ("CoreData", "CoreData"), ("Combine", "Combine"))

def _position(content, index):
    return {"line": content.count("\n", 0, index) + 1,
            "column": index - (content.rfind("\n", 0, index) + 1) + 1}

def _mask(content):
    """Remove comments and quoted strings, keep newlines/offsets for exact locations.

    Handles C#/Swift common quotes, multiline Swift strings, C# verbatim strings.
    Unrecognized language constructs remain lexical evidence, not verified AST.
    """
    chars = list(content)
    n = len(chars)
    i = 0
    while i < n:
        begin = i
        token = None
        if content.startswith("//", i):
            token = "line"
            i += 2
            while i < n and chars[i] != "\n":
                i += 1
        elif content.startswith("/*", i):
            token = "block"
            i += 2
            depth = 1
            while i < n and depth:
                if content.startswith("/*", i):
                    depth += 1
                    i += 2
                elif content.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
        elif content.startswith('"""', i):
            token = "triple"
            i += 3
            while i < n:
                if content.startswith('"""', i):
                    i += 3
                    break
                i += 1
        elif content.startswith('@"', i):
            token = "verbatim"
            i += 2
            while i < n:
                if content.startswith('""', i):
                    i += 2
                elif chars[i] == '"':
                    i += 1
                    break
                else:
                    i += 1
        elif chars[i] in ('"', "'"):
            token = "quote"
            quote = chars[i]
            i += 1
            while i < n:
                if chars[i] == "\\":
                    i += 2
                elif chars[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
        else:
            i += 1
        if token:
            for j in range(begin, min(i, n)):
                if chars[j] not in ("\n", "\r"):
                    chars[j] = " "
    return "".join(chars)

def _sources(root, path, resolve_path):
    folder = resolve_path(root, path)
    if not folder.is_dir():
        raise ValueError("code intelligence path must be an existing directory")
    entries, issues, truncated = [], [], False
    scanned = 0
    for base, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and
                         not d.endswith((".xcodeproj", ".xcworkspace", ".xcassets")) and
                         not (Path(base) / d).is_symlink())
        for name in sorted(names):
            file = Path(base) / name
            if file.is_symlink() or not file.is_file():
                continue
            if file.suffix.lower() not in (set(CODE) | MANIFEST) and name not in {"Package.swift", "Package.resolved"}:
                continue
            if scanned >= MAX_FILES:
                truncated = True
                break
            scanned += 1
            try:
                if file.stat().st_size > MAX_BYTES:
                    issues.append({"path": file.relative_to(root).as_posix(), "reason": "file-too-large"})
                    continue
                raw = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                issues.append({"path": file.relative_to(root).as_posix(), "reason": "unreadable-utf8"})
                continue
            entries.append((file.relative_to(root).as_posix(), raw))
        if truncated:
            break
    return entries, issues[:24], truncated or len(issues) > 24

def _sym(raw, path, language):
    masked = _mask(raw)
    patterns = ((CS_TYPE, CS_METHOD) if language == "csharp" else (SWIFT_TYPE, SWIFT_MEMBER))
    namespace = ""
    if language == "csharp":
        ns = re.search(r"\bnamespace\s+([A-Za-z_][\w.]*)", masked)
        if ns:
            namespace = ns.group(1)
    found = []
    for pattern in patterns:
        for match in pattern.finditer(masked):
            kind, name = match.group(1), match.group(2) if pattern in (CS_TYPE, SWIFT_TYPE, SWIFT_MEMBER) else match.group(1)
            if pattern is CS_METHOD:
                kind = "method"
                name = match.group(1)
            if name in {"if", "while", "switch", "catch", "return"}:
                continue
            start = match.start(2) if pattern is not CS_METHOD else match.start(1)
            location = _position(raw, start)
            line = raw.splitlines()[location["line"] - 1].strip()[:180]
            found.append({"name": name, "qualifiedName": f"{namespace}.{name}" if namespace else name,
                          "kind": kind, "language": language, "path": path, **location,
                          "signature": line, "confidence": "syntax-pattern"})
    found.sort(key=lambda x: (x["line"], x["column"], x["name"]))
    return found, masked

def _api(raw, masked, path, language):
    usages = []
    candidates = []
    if language == "csharp":
        for namespace, family in CS_PLATFORMS:
            pattern = re.compile(r"\busing\s+(?:static\s+)?"+re.escape(namespace)+r"(?:\.[\w.]+)?\s*;")
            for m in pattern.finditer(masked):
                candidates.append((m.start(), family, namespace, "namespace-import"))
        for m in re.finditer(r"\b(?:DllImport|LibraryImport)\s*\(", masked):
            candidates.append((m.start(), "Win32 interop", m.group(0).split("(")[0], "interop-attribute"))
    elif language == "swift":
        for module, family in SWIFT_PLATFORMS:
            for m in re.finditer(r"\bimport\s+"+re.escape(module)+r"\b", masked):
                candidates.append((m.start(), family, module, "module-import"))
        if re.search(r"\bimport\s+SwiftUI\b", masked):
            for m in IDENT.finditer(masked):
                if m.group() in SWIFT_UI and m.group() not in {"SwiftUI"}:
                    candidates.append((m.start(), "SwiftUI", m.group(), "lexical-api-usage"))
    for position, family, symbol, evidence in candidates[:MAX_RESULTS]:
        usages.append({"path": path, **_position(raw, position), "apiFamily": family,
                       "symbol": symbol, "evidence": evidence, "confidence": "convention-only"})
    return usages

def _xml_manifest(path, raw):
    items, meta, problems = [], {}, []
    # Never allow DTD/entity expansion from untrusted project files.
    if "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
        return [], {}, [{"path": path, "reason": "xml-dtd-rejected"}]
    try:
        document = ET.fromstring(raw)
    except ET.ParseError:
        return [], {}, [{"path": path, "reason": "invalid-xml"}]
    for element in document.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        value = (element.text or "").strip()
        if tag in {"TargetFramework", "TargetFrameworks", "UseWPF", "UseWindowsForms", "OutputType", "Sdk"} and value:
            meta[tag] = value[:120]
        if tag not in {"ProjectReference", "PackageReference", "FrameworkReference",
                       "Reference", "PackageVersion", "Import", "COMReference"}:
            continue
        name = element.attrib.get("Include", "") or element.attrib.get("Update", "") or element.attrib.get("Project", "")
        if not name:
            continue
        version = element.attrib.get("Version", "")
        if not version:
            version = next(((c.text or "").strip() for c in element if c.tag.rsplit("}", 1)[-1] == "Version"), "")
        items.append({"manifest": path, "kind": tag, "name": name[:280],
                      "version": version[:100], "condition": element.attrib.get("Condition", "")[:160],
                      "evaluated": False})
    return items, meta, problems

def _swift_manifest(path, raw):
    items, meta, problems = [], {}, []
    masked = _mask(raw)
    # Manifest is Swift source and can compute dependencies dynamically; parse only literal declarations.
    for match in re.finditer(r"\.package\s*\(\s*url\s*:\s*['\"]([^'\"]{1,250})['\"](?:\s*,\s*(?:from|exact|branch|revision)\s*:\s*['\"]([^'\"]{1,80})['\"])?", raw):
        if masked[match.start(): match.start()+8].strip() == "":
            continue
        items.append({"manifest": path, "kind": "SwiftPackage", "name": match.group(1),
                      "version": match.group(2) or "", "condition": "", "evaluated": False})
    for match in re.finditer(r"\.product\s*\(\s*name\s*:\s*['\"]([^'\"]{1,120})['\"]\s*,\s*package\s*:\s*['\"]([^'\"]{1,120})['\"]", raw):
        items.append({"manifest": path, "kind": "SwiftProduct", "name": match.group(1),
                      "version": "", "package": match.group(2), "condition": "", "evaluated": False})
    return items, meta, problems

def _dependencies(entries):
    items, metadata, problems = [], [], []
    for path, raw in entries:
        name = Path(path).name
        ext = Path(path).suffix.lower()
        if ext in {".csproj", ".fsproj", ".vbproj", ".props", ".targets"}:
            dependencies, details, errors = _xml_manifest(path, raw)
        elif name == "Package.swift":
            dependencies, details, errors = _swift_manifest(path, raw)
        elif name == "Package.resolved":
            dependencies, details, errors = [], {}, []
            try:
                manifest = json.loads(raw)
                pins = manifest.get("pins", manifest.get("object", {}).get("pins", []))
                for pin in pins[:MAX_RESULTS]:
                    if not isinstance(pin, dict):
                        continue
                    state = pin.get("state", {})
                    dependencies.append({"manifest": path, "kind": "SwiftResolvedPin",
                                         "name": str(pin.get("identity", pin.get("package", "")))[:120],
                                         "version": str(state.get("version", state.get("revision", "")))[:100],
                                         "evaluated": False})
            except (ValueError, AttributeError):
                errors.append({"path": path, "reason": "invalid-package-resolved"})
        elif name == "project.yml":
            dependencies, details, errors = [], {}, []
            platform = re.search(r"(?m)^\s+platform:\s*([A-Za-z0-9_]+)\s*$", raw)
            if platform:
                details["XcodeGenPlatform"] = platform.group(1)
        else:
            continue
        if details:
            metadata.append({"path": path, "properties": details})
        items.extend(dependencies[:MAX_RESULTS])
        problems.extend(errors)
    return {"items": items[:MAX_RESULTS], "projects": metadata[:MAX_RESULTS],
            "issues": problems[:24], "truncated": len(items) > MAX_RESULTS or len(metadata) > MAX_RESULTS}

def _xaml(path, raw):
    """XAML class binding/source markup evidence; no type or SDK resolution."""
    refs, apis = [], []
    if "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
        return refs, apis
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return refs, apis
    for key, value in root.attrib.items():
        if key.endswith("}Class") and re.fullmatch(r"[A-Za-z_][\w.]*", value, re.ASCII):
            short = value.rsplit(".", 1)[-1]
            # We already verified the XML attribute; this is a source-position hint.
            for marker in (f'x:Class="{value}"', f"x:Class='{value}'"):
                start = raw.find(marker)
                if start < 0:
                    continue
                offset = start + marker.index(value) + len(value) - len(short)
                location = _position(raw, offset)
                refs.append({"name": short, "path": path, **location,
                             "language": "xaml",
                             "sourceLine": raw.splitlines()[location["line"]-1].strip()[:180],
                             "confidence": "declarative-class-binding", "resolution": "candidate"})
                break
    if "http://schemas.microsoft.com/winfx/2006/xaml/presentation" in raw:
        i = raw.index("http://schemas.microsoft.com/winfx/2006/xaml/presentation")
        apis.append({"path": path, **_position(raw, i), "apiFamily": "WPF XAML",
                     "symbol": "XAML presentation namespace", "evidence": "xml-namespace",
                     "confidence": "convention-only"})
    return refs, apis

def _build(root, path, resolve_path):
    entries, problems, partial = _sources(root, path, resolve_path)
    symbols, units, apis, xaml_refs = [], [], [], []
    for file, raw in entries:
        if file.endswith(".xaml"):
            references, usages = _xaml(file, raw)
            xaml_refs.extend(references)
            apis.extend(usages)
        language = CODE.get(Path(file).suffix.lower())
        if not language or file.endswith("Package.swift"):
            continue
        definitions, mask = _sym(raw, file, language)
        symbols.extend(definitions)
        units.append((file, raw, mask, language, definitions))
        apis.extend(_api(raw, mask, file, language))
    return {"symbols": symbols, "units": units, "xamlReferences": xaml_refs, "apiUsages": apis,
            "dependencies": _dependencies(entries), "filesScanned": len(entries),
            "issues": problems, "partial": partial}

def symbols(root, args, resolve_path):
    state = _build(root, args.get("path", "."), resolve_path)
    query = args.get("query", "")
    if not isinstance(query, str) or len(query) > 80:
        raise ValueError("Symbol query must be <= 80 characters")
    found = [item for item in state["symbols"] if query.casefold() in item["name"].casefold()]
    return {"symbols": found[:MAX_RESULTS], "count": len(found),
            "filesScanned": state["filesScanned"], "truncated": state["partial"] or len(found)>MAX_RESULTS,
            "issues": state["issues"], "semanticVerified": False,
            "note": "Syntax patterns only; types, overloads and scopes are not semantically resolved."}

def references(root, args, resolve_path):
    name = args["symbol"]
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_]\w{0,79}", name, re.ASCII):
        raise ValueError("symbol must be a single identifier, max 80 ASCII characters")
    state = _build(root, args.get("path", "."), resolve_path)
    defs = [s for s in state["symbols"] if s["name"] == name]
    refs = []
    token = re.compile(r"(?<![A-Za-z0-9_])"+re.escape(name)+r"(?![A-Za-z0-9_])")
    for path, raw, masked, language, definitions in state["units"]:
        declaration_sites = {(s["line"], s["column"]) for s in definitions if s["name"] == name}
        for m in token.finditer(masked):
            pos = _position(raw, m.start())
            if (pos["line"], pos["column"]) in declaration_sites:
                continue
            refs.append({"path": path, **pos, "language": language,
                         "sourceLine": raw.splitlines()[pos["line"]-1].strip()[:180],
                         "confidence": "unresolved-lexical", "resolution": "candidate"})
            if len(refs) >= MAX_RESULTS:
                break
        if len(refs) >= MAX_RESULTS:
            break
    for item in state["xamlReferences"]:
        if item["name"] == name and len(refs) < MAX_RESULTS:
            refs.append({key: value for key, value in item.items() if key != "name"})
    return {"symbol": name, "definitions": defs[:MAX_RESULTS], "references": refs,
            "ambiguous": len(defs) != 1, "filesScanned": state["filesScanned"],
            "truncated": state["partial"] or len(refs) >= MAX_RESULTS or len(defs)>MAX_RESULTS,
            "semanticVerified": False,
            "note": "Occurrences are not proven references to a definition; same-name symbols, overloads and shadowing may differ."}

def dependencies(root, args, resolve_path):
    state = _build(root, args.get("path", "."), resolve_path)
    result = state["dependencies"]
    return {**result, "filesScanned": state["filesScanned"],
            "truncated": result["truncated"] or state["partial"],
            "issues": (result["issues"]+state["issues"])[:24],
            "evaluated": False,
            "note": "MSBuild conditions, NuGet resolution and Swift manifest execution are not performed."}

def platform_apis(root, args, resolve_path):
    state = _build(root, args.get("path", "."), resolve_path)
    found = state["apiUsages"]
    return {"usages": found[:MAX_RESULTS], "count": len(found),
            "filesScanned": state["filesScanned"],
            "truncated": state["partial"] or len(found)>MAX_RESULTS, "issues": state["issues"],
            "semanticVerified": False,
            "note": "Framework imports and identifiers are heuristic evidence, not SDK type checking."}
