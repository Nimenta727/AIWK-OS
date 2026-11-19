import tempfile
import unittest
import zipfile
from pathlib import Path
from scripts.package_portable import package


class PackageTests(unittest.TestCase):
    def test_portable_archive_excludes_secrets_and_runtime_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            (root / 'aiws').mkdir(parents=True)
            (root / 'web').mkdir()
            (root / '.git').mkdir()
            (root / 'aiws' / '__pycache__').mkdir()
            (root / 'app.py').write_text('print(1)', encoding='utf-8')
            (root / 'README.md').write_text('# demo', encoding='utf-8')
            (root / '.env').write_text('DO_NOT_PACKAGE', encoding='utf-8')
            (root / 'aiws' / 'backend.py').write_text('pass', encoding='utf-8')
            (root / 'aiws' / '__pycache__' / 'bad.pyc').write_bytes(b'SECRET')
            (root / 'web' / 'index.html').write_text('ok', encoding='utf-8')
            output = Path(tmp) / 'AIWS-Prototype.zip'
            paths = package(output, root)
            with zipfile.ZipFile(output) as f:
                self.assertEqual(set(f.namelist()), set(paths))
                self.assertIn('app.py', paths)
                self.assertIn('web/index.html', paths)
                self.assertNotIn('.env', paths)
                self.assertNotIn('aiws/__pycache__/bad.pyc', paths)
                self.assertNotIn(b'DO_NOT_PACKAGE', b''.join(f.read(name) for name in paths))


if __name__ == '__main__':
    unittest.main()
