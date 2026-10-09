import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build import verify_signer


class SigningTests(unittest.TestCase):
    fingerprint = "bd3aeb249a8808fba86bb5a182a0a2903fe1cbbbb0249b7271ce32e9fee7984a"

    def test_numbered_signer(self):
        verify_signer("Signer #1 certificate SHA-256 digest: " + self.fingerprint + "\n", self.fingerprint)

    def test_scheme_labelled_signer(self):
        verify_signer("V2 Signer: certificate SHA-256 digest: " + self.fingerprint + "\n", self.fingerprint)

    def test_uppercase_fingerprint(self):
        verify_signer("V3 Signer: certificate SHA-256 digest: " + self.fingerprint.upper() + "\n", self.fingerprint)

    def test_wrong_certificate_is_rejected(self):
        with self.assertRaises(RuntimeError):
            verify_signer("V2 Signer: certificate SHA-256 digest: " + "0" * 64 + "\n", self.fingerprint)

    def test_missing_certificate_is_rejected(self):
        with self.assertRaises(RuntimeError):
            verify_signer("No certificate digest\n", self.fingerprint)

    def test_additional_wrong_signer_is_rejected(self):
        with self.assertRaises(RuntimeError):
            verify_signer(
                "Signer #1 certificate SHA-256 digest: " + self.fingerprint + "\n"
                + "Signer #2 certificate SHA-256 digest: " + "0" * 64 + "\n",
                self.fingerprint,
            )


if __name__ == "__main__":
    unittest.main()
