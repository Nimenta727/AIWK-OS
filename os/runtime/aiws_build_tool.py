"""Restricted build / test / run tool for the cloud agent. NOT a shell.

The model picks a language, an action and (optionally) one target path. Everything else is a FIXED command template: there is no
free-form argument, no pipe, no `sh -c`. Targets are validated like every other path (relative, inside the project, no symlinks,
no leading '-', right file extension). Programs run with a minimal environment (the agent's own environment, in particular any
key, is NOT passed), inside the project folder, in their own process group, with CPU / file-size limits and a hard timeout.
Output goes to a temp file (so a runaway program cannot fill memory) and only a bounded head and tail come back.

Builds are OFFLINE by design: no network is granted to these processes (and cargo/go/npm/pip are told not to try), so dependencies
must already be present. Compiled programs are written to an exec-capable scratch directory, because the work disk is mounted
noexec. Whether running model-written code is acceptable is decided by the caller: the supervisor only enables this tool when the
builder is isolated (dedicated low-privilege user) or the owner explicitly accepted the risk.
"""
import os
import re
import resource
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

LANGUAGES = ("c", "cpp", "go", "python", "rust", "csharp", "java", "javascript", "swift")
ACTIONS = ("check", "build", "test", "run")
TIMEOUT = {"check": 120, "build": 300, "test": 600, "run": 120}
EXT = {"c": (".c",), "cpp": (".cpp", ".cc", ".cxx"), "go": (".go",), "python": (".py",), "rust": (".rs",), "csharp": (".cs",), "java": (".java",),
       "javascript": (".js", ".mjs", ".cjs"), "swift": (".swift",)}
MAX_OUT = 4000            # characters kept from the start and from the end of the output
MAX_FILE_OUT = 32 << 20   # the output file itself is capped by RLIMIT_FSIZE
MAX_SOURCES = 200
PROTECTED = (".git", ".ssh", ".aiws-trash")


# Toolchains that are often installed outside the default PATH (the Swift toolchain from swift.org, Go from go.dev, .NET, rustup).
TOOL_DIRS = ("/opt/swift/usr/bin", "/usr/local/go/bin", "/opt/dotnet", "/usr/local/dotnet", "/opt/node/bin")


