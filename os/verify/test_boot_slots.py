"""A/B boot slot staging and one-shot fallback contract (no real bootctl)."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"runtime"))
from aiws_boot_slots import BootSlots, BootSlotError

class BootSlotsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        self.esp=root/"esp"
        self.inbox=root/"inbox"
        self.state=root/"state"
        (self.esp/"loader/entries").mkdir(parents=True)
        self.inbox.mkdir()
        (self.esp/"loader/entries/aiws-A.conf").write_text(
            "title AIWS known-good A\nlinux /aiws/slot-a/vmlinuz\n"
            "initrd /aiws/slot-a/initrd\noptions root=UUID=TEST rw console=ttyS0 aiws.slot=A\n")
        self.kernel=self.inbox/"vmlinuz-new"
        self.initrd=self.inbox/"initrd-new"
        self.kernel.write_bytes(b"MZ"+b"K"*8192)
        self.initrd.write_bytes(b"I"*8192)
        self.calls=[]
        def runner(argv,**kwargs):
            self.calls.append(argv)
            return SimpleNamespace(returncode=0,stdout="")
        self.mgr=BootSlots(self.esp,self.inbox,self.state,guard=lambda:None,
                           runner=runner,mount_check=lambda path:True)
        self.sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def test_trial_boot_preserves_known_good_and_rollback(self):
        receipt=self.mgr.stage("vmlinuz-new","initrd-new","6.12.42-aiws",
                               self.sha(self.kernel),self.sha(self.initrd))
        self.assertEqual(receipt["status"],"staged")
        self.assertTrue((self.esp/"loader/entries/aiws-A.conf").is_file())
        conf=(self.esp/"loader/entries/aiws-B+3.conf").read_text()
        self.assertIn("aiws.slot=B",conf)
        self.assertNotIn("aiws.slot=A",conf)
        self.assertTrue(self.mgr.try_once()["trialRequested"])
        self.assertEqual(self.calls[-2:],
            [["bootctl","set-default","aiws-A.conf"],
             ["bootctl","set-oneshot","aiws-B+3.conf"]])
        self.assertEqual(self.mgr.rollback()["nextBoot"],"A")
        self.assertEqual(self.calls[-2:],
            [["bootctl","set-default","aiws-A.conf"],
             ["bootctl","set-oneshot","aiws-A.conf"]])

    def test_bad_hash_and_repeated_slot_rejected(self):
        with self.assertRaises(BootSlotError):
            self.mgr.stage("vmlinuz-new","initrd-new","6.12.42",
                           "0"*64,self.sha(self.initrd))
        self.mgr.stage("vmlinuz-new","initrd-new","6.12.42",
                       self.sha(self.kernel),self.sha(self.initrd))
        with self.assertRaises(BootSlotError):
            self.mgr.stage("vmlinuz-new","initrd-new","6.12.42",
                           self.sha(self.kernel),self.sha(self.initrd))
        (self.esp/"aiws/slot-b/vmlinuz").write_bytes(b"MODIFIED")
        with self.assertRaises(BootSlotError):
            self.mgr.try_once()

    def test_unsafe_artifact_paths_rejected(self):
        with self.assertRaises(BootSlotError):
            self.mgr.stage("../../host","initrd-new","6.12",
                           self.sha(self.kernel),self.sha(self.initrd))
        with self.assertRaises(BootSlotError):
            self.mgr.stage("vmlinuz-new","initrd-new","6.12;evil",
                           self.sha(self.kernel),self.sha(self.initrd))

if __name__=="__main__":
    unittest.main()
