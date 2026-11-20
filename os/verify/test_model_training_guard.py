"""Training recipe guard: dry-run never trains or accesses host/model weights."""
import subprocess
import sys
from pathlib import Path
import json
import unittest

class TrainGuardTests(unittest.TestCase):
    def test_train_recipe_defaults_to_dry_run(self):
        root=Path(__file__).resolve().parents[1]
        script=root/"model/training/train_lora.py"
        result=subprocess.run([sys.executable,str(script)],capture_output=True,
                              text=True,check=True,timeout=12)
        report=json.loads(result.stdout)
        self.assertFalse(report["adapter_trained"])
        self.assertTrue(report["dry_run"])
        self.assertIn("HF_HUB_OFFLINE",script.read_text())
        self.assertIn("require_guest_runtime()",script.read_text())
        self.assertIn('CUDA_VISIBLE_DEVICES',script.read_text())

if __name__=="__main__":
    unittest.main()
