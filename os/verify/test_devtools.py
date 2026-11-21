"""Developer toolchain: package lists are well-formed and runtime.detect knows the tools."""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "debian" / "tools"))
import aiws_toolplane as plane
import check_packages as cp

LISTS = ROOT / "debian/config/package-lists"

class PackageListTests(unittest.TestCase):
    def names(self, f):
        return cp.read_list(LISTS / f)

    def test_names_are_valid_and_not_duplicated_within_or_across_lists(self):
        seen = {}
        for f in ("aiws-desktop.list.chroot", "aiws-devtools.list.chroot"):
            for n in self.names(f):
                self.assertRegex(n, r"^[a-z0-9][a-z0-9+.\-]+$", n)
                self.assertNotIn(n, seen, "%s duplicated (also in %s)" % (n, seen.get(n)))
                seen[n] = f
        self.assertGreater(len(self.names("aiws-devtools.list.chroot")), 40)

    def test_known_non_debian_packages_are_not_listed(self):
        everything = set(self.names("aiws-desktop.list.chroot") + self.names("aiws-devtools.list.chroot"))
        for absent in ("dotnet-sdk-8.0", "pnpm", "ruff", "python3-black", "code", "codium", "visual-studio-code", "docker.io"):
            self.assertNotIn(absent, everything)

    def test_devtools_are_full_profile_only(self):
        build = (ROOT / "debian/build.sh").read_text()
        self.assertIn('rm -f -- "$out/config/package-lists/aiws-devtools.list.chroot"', build)
        smoke = set(cp.read_list(ROOT / "debian/profiles/smoke.list.chroot"))
        self.assertFalse(smoke & set(self.names("aiws-devtools.list.chroot")))

    def test_every_listed_language_has_a_runtime_detect_entry(self):
        listed = set(self.names("aiws-desktop.list.chroot") + self.names("aiws-devtools.list.chroot"))
        for pkg, exe in (("ruby", "ruby"), ("php-cli", "php"), ("lua5.4", "lua5.4"), ("node-typescript", "tsc"), ("golang-go", "go"),
                         ("rustc", "rustc"), ("gdb", "gdb"), ("valgrind", "valgrind"), ("clangd", "clangd"), ("gh", "gh"),
                         ("ripgrep", "rg"), ("neovim", "nvim"), ("postgresql-client", "psql")):
            self.assertIn(pkg, listed, pkg)
            self.assertIn(exe, plane.DETECT_TOOLS, exe)

class DetectTests(unittest.TestCase):
    def test_detect_reports_every_tool_key(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "ws"; ws.mkdir()
            old = os.environ.get("AIWS_WORKSPACE"); os.environ["AIWS_WORKSPACE"] = str(ws)
            try:
                out = plane.invoke("runtime.detect", {})["tools"]
            finally:
                os.environ.pop("AIWS_WORKSPACE") if old is None else os.environ.__setitem__("AIWS_WORKSPACE", old)
        self.assertEqual(set(out), set(plane.DETECT_TOOLS))
        self.assertTrue(all(v is None or v.startswith("/") for v in out.values()))

    def test_tool_list_has_no_duplicates(self):
        self.assertEqual(len(plane.DETECT_TOOLS), len(set(plane.DETECT_TOOLS)))

if __name__ == "__main__":
    unittest.main()
