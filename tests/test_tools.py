import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aiws.tools import interactive


class ToolTests(unittest.TestCase):
    def test_interactive_uses_resolved_path(self):
        with tempfile.TemporaryDirectory() as temp:
            binary = r"C:\Program Files\Safe Agent\codex.cmd"
            with patch("aiws.tools.platform.system", return_value="Windows"), \
                 patch("aiws.tools.shutil.which", return_value=binary), \
                 patch("aiws.tools.subprocess.Popen") as popen, \
                 patch("aiws.tools.subprocess.CREATE_NEW_CONSOLE", 16, create=True):
                interactive("codex", Path(temp))
            args = popen.call_args.args[0]
            self.assertEqual(args[:2], ["cmd.exe", "/k"])
            self.assertIn(binary, args[2])
            self.assertNotEqual(args[2], "codex")

    def test_unknown_agent_rejected(self):
        with self.assertRaises(ValueError):
            interactive("powershell", Path("."))


if __name__ == "__main__":
    unittest.main()