def find_tool(name):
    """Resolve a program like `which`, also looking in the usual toolchain folders. Returns an absolute path or None."""
    found = shutil.which(name)
    if found:
        return found
    import glob
    for d in list(TOOL_DIRS) + sorted(glob.glob("/usr/libexec/swift/*/bin"), reverse=True):      # Debian's swiftlang keeps its binaries under /usr/libexec/swift/<version>/bin
        cand = os.path.join(d, name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def dep_cache():
    """Per-user cache for downloaded dependencies. build_run reads it OFFLINE; deps_install is the only thing that fills it."""
    base = Path(os.environ.get("AIWS_DEP_CACHE") or (Path.home() / ".cache" / "aiws-deps"))
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    return str(base)


# Modules that exist only on Apple platforms: the compiler error would otherwise look like a bug in the user's code.
APPLE_ONLY = re.compile(r"no such module '(SwiftUI|UIKit|AppKit|Cocoa|CoreData|CoreGraphics|CoreLocation|AVFoundation|Combine|MapKit|StoreKit|WebKit|CloudKit|SpriteKit|SceneKit|RealityKit|WidgetKit|XCTest.*Apple)'")


def hint_for(language, output):
    """A one-line explanation appended to compiler output when the failure is about the platform, not about the code."""
    if language == "swift":
        m = APPLE_ONLY.search(output or "")
        if m:
            return ("Note: the module '%s' only exists on Apple platforms (it ships with Xcode's SDKs). This Linux toolchain can build Swift code that uses "
                    "the standard library and Foundation, but not SwiftUI/UIKit/AppKit apps; those can only be built on a Mac." % m.group(1))
    return None


class BuildError(Exception):
    """Safe-to-show reason a request cannot be turned into a command."""


# ---------------------------------------------------------------- targets
def check_target(project, target):
    """Return (relative string, absolute Path). target may be None/'' meaning the project itself ('.')."""
    project = Path(project)
    if target in (None, "", "."):
        return ".", project
    if not isinstance(target, str) or len(target) > 200 or "\x00" in target or "\n" in target or "\\" in target:
        raise BuildError("The target must be a short relative path")
    if target.startswith("-") or target.startswith("/") or target.startswith("~"):
        raise BuildError("The target must be a relative path that does not start with '-'")
    parts = Path(target).parts
    if any(p in ("..",) or p in PROTECTED for p in parts):
        raise BuildError("The target is outside the project or in a protected folder")
    cur = project
    for p in parts:
        cur = cur / p
        if cur.is_symlink():
            raise BuildError("The target path contains a symbolic link")
    if not cur.exists():
        raise BuildError("The target does not exist")
    if not cur.resolve().is_relative_to(project.resolve()):
        raise BuildError("The target is outside the project")
    return "/".join(parts), cur


def _sources(language, path, rel):
    """Source files for a target: the file itself, or every matching file under a folder (bounded)."""
    if path.is_file():
        if path.suffix not in EXT[language]:
            raise BuildError("The target must be a %s source file (%s)" % (language, "/".join(EXT[language])))
        return [rel]
    out = []
    for p in sorted(path.rglob("*")):
        rel_in = p.relative_to(path)
        if p.is_file() and not p.is_symlink() and p.suffix in EXT[language] and not any(x in PROTECTED for x in rel_in.parts):
            out.append(("" if rel == "." else rel + "/") + str(rel_in))
        if len(out) > MAX_SOURCES:
            raise BuildError("Too many source files; give a single file or a project with a build file")
    if not out:
        raise BuildError("No %s source files found" % language)
    return out


def _step(argv):
    return {"argv": argv, "label": " ".join(a if re.fullmatch(r"[A-Za-z0-9_./:=+@%,-]+", a) else "'%s'" % a for a in argv)}


def _has(path, *names):
    return any((Path(path) / n).is_file() for n in names)


# ---------------------------------------------------------------- planning
def plan(language, action, project, target=None, out="/tmp/aiws-out", which=find_tool, has_module=None, cache=None):
    """Return {"steps":[{"argv","label"}...], "env":{...}} for one request, or raise BuildError.

    `out` is the exec-capable scratch directory; `which` and `has_module` are injected so the plan is testable without toolchains."""
    if language not in LANGUAGES:
        raise BuildError("Unknown language")
    if action not in ACTIONS:
        raise BuildError("Unknown action")
    rel, path = check_target(project, target)
    isdir = path.is_dir()
    cache = cache or dep_cache()
    has_module = has_module or (lambda name: __import__("importlib.util").util.find_spec(name) is not None)

    def need(tool):
        exe = which(tool)
        if not exe:
            raise BuildError("%s is not installed on this system" % tool)
        return exe

    stem = re.sub(r"[^A-Za-z0-9_]", "_", path.stem) or "app"
    env, steps = {}, []

    if language in ("c", "cpp"):
        cc, std = (need("cc"), "-std=c17") if language == "c" else (need("c++"), "-std=c++20")
        if not isdir:
            _sources(language, path, rel)
            exe = out + "/" + stem
            if action == "check":
                steps = [[cc, std, "-Wall", "-Wextra", "-fsyntax-only", rel]]
            elif action == "build":
                steps = [[cc, std, "-Wall", "-Wextra", "-o", exe, rel]]
            elif action == "run":
                steps = [[cc, std, "-Wall", "-Wextra", "-o", exe, rel], [exe]]
            else:
                raise BuildError("Tests need a CMake or Makefile project: give the project folder")
        elif _has(path, "CMakeLists.txt"):
            b = out + "/cmake"
            conf, build = [need("cmake"), "-S", rel, "-B", b], [need("cmake"), "--build", b]
            if action in ("check", "build"):
                steps = [conf, build]
            elif action == "test":
                steps = [conf, build, [need("ctest"), "--test-dir", b, "--output-on-failure"]]
            else:
                raise BuildError("To run a program give its source file as the target")
        elif _has(path, "Makefile", "makefile", "GNUmakefile"):
            mk = [need("make"), "-C", rel]
            if action in ("check", "build"):
                steps = [mk]
            elif action == "test":
                steps = [mk + ["test"]]
            else:
                raise BuildError("To run a program give its source file as the target")
        else:
            raise BuildError("Give a source file, or a folder containing CMakeLists.txt or a Makefile")

    elif language == "go":
        go = need("go")
        env = {"GOFLAGS": "-mod=readonly", "GOPROXY": "off", "GOTOOLCHAIN": "local", "GOCACHE": out + "/gocache", "GOPATH": out + "/gopath", "GOTMPDIR": out + "/gotmp", "GOMODCACHE": cache + "/go"}
        if path.is_file():
            _sources("go", path, rel)
            pkg = rel
        else:
            pkg = "./..." if rel == "." else "./" + rel + "/..."
        if action == "check":
            steps = [[go, "vet", pkg]]
        elif action == "build":
            steps = [[go, "build", "-o", out + "/bin/", pkg]]
        elif action == "test":
            steps = [[go, "test", pkg]]
        else:
            steps = [[go, "run", rel if path.is_file() else ("." if rel == "." else "./" + rel)]]

    elif language == "python":
        py = need("python3")
        env = {"PYTHONPYCACHEPREFIX": out + "/pyc"}
        if (Path(project) / ".aiws-deps").is_dir():                               # filled by deps_install; the project stays self-contained
            env["PYTHONPATH"] = str(Path(project) / ".aiws-deps")
        if action in ("check", "build"):
            steps = [[py, "-m", "py_compile", rel]] if path.is_file() else [[py, "-m", "compileall", "-q", rel]]
            if path.is_file():
                _sources("python", path, rel)
        elif action == "test":
            if has_module("pytest"):
                steps = [[py, "-m", "pytest", "-q", "-p", "no:cacheprovider", rel]]
            else:
                steps = [[py, "-m", "unittest", "discover", "-v", "-s", rel if isdir else str(Path(rel).parent) or "."]]
        else:
            if not path.is_file():
                raise BuildError("To run a program give the .py file as the target")
            _sources("python", path, rel)
            steps = [[py, rel]]

    elif language == "rust":
        env = {"CARGO_TARGET_DIR": out + "/cargo", "CARGO_NET_OFFLINE": "true", "CARGO_HOME": cache + "/cargo", "CARGO_INCREMENTAL": "0"}
        rustup = os.environ.get("RUSTUP_HOME") or str(Path.home() / ".rustup")        # rustup shims need to find the installed toolchains (just a path)
        if os.path.isdir(rustup):
            env["RUSTUP_HOME"] = rustup
        manifest = path / "Cargo.toml" if isdir else None
        if manifest is not None and manifest.is_file():
            cargo = need("cargo")
            mp = ["--manifest-path", (rel + "/Cargo.toml") if rel != "." else "Cargo.toml", "--offline"]
            steps = [[cargo, {"check": "check", "build": "build", "test": "test", "run": "run"}[action]] + mp]
        elif path.is_file():
            _sources("rust", path, rel)
            rc, exe = need("rustc"), out + "/" + stem
            if action == "check":
                steps = [[rc, "--edition", "2021", "--emit=metadata", "-o", exe + ".rmeta", rel]]
            elif action == "build":
                steps = [[rc, "--edition", "2021", "-o", exe, rel]]
            elif action == "test":
                steps = [[rc, "--edition", "2021", "--test", "-o", exe + "_test", rel], [exe + "_test"]]
            else:
                steps = [[rc, "--edition", "2021", "-o", exe, rel], [exe]]
        else:
            raise BuildError("Give a .rs file, or a folder containing Cargo.toml")

    elif language == "java":
        env = {"MAVEN_OPTS": "-Dmaven.repo.local=" + os.environ.get("AIWS_M2_REPO", cache + "/m2")}
        if isdir and _has(path, "pom.xml"):
            mvn = need("mvn")
            base = [mvn, "-o", "-q", "-B", "-f", (rel + "/pom.xml") if rel != "." else "pom.xml"]
            if action in ("check", "build"):
                steps = [base + ["compile"]]
            elif action == "test":
                steps = [base + ["test"]]
            else:
                raise BuildError("To run a program give its .java file as the target")
        else:
            javac = need("javac")
            src = _sources("java", path, rel)
            classes = out + "/classes"
            compile_step = [javac, "-Xlint:all", "-d", classes] + src
            if action in ("check", "build"):
                steps = [compile_step]
            elif action == "run":
                if not path.is_file():
                    raise BuildError("To run a program give the .java file that contains main() as the target")
                text = path.read_text(encoding="utf-8", errors="replace")[:20000]
                m = re.search(r"^\s*package\s+([A-Za-z0-9_.]+)\s*;", text, re.M)
                main = (m.group(1) + "." if m else "") + path.stem
                steps = [compile_step, [need("java"), "-cp", classes, main]]
            else:
                raise BuildError("Tests need a Maven project (pom.xml)")

    elif language == "javascript":
        node = need("node")
        env = {"npm_config_cache": cache + "/npm", "npm_config_offline": "true", "npm_config_update_notifier": "false", "npm_config_fund": "false", "npm_config_audit": "false"}
        pkg = path / "package.json" if isdir else None
        if action in ("check", "build"):
            if path.is_file():
                _sources("javascript", path, rel)
                steps = [[node, "--check", rel]]
            elif pkg is not None and pkg.is_file() and '"build"' in pkg.read_text(encoding="utf-8", errors="replace")[:20000] and action == "build":
                steps = [[need("npm"), "run", "build", "--offline", "--prefix", rel]]
            else:
                raise BuildError("Give a .js file (or, for build, a folder whose package.json has a build script)")
        elif action == "test":
            if pkg is not None and pkg.is_file() and '"test"' in pkg.read_text(encoding="utf-8", errors="replace")[:20000]:
                steps = [[need("npm"), "test", "--offline", "--prefix", rel]]
            else:
                steps = [[node, "--test", rel] if path.is_file() else [node, "--test"]]
        else:
            if not path.is_file():
                raise BuildError("To run a program give the .js file as the target")
            _sources("javascript", path, rel)
            steps = [[node, rel]]

    elif language == "swift":
        env = {"CLANG_MODULE_CACHE_PATH": out + "/modcache", "SWIFTPM_MODULECACHE_OVERRIDE": out + "/modcache"}
        if isdir and _has(path, "Package.swift"):
            swift = need("swift")
            pkg = ["--package-path", rel, "--build-path", out + "/swiftpm", "--disable-automatic-resolution"]       # never fetches packages
            verb = {"check": "build", "build": "build", "test": "test", "run": "run"}[action]
            steps = [[swift, verb] + pkg]
        else:
            swiftc = need("swiftc")
            _sources("swift", path, rel)
            if not path.is_file():
                raise BuildError("Give a .swift file, or a folder containing Package.swift")
            exe = out + "/" + stem
            if action == "check":
                steps = [[swiftc, "-typecheck", rel]]
            elif action == "build":
                steps = [[swiftc, "-o", exe, rel]]
            elif action == "run":
                steps = [[swiftc, "-o", exe, rel], [exe]]
            else:
                raise BuildError("Swift tests need a Swift package (Package.swift)")

    elif language == "csharp":
        dotnet, mcs = which("dotnet"), which("mcs")
        env = {"DOTNET_CLI_HOME": out + "/home/dotnet", "NUGET_PACKAGES": cache + "/nuget", "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
               "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1", "MSBUILDDISABLENODEREUSE": "1"}
        if isdir and dotnet and (any(path.glob("*.csproj")) or any(path.glob("*.sln"))):
            if action == "run":
                steps = [[dotnet, "run", "--project", rel]]
            else:                                                  # no build server / node reuse: nothing may outlive the command
                steps = [[dotnet, {"check": "build", "build": "build", "test": "test"}[action], rel, "-nologo", "-p:UseSharedCompilation=false", "-nodeReuse:false"]]
        elif mcs:
            src = _sources("csharp", path, rel)
            exe = out + "/" + stem + ".exe"
            if action in ("check", "build"):
                steps = [[mcs, "-out:" + exe] + src]
            elif action == "run":
                steps = [[mcs, "-out:" + exe] + src, [need("mono"), exe]]
            else:
                raise BuildError("Tests need a .NET project")
        elif dotnet:
            raise BuildError("Give a folder containing a .csproj or .sln")
        else:
            raise BuildError("No C# compiler (dotnet or mcs) is installed on this system")

    return {"steps": [_step(s) for s in steps], "env": env}


# ---------------------------------------------------------------- execution
PROXY_VARS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "NO_PROXY", "no_proxy")


