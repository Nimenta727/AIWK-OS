"""Guest-only model version import/verify/rollback; no real weights or network."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"runtime"))
import aiws_model_registry as REG
from aiws_model_registry import GuestModelRegistry, ModelArtifactError

class GuestModelRegistryTests(unittest.TestCase):
    def setUp(self):
        self.base=tempfile.TemporaryDirectory()
        self.root=Path(self.base.name)
        self.project=self.root/"guest-project"
        self.project.mkdir()
        self.boundary=patch("aiws_model_registry.protect_guest_workspace",return_value=True)
        self.tool_boundary=patch("aiws_toolplane.protect_guest_workspace",return_value=True)
        self.boundary.start();self.tool_boundary.start()
        self.reg=GuestModelRegistry(self.root/"models",self.project,
             guard=lambda:True,runner=lambda *a,**k:SimpleNamespace(returncode=1))
        self.weights=self.project/"model.gguf"
        self.weights.write_bytes(b"GGUF"+b"\x01"*2048)
        self.digest=hashlib.sha256(self.weights.read_bytes()).hexdigest()

    def tearDown(self):
        self.tool_boundary.stop();self.boundary.stop()
        self.base.cleanup()

    def test_import_manifest_verification_and_rollback(self):
        with self.assertRaises(ModelArtifactError):
            self.reg.import_guest("model.gguf",self.digest,False)
        with self.assertRaises(ModelArtifactError):
            self.reg.import_guest("model.gguf","0"*64,True)
        first=self.reg.import_guest("model.gguf",self.digest,True)
        self.assertTrue(first["verified"])
        self.assertEqual(first["sha256"],self.digest)
        self.weights.write_bytes(b"GGUF"+b"\x02"*2048)
        second_sha=hashlib.sha256(self.weights.read_bytes()).hexdigest()
        next_model=self.reg.import_guest("model.gguf",second_sha,True)
        self.assertEqual(next_model["sha256"],second_sha)
        self.assertEqual(self.reg.rollback(self.digest)["sha256"],self.digest)

    def test_corrupted_previous_model_cannot_be_reactivated(self):
        self.reg.import_guest("model.gguf",self.digest,True)
        self.weights.write_bytes(b"GGUF"+b"\x02"*2048)
        latest=hashlib.sha256(self.weights.read_bytes()).hexdigest()
        self.reg.import_guest("model.gguf",latest,True)
        (self.root/"models/versions"/(self.digest+".gguf")).write_bytes(b"tampered")
        with self.assertRaises(ModelArtifactError):
            self.reg.rollback(self.digest)
        self.assertEqual(self.reg.verify()["sha256"],latest)

    def test_modified_current_model_refuses_verification(self):
        self.reg.import_guest("model.gguf",self.digest,True)
        (self.root/"models/aiws-local.gguf").write_bytes(b"GGUF"+b"x"*2048)
        with self.assertRaises(ModelArtifactError):
            self.reg.verify()

    def test_bundled_image_requires_checked_manifest_and_refuses_replacement(self):
        import json
        preload=self.root/"preload"
        preload.mkdir()
        bundled=preload/"aiws-local.gguf"
        bundled.write_bytes(self.weights.read_bytes())
        manifest={"modelId":REG.MODEL_ID,"sha256":self.digest,
                  "source":"test-only fake bytes","licenseReviewed":True}
        (preload/"manifest.json").write_text(json.dumps(manifest))
        read_only=self.reg.import_bundled(preload,verify_only=True)
        self.assertTrue(read_only["bundledReadonly"])
        self.assertFalse((self.root/"models/registry.json").exists())
        result=self.reg.import_bundled(preload)
        self.assertTrue(result["verified"])
        self.assertEqual(self.reg.import_bundled(preload)["sha256"],self.digest)
        bundled.write_bytes(b"GGUF"+b"x"*2048)
        with self.assertRaises(ModelArtifactError):
            self.reg.import_bundled(preload)
        self.assertEqual(self.reg.verify()["sha256"],self.digest)

    def test_guest_guard_and_source_mount_are_mandatory(self):
        bad=GuestModelRegistry(self.root/"models",self.project,
            guard=lambda:(_ for _ in ()).throw(PermissionError("not guest")))
        with self.assertRaises(PermissionError):
            bad.import_guest("model.gguf",self.digest,True)
        with self.assertRaises((ValueError,PermissionError)):
            self.reg.import_guest("../host.gguf",self.digest,True)


class ProductModelPinTests(unittest.TestCase):
    def test_product_model_is_the_9b_and_the_size_limit_fits_it(self):
        self.assertEqual(REG.MODEL_ID, "Qwen/Qwen3.5-9B")
        self.assertGreater(REG.MAX_BYTES, 6 * 1024 ** 3)                  # Q4_K_M of the 9B is about 5.7 GB

    def test_the_small_model_is_refused_unless_the_ci_marker_exists(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "guest-model-acceptance"
            self.assertEqual(REG.approved_model_ids(marker), {REG.MODEL_ID})          # no marker: product only
            marker.write_text("AIWS_MODEL_CI_ONLY=1\n")
            self.assertEqual(REG.approved_model_ids(marker), {REG.MODEL_ID, REG.CI_MODEL_ID})
            marker.write_text("something else\n")
            self.assertEqual(REG.approved_model_ids(marker), {REG.MODEL_ID})
            link = Path(d) / "link"
            marker.write_text("AIWS_MODEL_CI_ONLY=1\n")
            link.symlink_to(marker)
            self.assertEqual(REG.approved_model_ids(link), {REG.MODEL_ID})            # a symlink never counts

    def test_a_manifest_naming_the_small_model_fails_verification_in_a_product_image(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            project = base / "p"; project.mkdir()
            with patch("aiws_model_registry.protect_guest_workspace", return_value=True), patch("aiws_toolplane.protect_guest_workspace", return_value=True), \
                 patch("aiws_model_registry.CI_MARKER", base / "absent"):
                reg = GuestModelRegistry(base / "models", project, guard=lambda: True, runner=lambda *a, **k: SimpleNamespace(returncode=1))
                weights = project / "m.gguf"; weights.write_bytes(b"GGUF" + b"\x02" * 2048)
                digest = hashlib.sha256(weights.read_bytes()).hexdigest()
                reg.import_guest("m.gguf", digest, True)
                manifest = base / "models" / "registry.json"
                import json
                data = json.loads(manifest.read_text()); data["modelId"] = REG.CI_MODEL_ID; manifest.write_text(json.dumps(data))
                with self.assertRaises(ModelArtifactError):
                    reg.verify()


if __name__=="__main__":
    unittest.main()
