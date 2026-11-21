"""Preflight is read-only; these tests do NOT qualify disk installation."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "os/installer/aiws_install_preflight.py"
spec = importlib.util.spec_from_file_location("aiws_install_preflight", MODULE)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class InstallerPreflightContract(unittest.TestCase):
    def test_blank_virtual_disk_is_reported_not_modified(self):
        data = {"blockdevices": [{"path": "/dev/vda", "type": "disk",
                                  "size": 40 * 1024**3, "rm": False,
                                  "mountpoint": None, "children": None,
                                  "model": "QEMU"}]}
        self.assertEqual(installer.inspect_devices(data)[0]["device"], "/dev/vda")

    def test_mounted_or_partitioned_or_removable_or_small_rejected(self):
        base = {"path": "/dev/vda", "type": "disk", "size": 40 * 1024**3,
                "rm": False, "mountpoint": None}
        for override in ({"children": [{"type": "part"}]},
                         {"mountpoint": "/"}, {"rm": True},
                         {"size": 1024}, {"path": "/dev/mapper/system"},
                         {"type": "part"}, {"size": True}):
            with self.subTest(override=override):
                self.assertEqual(installer.inspect_devices(
                    {"blockdevices": [{**base, **override}]}), [])

    def test_invalid_report_is_rejected(self):
        for value in ({}, {"blockdevices": "no"}, []):
            with self.assertRaises(ValueError):
                installer.inspect_devices(value)

    def test_install_flag_always_refused(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(installer.main(["--install"]), 3)

    def test_no_write_commands_or_disk_mutation_imports(self):
        text = MODULE.read_text()
        for forbidden in ("subprocess.run([\"mkfs", "subprocess.run([\"sgdisk",
                          "subprocess.run([\"wipefs", "subprocess.run([\"parted",
                          "os.system(", "shutil.rmtree("):
            self.assertNotIn(forbidden, text)

if __name__ == "__main__":
    unittest.main()
