from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.build_blind_workspace import (
    EXACTIFY_RUNTIME_FILES,
    INVENTORY_NAME,
    TRUSTED_FILES,
    BuildError,
    build_blind_workspace,
)


class BlindRepositoryFixture:
    def __init__(self, directory: str) -> None:
        self.root = Path(directory) / "repository"
        self.root.mkdir()
        for relative in TRUSTED_FILES + EXACTIFY_RUNTIME_FILES:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# public runtime: {relative}\n", encoding="utf-8")
        self.add_case("case-one")
        self.add_case("case-two")

    def add_case(self, case_id: str) -> Path:
        input_directory = self.root / "testcases" / case_id / "input"
        input_directory.mkdir(parents=True)
        (input_directory / "README.md").write_text(
            f"Public input for {case_id}.\n", encoding="utf-8"
        )
        for filename, value in (
            ("manifest.json", {"format": "exactification-testcase-v1", "id": case_id}),
            ("model.json", {"format": "exact-block-sdp-model-v1"}),
            (
                "approximate_solution.json",
                {"format": "approximate-block-sdp-solution-v1"},
            ),
        ):
            (input_directory / filename).write_text(
                json.dumps(value, sort_keys=True) + "\n", encoding="utf-8"
            )
        return input_directory


class BlindWorkspaceBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = BlindRepositoryFixture(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def destination(self, name: str) -> Path:
        return Path(self.temporary.name) / name

    def test_inventory_is_deterministic_across_destinations_and_case_order(self) -> None:
        first = self.destination("first")
        second = self.destination("second")

        first_report = build_blind_workspace(
            self.fixture.root, first, ["case-two", "case-one"]
        )
        second_report = build_blind_workspace(
            self.fixture.root, second, ["case-one", "case-two"]
        )

        self.assertEqual(first_report["inventory_sha256"], second_report["inventory_sha256"])
        self.assertEqual(
            (first / INVENTORY_NAME).read_bytes(),
            (second / INVENTORY_NAME).read_bytes(),
        )
        inventory = json.loads((first / INVENTORY_NAME).read_text(encoding="utf-8"))
        paths = [record["path"] for record in inventory["files"]]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(inventory["case_ids"], ["case-one", "case-two"])

    def test_only_selected_public_input_and_allowlisted_runtime_are_copied(self) -> None:
        case_root = self.fixture.root / "testcases" / "case-one"
        (case_root / "attempts" / "old").mkdir(parents=True)
        (case_root / "attempts" / "old" / "certificate.json").write_text(
            "ATTEMPT_SECRET", encoding="utf-8"
        )
        (case_root / "construction").mkdir()
        (case_root / "construction" / "witness.json").write_text(
            "CONSTRUCTION_SECRET", encoding="utf-8"
        )
        (case_root / "oracle").mkdir()
        (case_root / "oracle" / "expected.json").write_text(
            "ORACLE_SECRET", encoding="utf-8"
        )

        destination = self.destination("blind")
        build_blind_workspace(self.fixture.root, destination, ["case-one"])

        copied = [
            path.relative_to(destination).as_posix()
            for path in destination.rglob("*")
            if path.is_file()
        ]
        self.assertFalse(any("attempts" in Path(path).parts for path in copied))
        self.assertFalse(any("construction" in Path(path).parts for path in copied))
        self.assertFalse(any("oracle" in Path(path).parts for path in copied))
        self.assertFalse(any("case-two" in Path(path).parts for path in copied))
        all_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in destination.rglob("*")
            if path.is_file()
        )
        self.assertNotIn("ATTEMPT_SECRET", all_text)
        self.assertNotIn("CONSTRUCTION_SECRET", all_text)
        self.assertNotIn("ORACLE_SECRET", all_text)

    def test_case_id_traversal_is_rejected_without_partial_destination(self) -> None:
        destination = self.destination("traversal")

        with self.assertRaisesRegex(BuildError, "unsafe testcase ID"):
            build_blind_workspace(self.fixture.root, destination, ["../oracle"])

        self.assertFalse(destination.exists())

    def test_public_input_symlink_is_rejected(self) -> None:
        outside = Path(self.temporary.name) / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        link = self.fixture.root / "testcases" / "case-one" / "input" / "linked.json"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        destination = self.destination("symlink")

        with self.assertRaisesRegex(BuildError, "symlinks are forbidden"):
            build_blind_workspace(self.fixture.root, destination, ["case-one"])

        self.assertFalse(destination.exists())

    def test_symlinked_testcase_root_is_rejected(self) -> None:
        target = self.fixture.root / "testcases" / "case-one"
        link = self.fixture.root / "testcases" / "linked-case"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        destination = self.destination("root-symlink")

        with self.assertRaisesRegex(BuildError, "testcase root must be a real directory"):
            build_blind_workspace(self.fixture.root, destination, ["linked-case"])

        self.assertFalse(destination.exists())

    def test_symlinked_testcases_parent_is_rejected(self) -> None:
        testcases = self.fixture.root / "testcases"
        real_testcases = self.fixture.root / "testcases-real"
        testcases.rename(real_testcases)
        try:
            testcases.symlink_to(real_testcases, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        destination = self.destination("parent-symlink")

        with self.assertRaisesRegex(BuildError, "testcases directory must be a real directory"):
            build_blind_workspace(self.fixture.root, destination, ["case-one"])

        self.assertFalse(destination.exists())

    def test_oracle_path_inside_public_input_is_rejected(self) -> None:
        oracle = (
            self.fixture.root
            / "testcases"
            / "case-one"
            / "input"
            / "oracles"
        )
        oracle.mkdir()
        (oracle / "secret.json").write_text("{}\n", encoding="utf-8")

        with self.assertRaisesRegex(BuildError, "prohibited path component"):
            build_blind_workspace(
                self.fixture.root, self.destination("oracle"), ["case-one"]
            )

    def test_certificate_content_leak_is_rejected(self) -> None:
        leak = (
            self.fixture.root
            / "testcases"
            / "case-one"
            / "input"
            / "leak.json"
        )
        leak.write_text(
            json.dumps({"format": "exact-block-sdp-certificate-v1"}) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(BuildError, "certificate-format object leaked"):
            build_blind_workspace(
                self.fixture.root, self.destination("leak"), ["case-one"]
            )

    def test_cache_files_are_excluded(self) -> None:
        input_directory = self.fixture.root / "testcases" / "case-one" / "input"
        cache = input_directory / "__pycache__"
        cache.mkdir()
        (cache / "module.pyc").write_bytes(b"cache")
        (input_directory / ".DS_Store").write_bytes(b"cache")
        destination = self.destination("no-cache")

        build_blind_workspace(self.fixture.root, destination, ["case-one"])

        self.assertFalse(any("__pycache__" in path.parts for path in destination.rglob("*")))
        self.assertFalse((destination / "testcases/case-one/input/.DS_Store").exists())

    def test_existing_destination_is_never_overwritten(self) -> None:
        destination = self.destination("existing")
        destination.mkdir()
        sentinel = destination / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(BuildError, "refusing to overwrite"):
            build_blind_workspace(self.fixture.root, destination, ["case-one"])

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_generic_run_recorder_attempt_placeholder_is_allowlisted(self) -> None:
        recorder = self.fixture.root / "exactify" / "make_run_records.py"
        recorder.write_text(
            "# Generic output: attempts/<attempt-id>/run.json\n",
            encoding="utf-8",
        )
        destination = self.destination("generic-recorder")

        build_blind_workspace(self.fixture.root, destination, ["case-one"])

        self.assertEqual(
            (destination / "exactify/make_run_records.py").read_bytes(),
            recorder.read_bytes(),
        )

    def test_hardcoded_testcase_path_in_runtime_is_rejected(self) -> None:
        recorder = self.fixture.root / "exactify" / "make_run_records.py"
        recorder.write_text(
            "OUTPUT = 'testcases/grzesik-pentagon/attempts/new'\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(BuildError, "hardcoded testcase path"):
            build_blind_workspace(
                self.fixture.root, self.destination("case-specific"), ["case-one"]
            )

    def test_hardcoded_attempt_identifier_in_runtime_is_rejected(self) -> None:
        recorder = self.fixture.root / "exactify" / "make_run_records.py"
        recorder.write_text("OUTPUT = 'retry-2'\n", encoding="utf-8")

        with self.assertRaisesRegex(BuildError, "hardcoded attempt identifier"):
            build_blind_workspace(
                self.fixture.root, self.destination("attempt-specific"), ["case-one"]
            )


if __name__ == "__main__":
    unittest.main()
