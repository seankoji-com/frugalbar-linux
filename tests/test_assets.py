import hashlib
import json
from pathlib import Path
import unittest
from frugalbar_linux.providers import definitions


class OriginalLogos(unittest.TestCase):
    def test_all_provider_logos_are_original_imports(self):
        directory = Path(__file__).resolve().parents[1] / "frugalbar_linux/assets"
        provenance = json.loads((directory / "provenance.json").read_text())
        self.assertEqual(provenance["revision"], "3a058ce5f9298d90d57459b039b745d40224af3d")
        for provider, _ in definitions():
            name = provider + ".svg"
            with self.subTest(provider=provider):
                self.assertIn(name, provenance["sha256"])
                self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), provenance["sha256"][name])
