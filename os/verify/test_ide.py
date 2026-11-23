"""AIWS Code (rebranded Code - OSS build): overrides, patch, build/launcher scripts, branding and legal files.

Set AIWS_VSCODE_SRC to a checkout of microsoft/vscode at the pinned tag to also verify the overrides and the patch
against the REAL upstream files (the author ran this with 1.147.0). Without it those two tests are skipped.
"""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
IDE = ROOT / "ide"
sys.path.insert(0, str(IDE / "tools"))
import apply_product_overrides as apo
import scan_endpoints as se

LAUNCHER = ROOT / "debian/config/includes.chroot/usr/local/bin/aiws-code"
OVERRIDES = json.loads((IDE / "product.overrides.json").read_text())
PIN = dict(l.strip().split("=", 1) for l in (IDE / "PIN.env").read_text().splitlines() if "=" in l and not l.startswith("#"))
SRC = os.environ.get("AIWS_VSCODE_SRC")

SYNTHETIC_UPSTREAM = {   # same key names as the real upstream file, with representative values
    "nameShort": "Code - OSS", "nameLong": "Code - OSS", "applicationName": "code-oss", "dataFolderName": ".vscode-oss",
    "serverApplicationName": "code-server-oss", "urlProtocol": "code-oss", "licenseUrl": "https://github.com/microsoft/vscode/blob/main/LICENSE.txt",
    "defaultChatAgent": {"extensionId": "GitHub.copilot", "entitlementUrl": "https://api.github.com/copilot_internal/user"},
    "voiceWsUrl": "wss://falcon-caas.mai.microsoft.com/voice-code/api/v1/realtime/voice",
    "trustedExtensionAuthAccess": {"github": ["GitHub.copilot-chat"]},
    "webviewContentExternalBaseUrlTemplate": "https://{{uuid}}.vscode-cdn.net/insider/x/out/",
    "win32AppUserModelId": "Microsoft.CodeOSS", "darwinBundleIdentifier": "com.visualstudio.code.oss",
    "onboardingKeymaps": [{"id": "vscode", "label": "VS Code"}],
    "builtInExtensions": [{"name": "ms-vscode.js-debug", "repo": "https://github.com/microsoft/vscode-js-debug", "metadata": {"publisherName": "ms-vscode", "displayName": "Microsoft"}}],
}

