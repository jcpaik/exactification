from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.check_blind_inventory import InventoryError, check_blind_inventory


class BlindInventoryCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "blind"
        (self.root / "manual").mkdir(parents=True)
        (self.root / "testcases" / "case-a" / "input").mkdir(parents=True)
        (self.root / "manual" / "workflow.md").write_text("workflow\n")
        (self.root / "testcases" / "case-a" / "input" / "model.json").write_text("{}\n")
        self.write_inventory()

    def entry(self, relative: str) -> dict:
        path = self.root / relative
        return {
            "path": relative,
            "source": relative,
            "category": "fixture",
            "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def write_inventory(self, *, files: list[dict] | None = None) -> None:
        if files is None:
            files = [
                self.entry("manual/workflow.md"),
                self.entry("testcases/case-a/input/model.json"),
            ]
        document = {
            "format": "exactification-blind-workspace-inventory-v1",
            "case_ids": ["case-a"],
            "files": files,
        }
        (self.root / "BLIND_WORKSPACE_INVENTORY.json").write_text(
            json.dumps(document, indent=2) + "\n"
        )

    def test_clean_initial_workspace_passes(self) -> None:
        report = check_blind_inventory(self.root)
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["inventoried_files"], 2)
        self.assertEqual(report["generated_file_count"], 0)

    def test_generated_attempts_require_explicit_mode(self) -> None:
        attempt = self.root / "testcases" / "case-a" / "attempts" / "round-2"
        attempt.mkdir(parents=True)
        (attempt / "certificate.json").write_text("{}\n")
        (self.root / "executor-report-round-2.md").write_text("report\n")
        with self.assertRaisesRegex(InventoryError, "unexpected workspace path"):
            check_blind_inventory(self.root)
        report = check_blind_inventory(self.root, allow_generated_attempts=True)
        self.assertEqual(report["generated_file_count"], 2)

    def test_hash_mismatch_is_rejected(self) -> None:
        (self.root / "manual" / "workflow.md").write_text("changed\n")
        with self.assertRaisesRegex(InventoryError, "hash mismatch|size mismatch"):
            check_blind_inventory(self.root)

    def test_missing_inventoried_file_is_rejected(self) -> None:
        (self.root / "manual" / "workflow.md").unlink()
        with self.assertRaisesRegex(InventoryError, "cannot stat"):
            check_blind_inventory(self.root)

    def test_unlisted_file_is_rejected(self) -> None:
        (self.root / "extra.txt").write_text("extra\n")
        with self.assertRaisesRegex(InventoryError, "unexpected workspace path: extra.txt"):
            check_blind_inventory(self.root)

    def test_inventory_traversal_is_rejected(self) -> None:
        files = [self.entry("manual/workflow.md")]
        files[0]["path"] = "../workflow.md"
        self.write_inventory(files=files)
        with self.assertRaisesRegex(InventoryError, "unsafe relative path"):
            check_blind_inventory(self.root)

    def test_symlink_is_rejected(self) -> None:
        target = self.root / "manual" / "workflow.md"
        link = self.root / "extra-link"
        try:
            link.symlink_to(target)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaisesRegex(InventoryError, "symlinks are forbidden"):
            check_blind_inventory(self.root, allow_generated_attempts=True)

    def test_wrong_case_and_oracle_additions_are_rejected(self) -> None:
        additions = [
            "testcases/case-b/attempts/round-2/certificate.json",
            "testcases/case-a/construction/secret.json",
            "testcases/case-a/oracle/certificate.json",
            "testcases/case-a/attempts/round-2/oracle/secret.json",
            "testcases/case-a/attempts/round-2/construction/secret.json",
            "testcases/case-a/attempts/round-2/oracle.json",
            "testcases/case-a/attempts/round-2/construction.py",
            "testcases/case-a/attempts/round-2/hidden-oracle-data.json",
        ]
        for relative in additions:
            with self.subTest(relative=relative):
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n")
                with self.assertRaisesRegex(InventoryError, "unexpected workspace path"):
                    check_blind_inventory(self.root, allow_generated_attempts=True)
                path.unlink()
                while path.parent != self.root and not any(path.parent.iterdir()):
                    parent = path.parent
                    path = parent
                    parent.rmdir()


if __name__ == "__main__":
    unittest.main()
