import unittest
from pathlib import Path

from buildsrc import OS, runtime_modules

class RuntimeManifestTests(unittest.TestCase):
    def test_manifest_lists_every_runtime_module_exactly_once(self):
        listed = runtime_modules()
        self.assertEqual(len(listed), len(set(listed)), "duplicate entry in os/runtime/MODULES")
        on_disk = sorted(p.name for p in (OS / "runtime").glob("aiws_*.py"))
        self.assertEqual(sorted(listed), on_disk)

    def test_build_script_reads_the_manifest_and_rejects_odd_entries(self):
        build = (OS / "debian/build.sh").read_text(encoding="utf-8")
        self.assertIn('os/runtime/MODULES', build)
        self.assertIn("aiws_*.py", build)                       # only module-looking names are copied
        self.assertNotIn('os/runtime/aiws_toolplane.py"', build)  # the old hand-written cp list must stay gone

class ReleaseControlFileTests(unittest.TestCase):
    def test_preview_env_can_be_sourced_by_a_shell_like_the_workflow_does(self):
        import subprocess
        out = subprocess.run(["bash", "-c", "set -a; . release/PREVIEW.env; set +a; printf '%s|%s|%s' \"$AIWS_RELEASE_STAGE\" \"$AIWS_RELEASE_TAG\" \"$AIWS_RELEASE_TITLE\""],
                             cwd=OS.parent, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        stage, tag, title = out.stdout.split("|")
        self.assertIn(stage, ("code", "iso-dry", "full"))
        self.assertRegex(tag, r"^v\d+\.\d+\.\d+-preview\.\d+$")
        self.assertIn("test build", title)

if __name__ == "__main__":
    unittest.main()
