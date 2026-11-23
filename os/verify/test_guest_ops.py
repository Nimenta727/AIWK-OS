"""Guest service/immutable kernel candidate operation contract (no root/host)."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"runtime"))
from aiws_guest_ops import GuestOperations, GuestOperationError, validate

class GuestOperationsTest(unittest.TestCase):
    def setUp(self):
        self.boundary=patch("aiws_guest_ops.protect_guest_workspace",return_value=True)
        self.tool_boundary=patch("aiws_toolplane.protect_guest_workspace",return_value=True)
        self.boundary.start()
        self.tool_boundary.start()
        self.temp=tempfile.TemporaryDirectory()
        base=Path(self.temp.name)
        self.workspace=base/"guest-project"
        self.workspace.mkdir()
        self.state=base/"private-kernel-candidates"
        self.commands=[]
        def fake_run(command,**kwargs):
            self.commands.append(command)
            return SimpleNamespace(returncode=0,stdout="LoadState=loaded\nActiveState=active\nSubState=running\n")
        self.ops=GuestOperations(self.workspace,self.state,guard=lambda:True,runner=fake_run)
        self.fragment=self.workspace/"policy.fragment"
        self.fragment.write_text("CONFIG_VIRTIO=y\nCONFIG_SECCOMP=y\n",encoding="ascii")
        self.digest=hashlib.sha256(self.fragment.read_bytes()).hexdigest()

    def tearDown(self):
        self.temp.cleanup()
        self.tool_boundary.stop()
        self.boundary.stop()

    def test_model_service_enable_disable_also_require_approved_dag(self):
        for tool in ("service.enable","service.disable"):
            with self.assertRaises(PermissionError):
                self.ops.execute(tool,{"service":"aiws-local-model.service"})
            with self.assertRaises(GuestOperationError):
                self.ops.execute(tool,{"service":"host.service"},approved=True)
        # The disable operation can be tested without any model weights.
        # All systemd calls are intercepted by a fake, never executed.
        with patch("aiws_guest_ops.Path.home",return_value=self.root if hasattr(self,"root") else self.workspace):
            result=self.ops.execute("service.disable",
                {"service":"aiws-local-model.service"},approved=True)
        self.assertFalse(result["enabled"])
        self.assertEqual(self.commands[-1],
            ["systemctl","--user","disable","--now","aiws-local-model.service"])

    def test_service_is_allowlisted_and_mutations_require_approval(self):
        self.assertEqual(self.ops.execute("service.inspect",
            {"service":"aiws-local-model.service"})["status"]["ActiveState"],"active")
        self.assertEqual(self.commands[0][-1],"aiws-local-model.service")
        for name in ("ssh.service","host.service","aiws-workbench.service"):
            with self.assertRaises(GuestOperationError):
                self.ops.execute("service.restart",{"service":name},approved=True)
        with self.assertRaises(PermissionError):
            self.ops.execute("service.restart",{"service":"aiws-local-model.service"})
        self.ops.execute("service.restart",{"service":"aiws-local-model.service"},approved=True)
        self.assertEqual(self.commands[-1],["systemctl","--user","restart","aiws-local-model.service"])
        self.assertFalse(any("sudo" in str(x) or "qemu" in str(x) for x in self.commands))

    def test_kernel_stage_verify_abandon_without_deployment(self):
        args={"path":"policy.fragment","expectedSha256":self.digest}
        with self.assertRaises(PermissionError):
            self.ops.execute("kernel.stage",args)
        staged=self.ops.execute("kernel.stage",args,approved=True)
        self.assertFalse(staged["deployed"])
        cid=staged["id"]
        self.assertEqual(self.ops.execute("kernel.verify",{"candidateId":cid})["integrity"],"verified")
        recovery=self.ops.execute("kernel.recovery_plan",{"candidateId":cid})
        self.assertFalse(recovery["bootRecoveryReady"])
        self.assertFalse(recovery["bootSlotSwitchAllowed"])
        self.assertEqual(self.ops.execute("kernel.abandon",{"candidateId":cid},approved=True)["status"],"abandoned")
        self.assertEqual(self.ops.execute("kernel.verify",{"candidateId":cid})["status"],"abandoned")
        self.assertFalse(self.commands)

    def test_unsafe_fragment_and_tampering_rejected(self):
        with self.assertRaises(GuestOperationError):
            self.ops.execute("kernel.stage",{"path":"../host.fragment",
                "expectedSha256":self.digest},approved=True)
        with self.assertRaises(GuestOperationError):
            self.ops.execute("kernel.stage",{"path":"policy.fragment",
                "expectedSha256":"0"*64},approved=True)
        self.fragment.write_text("CONFIG_MODULE_SIG_FORCE=n\n",encoding="ascii")
        changed=hashlib.sha256(self.fragment.read_bytes()).hexdigest()
        with self.assertRaises(GuestOperationError):
            self.ops.execute("kernel.stage",{"path":"policy.fragment",
                "expectedSha256":changed},approved=True)

    def test_no_bypass_of_guest_gate(self):
        ops=GuestOperations(self.workspace,self.state,
            guard=lambda:(_ for _ in ()).throw(PermissionError("Must be guest")))
        with self.assertRaises(PermissionError):
            ops.execute("kernel.inspect",{})
        with self.assertRaises(GuestOperationError):
            validate("service.restart",{"service":"../aiws-local-model.service"})

if __name__=="__main__":
    unittest.main()