def base_env(home, out, extra, path_dirs=(), online=False):
    """A minimal environment. Nothing from the agent's own environment is passed on (in particular no key).
    `path_dirs` are the folders of the toolchain programs we resolved, so e.g. cargo can find rustc beside itself."""
    system = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    env = {"PATH": ":".join(list(dict.fromkeys(d for d in path_dirs if d)) + [system]), "HOME": home, "TMPDIR": home.rsplit("/", 1)[0] + "/tmp", "LANG": "C.UTF-8",
           "LC_ALL": "C.UTF-8", "TERM": "dumb", "NO_COLOR": "1", "CI": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
           "PIP_DISABLE_PIP_VERSION_CHECK": "1", "GIT_TERMINAL_PROMPT": "0"}
    if online:                                 # only the builder's allowlisting proxy is passed on; nothing else about the environment
        env.update({k: os.environ[k] for k in PROXY_VARS if os.environ.get(k)})
    else:
        env["PIP_NO_INDEX"] = "1"
    env.update(extra)
    return env


def _limits(cpu_seconds):
    def apply():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_OUT * 4, MAX_FILE_OUT * 4))
        resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
        os.umask(0o077)
    return apply


def _head_tail(path):
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        head = fh.read(MAX_OUT)
        tail = b""
        if size > 2 * MAX_OUT:
            fh.seek(-MAX_OUT, os.SEEK_END)
            tail = fh.read()
        elif size > MAX_OUT:
            tail = fh.read()
    text = head.decode("utf-8", "replace")
    if tail:
        omitted = size - len(head) - len(tail)
        text += ("\n[... %d bytes omitted ...]\n" % omitted if omitted > 0 else "") + tail.decode("utf-8", "replace")
    return text


