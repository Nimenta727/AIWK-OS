import json, re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class LegalConsistencyTests(unittest.TestCase):
    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_license_is_apache_and_every_document_agrees(self):
        self.assertIn("Apache License", self.read("LICENSE")[:200])
        self.assertIn("Apache-2.0", self.read("README.md"))
        for rel in ("README.md", "os/README.md", "docs/CODEBASE_MAP.md"):
            self.assertNotRegex(self.read(rel), r"(当前|currently)\s*MIT|仓库.{0,6}MIT 许可证", rel)
        self.assertEqual(json.loads(self.read("desktop/AIWorkstation.Frontend/package.json")).get("license"), "Apache-2.0")

    def test_notice_credits_third_parties_and_disclaims_trademarks(self):
        n = self.read("NOTICE")
        for needle in ("Apache License, Version 2.0", "T3 Tools Inc.", "Code - OSS", "Microsoft Corporation",
                       "not affiliated with or endorsed by Microsoft", "ThirdPartyNotices.txt"):
            self.assertIn(needle, n)

    def test_adapted_mit_code_keeps_its_license_text(self):
        t = self.read("third_party/t3code/NOTICE.md")
        self.assertIn("Permission is hereby granted, free of charge", t)
        self.assertIn("Copyright (c) 2026 T3 Tools Inc.", t)

    def test_repository_does_not_vendor_microsoft_code_or_marks(self):
        # Code - OSS is fetched at build time; nothing of it (or its logo) may be committed here.
        for rel in ("os/ide/branding",):
            for f in (ROOT / rel).rglob("*"):
                if f.is_file() and f.suffix in (".svg", ".png", ".ico"):
                    self.assertNotIn("microsoft", f.read_bytes()[:4000].lower().decode("latin-1"), str(f))
        self.assertFalse((ROOT / "os/ide/src").exists())

if __name__ == "__main__":
    unittest.main()
