"""Work disk: never format anything but one blank disk; snapshot names validated; rollback keeps the old state. System verify: tamper detection."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import aiws_workdisk as W
import aiws_sysverify as V

G = 1 << 30
def disk(name, size=20 * G, **kw): return {"name": name, "path": "/dev/" + name, "type": "disk", "size": size, "rm": False, "ro": False, **kw}
def lsblk(*d): return {"blockdevices": list(d)}

class Plan(unittest.TestCase):
    def test_boot_media_only_means_no_work_disk(self):
        live = disk("sr0", type="rom", fstype="iso9660", label="DEBIAN_LIVE", mountpoints=["/run/live/medium"])
        self.assertEqual(W.plan(lsblk(live))[0], "none")
    def test_one_blank_disk_is_formatted(self):
        self.assertEqual(W.plan(lsblk(disk("sr0", type="rom", fstype="iso9660"), disk("vdb")))[:2], ("format", "/dev/vdb"))
    def test_existing_labelled_btrfs_is_mounted_not_formatted(self):
        self.assertEqual(W.plan(lsblk(disk("vdb", fstype="btrfs", label=W.LABEL)))[:2], ("mount", "/dev/vdb"))
    def test_labelled_with_other_filesystem_is_refused(self):
        self.assertEqual(W.plan(lsblk(disk("vdb", fstype="ext4", label=W.LABEL)))[0], "refuse")
    def test_disks_with_data_partitions_labels_mounts_or_small_are_never_candidates(self):
        for d in (disk("vdb", fstype="ext4"), disk("vdb", label="DATA"), disk("vdb", children=[{"name": "vdb1", "path": "/dev/vdb1", "type": "part"}]),
                  disk("vdb", mountpoints=["/mnt"]), disk("vdb", size=10 ** 6), disk("vdb", rm=True), disk("vdb", ro=True), disk("loop0", type="loop")):
            self.assertEqual(W.plan(lsblk(d))[0], "none", d)
    def test_two_blank_disks_is_ambiguous_and_refused(self):
        self.assertEqual(W.plan(lsblk(disk("vdb"), disk("vdc")))[0], "refuse")
    def test_two_labelled_devices_refused(self):
        self.assertEqual(W.plan(lsblk(disk("vdb", fstype="btrfs", label=W.LABEL), disk("vdc", fstype="btrfs", label=W.LABEL)))[0], "refuse")
    def test_finds_labelled_partition_inside_a_disk(self):
        part = {"name": "vdb1", "path": "/dev/vdb1", "type": "part", "fstype": "btrfs", "label": W.LABEL}
        self.assertEqual(W.plan(lsblk(disk("vdb", children=[part])))[:2], ("mount", "/dev/vdb1"))

class Runner:
    def __init__(self, blkid=(2, "", ""), subvol_exists=False, snaps=()):
        self.calls, self.blkid, self.subvol_exists, self.snaps = [], blkid, subvol_exists, list(snaps)
    def __call__(self, argv, **kw):
        self.calls.append(list(argv)); a = argv[0]
        if a == "blkid": return self.blkid
        if argv[:3] == ["btrfs", "subvolume", "show"]: return (0 if self.subvol_exists else 1, "", "")
        if a == "ls": return 0, "\n".join(self.snaps) + "\n", ""
        if argv[:3] == ["btrfs", "subvolume", "snapshot"] and argv[3] == "-r": self.snaps.append(argv[-1].rsplit("/", 1)[1])
        return 0, "", ""

class Apply(unittest.TestCase):
    def test_format_then_mount_with_noexec_and_subvolumes(self):
        r = Runner(); W.apply("format", "/dev/vdb", r); cmds = [c[0] for c in r.calls]
        self.assertEqual(cmds[:2], ["blkid", "mkfs.btrfs"]); mount = next(c for c in r.calls if c[0] == "mount")
        opts = mount[mount.index("-o") + 1]
        for o in ("noexec", "nosuid", "nodev"): self.assertIn(o, opts)
        self.assertEqual(sum(1 for c in r.calls if c[:3] == ["btrfs", "subvolume", "create"]), 2)
    def test_disk_that_stopped_being_blank_is_not_formatted(self):
        for blkid in ((0, "/dev/vdb: TYPE=ext4", ""), (2, "something", ""), (1, "", "error")):
            r = Runner(blkid=blkid)
            with self.assertRaises(W.DiskError): W.apply("format", "/dev/vdb", r)
            self.assertFalse([c for c in r.calls if c[0] == "mkfs.btrfs"], blkid)
    def test_existing_disk_is_mounted_without_mkfs_and_existing_subvolumes_kept(self):
        r = Runner(subvol_exists=True); W.apply("mount", "/dev/vdb", r)
        self.assertFalse([c for c in r.calls if c[0] == "mkfs.btrfs" or c[:3] == ["btrfs", "subvolume", "create"]])
    def test_refuse_and_unsafe_device_names(self):
        with self.assertRaises(W.DiskError): W.apply("refuse", None, Runner())
        for bad in ("vdb", "/dev/../etc/x", "/dev/vdb; rm", "/dev/vdb\n", "-f"):
            with self.assertRaises(W.DiskError, msg=bad): W.apply("mount", bad, Runner())
        self.assertEqual(W.apply("none", None, Runner()), "no work disk")

class Snapshots(unittest.TestCase):
    CLOCK = staticmethod(lambda: time.gmtime(1_700_000_000))
    def test_names_are_validated(self):
        self.assertEqual(W.new_name("", self.CLOCK), "20231114T221320Z"); self.assertTrue(W.new_name("before-refactor", self.CLOCK).endswith("-before-refactor"))
        for bad in ("../x", "UPPER", "a b", "x" * 40, "a/b", "-x", "a\n"):
            with self.assertRaises(W.DiskError, msg=bad): W.new_name(bad, self.CLOCK)
    def test_snapshot_is_read_only_and_old_ones_pruned(self):
        old = ["2020%02d01T000000Z" % m for m in range(1, 13)] * 2
        r = Runner(snaps=sorted(set(old))[:])
        W.KEEP_SNAPSHOTS, keep = 5, W.KEEP_SNAPSHOTS
        try:
            W.snapshot(r, "", self.CLOCK)
        finally:
            W.KEEP_SNAPSHOTS = keep
        self.assertTrue(any(c[:4] == ["btrfs", "subvolume", "snapshot", "-r"] for c in r.calls))
        self.assertGreaterEqual(sum(1 for c in r.calls if c[:3] == ["btrfs", "subvolume", "delete"]), 1)
    def test_junk_entries_in_the_snapshot_dir_are_never_passed_to_delete(self):
        r = Runner(snaps=["../../etc", "20200101T000000Z", "random"])
        self.assertEqual(W.list_snapshots(r), ["20200101T000000Z"])
    def test_rollback_keeps_current_state_first_and_rejects_unknown_names(self):
        r = Runner(snaps=["20200101T000000Z"])
        keep = W.rollback(r, "20200101T000000Z", self.CLOCK); self.assertTrue(keep.endswith("-pre-rollback"))
        order = [c for c in r.calls if c[0] == "btrfs"]
        self.assertEqual(order[0][3], "-r"); self.assertEqual(order[1][2], "delete"); self.assertNotIn("-r", order[2])    # keep, delete work, restore writable
        for bad in ("nope", "../work", "", None):
            with self.assertRaises(W.DiskError): W.rollback(Runner(snaps=["20200101T000000Z"]), bad)

class SysVerify(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.p = self.t.name
        for d in ("/usr/local/lib/aiws", "/usr/local/bin"): os.makedirs(self.p + d)
        Path(self.p + "/usr/local/lib/aiws/a.py").write_text("print(1)"); Path(self.p + "/usr/local/bin/aiws-x").write_text("#!/bin/sh\n")
        os.symlink("a.py", self.p + "/usr/local/lib/aiws/link")
        self.roots = ("/usr/local/lib/aiws", "/usr/local/bin")
        self.m = V.build_manifest(self.roots, self.p)
    def tearDown(self): self.t.cleanup()
    def test_clean_tree_verifies(self):
        self.assertTrue(V.verify(self.m, self.roots, self.p)["ok"])
    def test_modified_missing_and_unlisted_are_reported(self):
        Path(self.p + "/usr/local/lib/aiws/a.py").write_text("print(2)"); os.remove(self.p + "/usr/local/bin/aiws-x"); Path(self.p + "/usr/local/bin/evil").write_text("x")
        r = V.verify(self.m, self.roots, self.p)
        self.assertFalse(r["ok"]); self.assertEqual(r["modified"], ["/usr/local/lib/aiws/a.py"]); self.assertEqual(r["missing"], ["/usr/local/bin/aiws-x"]); self.assertEqual(r["unlisted"], ["/usr/local/bin/evil"])
    def test_replacing_a_file_with_a_symlink_or_retargeting_a_link_is_caught(self):
        os.remove(self.p + "/usr/local/bin/aiws-x"); os.symlink("/bin/sh", self.p + "/usr/local/bin/aiws-x")
        os.remove(self.p + "/usr/local/lib/aiws/link"); os.symlink("/etc/passwd", self.p + "/usr/local/lib/aiws/link")
        r = V.verify(self.m, self.roots, self.p); self.assertFalse(r["ok"]); self.assertIn("/usr/local/bin/aiws-x", r["modified"]); self.assertIn("/usr/local/lib/aiws/link", r["modified"])
    def test_unlisted_files_only_count_in_strict_roots(self):
        Path(self.p + "/usr/local/bin/devtool").write_text("x")            # developers install here: not a finding
        self.assertTrue(V.verify(self.m, ("/usr/local/lib/aiws",), self.p)["ok"])
        Path(self.p + "/usr/local/lib/aiws/planted.py").write_text("x")    # but here the image is the only writer
        self.assertIn("/usr/local/lib/aiws/planted.py", V.verify(self.m, ("/usr/local/lib/aiws",), self.p)["unlisted"])
    def test_manifest_file_itself_and_model_weights_are_skipped(self):
        os.makedirs(self.p + "/usr/local/share/aiws/model-preload"); Path(self.p + "/usr/local/share/aiws/model-preload/w.gguf").write_bytes(b"x" * 10)
        Path(self.p + V.MANIFEST).write_text("{}")
        m = V.build_manifest(("/usr/local/share/aiws",), self.p)
        self.assertEqual(m, {})
        self.assertTrue(V.verify(m, ("/usr/local/share/aiws",), self.p)["ok"])
    def test_pyc_files_are_ignored(self):
        os.makedirs(self.p + "/usr/local/lib/aiws/__pycache__"); Path(self.p + "/usr/local/lib/aiws/__pycache__/a.pyc").write_bytes(b"x"); Path(self.p + "/usr/local/lib/aiws/b.pyc").write_bytes(b"x")
        self.assertTrue(V.verify(self.m, self.roots, self.p)["ok"])

if __name__ == "__main__":
    unittest.main()