def execute(steps, cwd, env, timeout, clock=time.monotonic, scratch=None):
    """Run steps in order; stop at the first failure. Returns {"exitCode","timedOut","seconds","output","step"}."""
    deadline = clock() + timeout
    scratch = scratch or tempfile.gettempdir()
    started, last_code, output = clock(), 0, ""
    for i, st in enumerate(steps):
        remaining = deadline - clock()
        if remaining <= 0:
            return {"exitCode": None, "timedOut": True, "seconds": round(clock() - started, 1), "output": output, "step": st["label"]}
        fd, outfile = tempfile.mkstemp(prefix="out-", dir=scratch)
        try:
            with os.fdopen(fd, "wb") as sink:
                try:
                    proc = subprocess.Popen(st["argv"], cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=sink, stderr=subprocess.STDOUT, start_new_session=True,
                                            close_fds=True, shell=False, preexec_fn=_limits(int(remaining) + 5))
                except OSError as exc:
                    return {"exitCode": None, "timedOut": False, "seconds": round(clock() - started, 1), "output": "could not start: %s" % type(exc).__name__, "step": st["label"]}
                try:
                    last_code = proc.wait(timeout=remaining)
                    timed_out = False
                except subprocess.TimeoutExpired:
                    timed_out = True
                    last_code = None
                finally:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)       # whole group, including anything the program started
                    except (ProcessLookupError, PermissionError):
                        pass
                    proc.wait()
            output += ("" if not output else "\n") + ("$ " + st["label"] + "\n" if len(steps) > 1 else "") + _head_tail(outfile)
        finally:
            try:
                os.unlink(outfile)
            except OSError:
                pass
        if timed_out:
            return {"exitCode": None, "timedOut": True, "seconds": round(clock() - started, 1), "output": output, "step": st["label"]}
        if last_code != 0:
            return {"exitCode": last_code, "timedOut": False, "seconds": round(clock() - started, 1), "output": output, "step": st["label"]}
    return {"exitCode": 0, "timedOut": False, "seconds": round(clock() - started, 1), "output": output, "step": steps[-1]["label"] if steps else ""}


