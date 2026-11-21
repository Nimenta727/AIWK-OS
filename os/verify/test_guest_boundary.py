"""Guest-only security policy regression. CI mocks VM detector; no host access."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from aiws_guest_boundary import MARKER_CONTENT, protect_guest_workspace, require_guest_runtime

class BoundaryTests(unittest.TestCase):
    def test_marker_and_vm_detection_both_required(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "guest-managed"
            marker.write_text(MARKER_CONTENT)
            with patch("aiws_guest_boundary.os.geteuid", return_value=1000):
                self.assertTrue(require_guest_runtime(marker, ["true"]))
                with self.assertRaises(PermissionError):
                    require_guest_runtime(marker, ["false"])
                marker.write_text("NOT_A_GUEST")
                with self.assertRaises(PermissionError):
                    require_guest_runtime(marker, ["true"])
                marker.unlink()
                with self.assertRaises(PermissionError):
                    require_guest_runtime(marker, ["true"])

    def test_reject_root_process(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "guest-managed"
            marker.write_text(MARKER_CONTENT)
            with patch("aiws_guest_boundary.os.geteuid", return_value=0):
                with self.assertRaises(PermissionError):
                    require_guest_runtime(marker, ["true"])

    def test_reject_host_shared_mounts_and_nested_mounts(self):
        mounts = "1 0 0:1 / / rw - ext4 /dev/vda1 rw\n2 1 0:2 / /mnt/shared rw - virtiofs host-share rw\n3 1 0:3 / /home/aiws/projects/host rw - 9p host0 rw\n"
        with self.assertRaises(PermissionError):
            protect_guest_workspace(Path("/home/aiws/projects"), Path("/home/aiws/projects/a.cs"), mounts)
        self.assertTrue(protect_guest_workspace(Path("/home/aiws/projects"),
            Path("/home/aiws/projects/a.cs"), "1 0 0:1 / / rw - ext4 /dev/vda1 rw\n"))
        with self.assertRaises(PermissionError):
            protect_guest_workspace(Path("/mnt/shared/proj"), mountinfo=mounts)
        with self.assertRaises(PermissionError):
            protect_guest_workspace(Path("/home/aiws/projects"),Path("/home/aiws/projects/host/a.cs"),mounts)

    def test_guest_workspace_scoping(self):
        mounts = "1 0 0:1 / / rw - overlay overlay rw\n"
        with self.assertRaises(PermissionError):
            protect_guest_workspace(Path("/home/aiws/projects"),Path("/etc/passwd"),mounts)
        with self.assertRaises(PermissionError):
            protect_guest_workspace(Path("/run/host/data"),mountinfo=mounts)

    def test_guest_image_includes_marker_and_no_host_pass_through(self):
        root=Path(__file__).resolve().parents[2]
        marker=root/"os/debian/config/includes.chroot/etc/aiws/guest-managed"
        self.assertEqual(marker.read_text().strip(),MARKER_CONTENT)
        host=(root/"os/host/run-qemu-offline.sh").read_text()
        for forbidden in ("-virtfs","-fsdev","-device vfio-","-device usb-host","hostfwd=","-nic user"):
            self.assertNotIn(forbidden,host)

if __name__ == "__main__":
    unittest.main()
