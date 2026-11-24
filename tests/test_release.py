"""Synthetic data-ingestion, checkpoint-integrity, and source-export checks."""

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audit_release
import export_release
from src import evaluation as ev
from src.study_io import acquire, load_manifest
from test_study import synthetic_inputs


class ReleaseTests(unittest.TestCase):
    def test_secret_scan_reports_category_not_value(self):
        token = "sk-or-" + "v1-" + "SYNTHETICEXAMPLE" * 4
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "example.txt").write_text(token)
            result = audit_release.scan_tree(root)
            self.assertIn("openrouter_credential", result[0]["categories"])
            self.assertNotIn(token, json.dumps(result))
            self.assertEqual(audit_release.scan_bytes(b"ordinary public documentation"), [])

    def test_private_assets_and_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "image.jpg").write_bytes(b"SYNTHETIC")
            (root / "link").symlink_to(root / "image.jpg")
            result = audit_release.scan_tree(root)
            self.assertEqual(len(result), 2)
            self.assertTrue(any("symlink" in r["categories"] for r in result))

    def test_clean_export_is_history_free_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "candidate"
            result = export_release.export(destination)
            self.assertFalse(result["history_copied"])
            self.assertFalse((destination / ".git").exists())
            self.assertFalse((destination / "output").exists())
            self.assertFalse((destination / "scripts").exists())
            self.assertEqual(audit_release.scan_tree(destination), [])
            hashes = json.loads((destination / "RELEASE_SHA256.json").read_text())
            self.assertTrue(
                all(
                    hashlib.sha256((destination / p).read_bytes()).hexdigest() == h
                    for p, h in hashes.items()
                )
            )
            with self.assertRaises(ValueError):
                export_release.export(destination)

    def test_archive_hash_and_image_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            images, manifest, _ = synthetic_inputs(directory)
            archive = directory / "synthetic.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                for r in load_manifest(manifest):
                    bundle.writestr(r["source_member_path"], (images / r["filename"]).read_bytes())
            with self.assertRaisesRegex(ValueError, "Archive SHA-256"):
                acquire(archive, directory / "out", manifest)
            archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch("src.study_io.ARCHIVE_SHA256", archive_hash):
                self.assertEqual(len(acquire(archive, directory / "out", manifest)), 20)
                self.assertEqual(len(acquire(archive, directory / "out", manifest)), 20)
                (directory / "out" / "105.jpg").write_bytes(b"CHANGED")
                with self.assertRaisesRegex(ValueError, "overwrite"):
                    acquire(archive, directory / "out", manifest)

    def test_checkpoint_verifier_never_reselects_or_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = {
                "model": "example/model",
                "image_filename": "synthetic.jpg",
                "status": "ASSESSABLE_FINDINGS",
                "parsed_response": {"problem_teeth": [11, 21]},
                "http_response": {"http_status": 200},
            }
            ev.write_new(root / "raw.json", raw)
            row = {
                "model": "example/model",
                "image_filename": "synthetic.jpg",
                "status": "ASSESSABLE_FINDINGS",
                "selected_record": "raw.json",
                "evaluable": True,
                "predicted_teeth": [11, 21],
                "reference_teeth": [11, 12],
                "tp": 1,
                "fp": 1,
                "fn": 1,
            }
            metrics = ev.metrics_for_pairs([row])
            checkpoint = {
                "pairs": [row],
                "models": {"example/model": {"tooth_metrics_micro": metrics}},
            }
            ev.write_new(root / "checkpoint.json", checkpoint)
            before = (root / "checkpoint.json").read_bytes()
            result = ev.verify_checkpoint([root / "checkpoint.json"], root)
            self.assertEqual(result["models"]["example/model"]["f1"], 0.5)
            self.assertEqual((root / "checkpoint.json").read_bytes(), before)
            checkpoint["pairs"][0]["tp"] = 99
            (root / "checkpoint.json").write_text(json.dumps(checkpoint))
            with self.assertRaisesRegex(ValueError, "counts"):
                ev.verify_checkpoint([root / "checkpoint.json"], root)
            checkpoint["pairs"][0]["selected_record"] = "../outside.json"
            (root / "checkpoint.json").write_text(json.dumps(checkpoint))
            with self.assertRaisesRegex(ValueError, "escapes"):
                ev.verify_checkpoint([root / "checkpoint.json"], root)


if __name__ == "__main__":
    unittest.main()