class Scratch:
    """An exec-capable private directory for one run (the work disk is noexec). Removed at the end."""
    def __init__(self, base=None):
        self.base = base or os.environ.get("AIWS_BUILD_SCRATCH") or "/var/tmp"
        self.path = None

    def get(self):
        if self.path is None:
            self.path = tempfile.mkdtemp(prefix="aiws-build-", dir=self.base)
            for sub in ("home", "tmp", "gotmp"):
                os.makedirs(self.path + "/" + sub, mode=0o700, exist_ok=True)
        return self.path

    def close(self):
        if self.path:
            shutil.rmtree(self.path, ignore_errors=True)
            self.path = None


def run_request(args, project, scratch, which=find_tool, has_module=None, clock=time.monotonic, timeout_scale=1.0, cache=None):
    """The whole tool: validate, plan, execute. Returns (command text for the approval prompt, callable that runs it)."""
    if not isinstance(args, dict) or set(args) - {"language", "action", "target"}:
        raise BuildError("Expected language, action and optionally target")
    out = scratch.get()
    planned = plan(args.get("language"), args.get("action"), project, args.get("target"), out, which, has_module, cache)
    command = " && ".join(s["label"] for s in planned["steps"])
    dirs = [os.path.dirname(st["argv"][0]) for st in planned["steps"] if os.path.isabs(st["argv"][0])]
    env = base_env(out + "/home", out, planned["env"], dirs)

    def go():
        res = execute(planned["steps"], str(project), env, TIMEOUT[args["action"]] * timeout_scale, clock, out + "/tmp")
        return res
    return command, go