class OverrideTests(unittest.TestCase):
    def test_merge_semantics(self):
        merged = apo.merge({"a": 1, "b": 2, "c": {"x": 1}}, {"a": None, "b": 3, "c": {"y": 2}, "d": 4})
        self.assertEqual(merged, {"b": 3, "c": {"y": 2}, "d": 4})              # null deletes; nested values are replaced whole

    def test_synthetic_upstream_becomes_clean(self):
        before = se.scan_product(SYNTHETIC_UPSTREAM)
        self.assertTrue({"service", "brand"} <= {f["class"] for f in before})
        merged = apo.merge(SYNTHETIC_UPSTREAM, OVERRIDES)
        self.assertEqual([f for f in se.scan_product(merged) if f["class"] in ("service", "brand")], [])
        for gone in ("defaultChatAgent", "voiceWsUrl", "trustedExtensionAuthAccess", "win32AppUserModelId", "darwinBundleIdentifier"):
            self.assertNotIn(gone, merged)
        self.assertEqual(merged["builtInExtensions"][0]["repo"], "https://github.com/microsoft/vscode-js-debug")   # credit is kept

    def test_identity_is_ours_and_consistent(self):
        o = OVERRIDES
        self.assertEqual((o["nameLong"], o["applicationName"], o["serverApplicationName"]), ("AIWS Code", "aiws-code", "aiws-code-server"))
        for key in ("dataFolderName", "sharedDataFolderName", "serverDataFolderName", "urlProtocol", "linuxIconName"):
            self.assertIn("aiws", o[key])
        self.assertTrue(o["extensionsGallery"]["serviceUrl"].startswith("https://open-vsx.org/"))
        self.assertNotIn("marketplace.visualstudio.com", json.dumps(o))
        self.assertIn(":18090/", o["webviewContentExternalBaseUrlTemplate"])
        self.assertTrue(o["webviewContentExternalBaseUrlTemplate"].startswith("http://{{uuid}}.localhost:"))

    def test_apply_cli_refuses_to_write_a_dirty_result(self):
        with tempfile.TemporaryDirectory() as t:
            up, ov, out = Path(t) / "up.json", Path(t) / "ov.json", Path(t) / "out.json"
            up.write_text(json.dumps(SYNTHETIC_UPSTREAM))
            ov.write_text(json.dumps({"nameShort": "X", "nameLong": "Visual Studio Code", "applicationName": "x", "dataFolderName": ".x",
                                      "serverApplicationName": "x-server", "urlProtocol": "x"}))
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(apo.main(["x", str(up), str(ov), str(out)]), 1)
            self.assertFalse(out.exists())
            self.assertEqual(apo.main(["x", str(up), str(IDE / "product.overrides.json"), str(out)]), 0)
            self.assertEqual(json.loads(out.read_text())["nameLong"], "AIWS Code")

    @unittest.skipUnless(SRC and (Path(SRC) / "product.json").is_file(), "set AIWS_VSCODE_SRC to a microsoft/vscode checkout")
    def test_real_upstream_product_json_is_clean_after_overrides(self):
        real = json.loads((Path(SRC) / "product.json").read_text())
        self.assertGreater(sum(1 for f in se.scan_product(real) if f["class"] in ("service", "brand")), 20)   # the scanner does see them
        merged = apo.merge(real, OVERRIDES)
        left = [f for f in se.scan_product(merged) if f["class"] in ("service", "brand")]
        self.assertEqual(left, [], left)

    @unittest.skipUnless(SRC and (Path(SRC) / ".git").exists(), "set AIWS_VSCODE_SRC to a microsoft/vscode checkout")
    def test_patch_applies_to_the_real_pinned_source(self):
        head = subprocess.run(["git", "-C", SRC, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(head, PIN["AIWS_CODE_VSCODE_COMMIT"])
        for patch in sorted((IDE / "patches").glob("*.patch")):
            r = subprocess.run(["git", "-C", SRC, "apply", "--check", str(patch)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, patch.name + ": " + r.stderr)

class PatchTests(unittest.TestCase):
    def test_patch_is_small_and_removes_the_microsoft_cdn(self):
        text = (IDE / "patches/0001-local-webview-endpoint.patch").read_text()
        files = re.findall(r"^diff --git a/(\S+)", text, flags=re.M)
        self.assertEqual(files, ["src/vs/server/node/webClientServer.ts", "src/vs/workbench/services/environment/browser/environmentService.ts"])
        added = [l for l in text.splitlines() if l.startswith("+") and not l.startswith("+++")]
        removed = [l for l in text.splitlines() if l.startswith("-") and not l.startswith("---")]
        self.assertTrue(any("vscode-cdn.net" in l for l in removed))
        self.assertFalse(any("vscode-cdn.net" in l for l in added))
        self.assertTrue(all("localhost" in l for l in added))

class ScannerTests(unittest.TestCase):
    def test_tree_scan_reports_services_and_skips_license_files(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "a.js").write_text('fetch("https://mobile.events.data.microsoft.com/x"); const u="https://abc.vscode-cdn.net/p"')
            (root / "LICENSE.txt").write_text("https://marketplace.visualstudio.com")
            (root / "node_modules").mkdir(); (root / "node_modules/b.js").write_text("https://vscode-unpkg.net")
            report = se.scan_tree(root)
            self.assertEqual(set(report), {"service:events.data.microsoft.com", "service:vscode-cdn.net"})

    def test_doc_links_are_not_blocking(self):
        findings = se.scan_product({"helpUrl": "https://code.visualstudio.com/docs", "x": "https://aka.ms/y"})
        self.assertEqual({f["class"] for f in findings}, {"doc-link"})

class BuildScriptTests(unittest.TestCase):
    def setUp(self):
        self.src = (IDE / "build-aiws-code.sh").read_text()

    def test_syntax_and_safety(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(IDE / "build-aiws-code.sh")]).returncode, 0)
        for needle in ('id -u', 'rev-parse HEAD', 'AIWS_CODE_VSCODE_COMMIT', 'already exists', 'nothing was deleted', 'git -C src apply --check',
                       'apply_product_overrides.py', 'scan_endpoints.py', 'LICENSE.txt', 'ThirdPartyNotices.txt', 'AIWS-NOTICE.md',
                       'frozen-lockfile', 'vscode-reh-web-linux-x64-min', 'sha256sum', 'NOT yet executed'):
            self.assertIn(needle, self.src, needle)
        # The "-ci" gulp task only PACKAGES (it needs an earlier compile step) and fails with a missing nls.keys.json;
        # the account/AI extensions are dropped from the OUTPUT because the gulp graph needs their sources.
        self.assertNotIn('min-ci', self.src.split('# 4b)')[0].split('gulp ')[-1])
        self.assertIn('"$out/extensions/copilot"', self.src)
        self.assertNotRegex(self.src.split('# 4)')[1].split('( cd src')[0], r'rm -rf[^\n]*src/extensions')
        for bad in ("curl", "| sh", "| bash", "rm -rf /", "eval "):
            self.assertNotIn(bad, self.src)
        self.assertIn("never ship upstream logos", self.src.lower().replace("we never ship upstream logos", "never ship upstream logos"))

    def test_pin_matches_files_in_the_repo(self):
        self.assertRegex(PIN["AIWS_CODE_VSCODE_COMMIT"], r"^[a-f0-9]{40}$")
        self.assertRegex(PIN["AIWS_CODE_VSCODE_TAG"], r"^1\.\d+\.\d+$")
        self.assertIn(PIN["AIWS_CODE_NODE_VERSION"], (IDE / "README.md").read_text())

    def test_build_sh_refuses_an_image_without_license_files(self):
        build = (ROOT / "debian/build.sh").read_text()
        for needle in ("AIWS_CODE_SHA256", "checksum mismatch", "LICENSE.txt ThirdPartyNotices.txt AIWS-NOTICE.md", "refusing to ship without the license files"):
            self.assertIn(needle, build)

class BrandingTests(unittest.TestCase):
    def test_artwork_is_original_and_complete(self):
        svg = (IDE / "branding/aiws-code.svg").read_text()
        ET.fromstring(svg)                                                  # well-formed XML
        for forbidden in ("microsoft", "visual studio", "vscode", "vs code"):
            self.assertNotIn(forbidden, svg.lower().replace("not derived from any microsoft or third-party logo", ""))
        self.assertIn("Original AIWS artwork", svg)
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed; the SVG checks above still ran")
        self.assertEqual(Image.open(IDE / "branding/icon-512.png").size, (512, 512))
        self.assertEqual(Image.open(IDE / "branding/icon-192.png").size, (192, 192))
        self.assertEqual(Image.open(IDE / "branding/icon-256.png").size, (256, 256))
        self.assertEqual((IDE / "branding/favicon.ico").read_bytes()[:4], b"\x00\x00\x01\x00")

class LegalTests(unittest.TestCase):
    def test_notice_keeps_the_credit_and_states_what_is_not_reused(self):
        text = (IDE / "NOTICE.md").read_text()
        for needle in ("MIT License", "Copyright (c) 2015 - present", "Microsoft Corporation", "never removed or edited", "LICENSE.txt",
                       "ThirdPartyNotices.txt", "not a Microsoft product", "trademarks", "Rebrand is not relicensing"):
            self.assertIn(needle, text)

    def test_readme_states_the_status_honestly(self):
        text = (IDE / "README.md").read_text()
        for needle in ("NOT built", "unverified", "MIT"):
            self.assertIn(needle, text)

class LauncherTests(unittest.TestCase):
    def test_static_properties(self):
        src = LAUNCHER.read_text()
        self.assertEqual(subprocess.run(["sh", "-n", str(LAUNCHER)]).returncode, 0)
        for needle in ('--host 127.0.0.1', '--connection-token-file', '--telemetry-level off', '--enable-remote-auto-shutdown',
                       'id -u', 'chmod 600', 'umask 0077', 'chat.disableAIFeatures', 'update.mode'):
            self.assertIn(needle, src, needle)
        for bad in ("eval ", "0.0.0.0", "--without-connection-token", "sudo", "curl "):
            self.assertNotIn(bad, src)
        self.assertIn(":" + str(OVERRIDES["webviewContentExternalBaseUrlTemplate"].split(":")[2].split("/")[0]), "port:18090".replace("port", ""))
        self.assertIn("18090", src)
        self.assertIn("bin/" + OVERRIDES["serverApplicationName"], src)

    def test_desktop_entry_and_installation_wiring(self):
        d = (ROOT / "debian/config/includes.chroot/usr/share/applications/aiws-code.desktop").read_text()
        for needle in ("Name=AIWS Code", "Exec=/usr/local/bin/aiws-code", "Icon=aiws-code", "Categories=Development;IDE;TextEditor;"):
            self.assertIn(needle, d)
        self.assertEqual(OVERRIDES["linuxIconName"], "aiws-code")
        if shutil.which("desktop-file-validate"):
            self.assertEqual(subprocess.run(["desktop-file-validate", str(ROOT / "debian/config/includes.chroot/usr/share/applications/aiws-code.desktop")]).returncode, 0)

@unittest.skipUnless(os.geteuid() == 0 and shutil.which("setpriv") or os.geteuid() != 0, "needs a non-root user")
class LauncherBehaviourTests(unittest.TestCase):
    """Runs the real launcher as an unprivileged user against a FAKE server that records its command line."""
    FAKE_SERVER = """#!/usr/bin/env python3
import json, os, socket, sys, time
args = sys.argv[1:]
port = int(args[args.index("--port") + 1])
open(os.environ["FAKE_LOG"], "a").write(json.dumps({"argv": args, "pid": os.getpid()}) + "\\n")
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("127.0.0.1", port)); s.listen(8)
while True:
    try: c, _ = s.accept(); c.close()
    except OSError: break
"""
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        base = Path(self.t.name); base.chmod(0o777)
        self.home = base / "home"; self.home.mkdir(); self.home.chmod(0o777)
        self.root = base / "aiws-code"; (self.root / "bin").mkdir(parents=True); (self.root / "out").mkdir()
        (self.root / "out/server-main.js").write_text("// fake")
        server = self.root / "bin/aiws-code-server"; server.write_text(self.FAKE_SERVER); server.chmod(0o755)
        for p in (self.root, self.root / "bin", self.root / "out"):
            p.chmod(0o755)
        (self.root / "out/server-main.js").chmod(0o644)
        self.project = base / "project"; self.project.mkdir(); self.project.chmod(0o777)
        self.log = base / "fake.log"; self.log.write_text(""); self.log.chmod(0o666)
        s = socket.socket(); s.bind(("127.0.0.1", 0)); self.port = s.getsockname()[1]; s.close()
        self.env = {"HOME": str(self.home), "PATH": os.environ["PATH"], "AIWS_CODE_ROOT": str(self.root), "AIWS_CODE_PORT": str(self.port),
                    "FAKE_LOG": str(self.log), "XDG_RUNTIME_DIR": str(self.home / "run")}
        (self.home / "run").mkdir(); (self.home / "run").chmod(0o700)
        if os.geteuid() == 0:                                  # the launcher runs as an unprivileged user: it must own its dirs
            for d in (base, self.home, self.home / "run", self.project, self.log):
                os.chown(d, 65534, 65534)

    def tearDown(self):
        for line in self.log.read_text().splitlines():
            try:
                os.kill(json.loads(line)["pid"], signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        self.t.cleanup()

    def run_launcher(self, *args, user=True):
        kw = {"user": 65534, "group": 65534} if (user and os.geteuid() == 0) else {}
        return subprocess.run(["sh", str(LAUNCHER), *args], capture_output=True, text=True, timeout=60, env=self.env, **kw)

    def test_starts_a_loopback_token_protected_server_once_with_safe_flags(self):
        r = self.run_launcher("--server-only", str(self.project))
        self.assertEqual(r.returncode, 0, r.stderr)
        r2 = self.run_launcher("--server-only", str(self.project))                       # already running: no second server
        self.assertEqual(r2.returncode, 0, r2.stderr)
        runs = [json.loads(l) for l in self.log.read_text().splitlines()]
        self.assertEqual(len(runs), 1)
        argv = runs[0]["argv"]
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")
        self.assertEqual(argv[argv.index("--port") + 1], str(self.port))
        self.assertIn("--enable-remote-auto-shutdown", argv)
        self.assertEqual(argv[argv.index("--telemetry-level") + 1], "off")
        self.assertEqual(argv[argv.index("--default-folder") + 1], str(self.project))
        self.assertNotIn("--without-connection-token", argv)
        token = Path(argv[argv.index("--connection-token-file") + 1])
        self.assertEqual(token.stat().st_mode & 0o777, 0o600)
        self.assertGreaterEqual(len(token.read_text().strip()), 32)
        self.assertEqual(self.home.joinpath(".local/share/aiws-code").stat().st_mode & 0o077, 0)

    def test_settings_are_seeded_once_and_user_edits_survive(self):
        self.run_launcher("--server-only", str(self.project))
        settings = self.home / ".local/share/aiws-code/server-data/data/User/settings.json"
        data = json.loads(settings.read_text())
        self.assertEqual(data["telemetry.telemetryLevel"], "off")
        self.assertIs(data["chat.disableAIFeatures"], True)
        settings.write_text('{"editor.tabSize": 2}')
        self.run_launcher("--server-only", str(self.project))
        self.assertEqual(json.loads(settings.read_text()), {"editor.tabSize": 2})

    def test_refuses_bad_inputs(self):
        self.assertEqual(self.run_launcher("--server-only", "relative/path").returncode, 2)
        self.assertEqual(self.run_launcher("--server-only", str(self.project / "missing")).returncode, 2)
        link = Path(self.t.name) / "link"; os.symlink(self.project, link)
        self.assertEqual(self.run_launcher("--server-only", str(link)).returncode, 2)
        self.env["AIWS_CODE_ROOT"] = str(Path(self.t.name) / "not-installed")
        r = self.run_launcher("--server-only", str(self.project))
        self.assertEqual(r.returncode, 3)
        self.assertIn("not installed", r.stderr)
        self.assertEqual(self.log.read_text(), "")

    @unittest.skipUnless(os.geteuid() == 0, "root check is only observable when running as root")
    def test_refuses_to_run_as_root(self):
        r = self.run_launcher("--server-only", str(self.project), user=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("must not run as root", r.stderr)

if __name__ == "__main__":
    unittest.main()