def describe(res, language=None):
    """Text for the model: exit status first, then the bounded output (plus a platform hint when that is the real cause)."""
    if res["timedOut"]:
        head = "timed out after %.0fs (killed)" % res["seconds"]
    elif res["exitCode"] is None:
        head = "could not run"
    else:
        head = "exit code %d in %.1fs" % (res["exitCode"], res["seconds"])
    text = head + ("\n" + res["output"] if res["output"] else "\n(no output)")
    hint = hint_for(language, res["output"]) if language and res.get("exitCode") not in (0, None) else None
    return text + ("\n" + hint if hint else "")


# ---------------------------------------------------------------- dependencies (the ONLY online step)
def plan_deps(language, project, target, out, cache, which=find_tool, environ=None):
    """Fixed commands that fill the dependency cache. They are the only commands here that get network, and only through the
    builder's allowlisting proxy: without one configured this refuses. Install scripts are NOT run (npm --ignore-scripts, pip wheels only)."""
    environ = os.environ if environ is None else environ
    if not (environ.get("HTTPS_PROXY") or environ.get("https_proxy")):
        raise BuildError("No network route is configured for downloads (the builder needs its isolation with the allowlisting proxy)")
    if language not in LANGUAGES:
        raise BuildError("Unknown language")
    rel, path = check_target(project, target)
    if not path.is_dir():
        raise BuildError("The target must be the project folder that holds the dependency file")

    def need(tool):
        exe = which(tool)
        if not exe:
            raise BuildError("%s is not installed on this system" % tool)
        return exe

    def manifest(*names):
        for n in names:
            if (path / n).is_file():
                return n
        raise BuildError("No %s found in %s" % (" or ".join(names), rel))
    here = lambda n: n if rel == "." else rel + "/" + n
    if language == "go":
        manifest("go.mod")
        steps = [[need("go")] + ([] if rel == "." else ["-C", rel]) + ["mod", "download"]]
        env = {"GOPROXY": "https://proxy.golang.org", "GOSUMDB": "sum.golang.org", "GOFLAGS": "-mod=readonly", "GOTOOLCHAIN": "local",
               "GOMODCACHE": cache + "/go", "GOCACHE": out + "/gocache", "GOPATH": out + "/gopath", "GOTMPDIR": out + "/gotmp"}
    elif language == "rust":
        manifest("Cargo.toml")
        steps = [[need("cargo"), "fetch", "--manifest-path", here("Cargo.toml")]]
        env = {"CARGO_HOME": cache + "/cargo", "CARGO_INCREMENTAL": "0"}
        rustup = os.environ.get("RUSTUP_HOME") or str(Path.home() / ".rustup")
        if os.path.isdir(rustup):
            env["RUSTUP_HOME"] = rustup
    elif language == "javascript":
        manifest("package.json")
        verb = "ci" if (path / "package-lock.json").is_file() else "install"
        steps = [[need("npm"), verb, "--ignore-scripts", "--no-audit", "--no-fund", "--prefix", rel]]
        env = {"npm_config_cache": cache + "/npm"}
    elif language == "python":
        manifest("requirements.txt")
        steps = [[need("python3"), "-m", "pip", "install", "--no-input", "--disable-pip-version-check", "--only-binary=:all:", "--target", ".aiws-deps", "-r", here("requirements.txt")]]
        env = {}
    elif language == "java":
        manifest("pom.xml")
        steps = [[need("mvn"), "-B", "-q", "-f", here("pom.xml"), "dependency:go-offline"]]
        env = {"MAVEN_OPTS": "-Dmaven.repo.local=" + os.environ.get("AIWS_M2_REPO", cache + "/m2")}
    elif language == "csharp":
        if not (any(path.glob("*.csproj")) or any(path.glob("*.sln"))):
            raise BuildError("No .csproj or .sln found in %s" % rel)
        steps = [[need("dotnet"), "restore", rel, "-nologo"]]
        env = {"NUGET_PACKAGES": cache + "/nuget", "DOTNET_CLI_HOME": out + "/home/dotnet", "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1"}
    elif language == "swift":
        raise BuildError("Swift packages are fetched from git hosts, which are not allowed through the proxy yet: put the sources in the project")
    else:
        raise BuildError("C and C++ have no package manager here: put the sources in the project")
    return {"steps": [_step(x) for x in steps], "env": env}


def deps_request(args, project, scratch, which=find_tool, cache=None, environ=None, extra_env=None):
    """Like run_request, for the download step. Returns (command text, runner)."""
    if not isinstance(args, dict) or set(args) - {"language", "target"}:
        raise BuildError("Expected language and optionally target")
    out = scratch.get()
    planned = plan_deps(args.get("language"), project, args.get("target"), out, cache or dep_cache(), which, environ)
    command = " && ".join(s["label"] for s in planned["steps"])
    dirs = [os.path.dirname(st["argv"][0]) for st in planned["steps"] if os.path.isabs(st["argv"][0])]
    env = base_env(out + "/home", out, planned["env"], dirs, online=True)
    env.update(extra_env or {})                              # test hook only: never reachable from the model's arguments

    def go():
        return execute(planned["steps"], str(project), env, 900, time.monotonic, out + "/tmp")
    return command, go
