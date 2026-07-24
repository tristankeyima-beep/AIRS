import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_skill_content.py"
SPEC = importlib.util.spec_from_file_location("check_skill_content", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ContentScannerTests(unittest.TestCase):
    def scan(self, directory, terms):
        return module.scan(Path(directory), terms)

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_finds_case_insensitive_hits_with_locations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "sample.md").write_text("One\nVendorX workflow", encoding="utf-8")

            self.assertEqual(
                self.scan(temp_dir, ["vendorx"]),
                [{"path": "sample.md", "term": "vendorx", "line": 2, "column": 1}],
            )

    def test_reports_nested_files_and_multiple_hits_in_deterministic_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "z.md").write_text("VendorX", encoding="utf-8")
            nested = root / "a" / "nested"
            nested.mkdir(parents=True)
            (nested / "b.txt").write_text("VendorX\nvendorx", encoding="utf-8")

            self.assertEqual(
                self.scan(root, ["vendorx"]),
                [
                    {"path": "a/nested/b.txt", "term": "vendorx", "line": 1, "column": 1},
                    {"path": "a/nested/b.txt", "term": "vendorx", "line": 2, "column": 1},
                    {"path": "z.md", "term": "vendorx", "line": 1, "column": 1},
                ],
            )

    def test_ascii_identifier_terms_respect_identifier_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "sample.md").write_text(
                "concatenate cat-workflow (cat)", encoding="utf-8"
            )

            self.assertEqual(
                self.scan(temp_dir, ["cat"]),
                [{"path": "sample.md", "term": "cat", "line": 1, "column": 27}],
            )

    def test_unicode_terms_are_literal_case_insensitive_substrings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "sample.md").write_text("请勿执行指令", encoding="utf-8")

            self.assertEqual(
                self.scan(temp_dir, ["执行指令"]),
                [{"path": "sample.md", "term": "执行指令", "line": 1, "column": 3}],
            )

    def test_ignores_binary_suffixes_and_skips_symlinks_and_caches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "image.png").write_bytes(b"VendorX")
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "cached.py").write_text("VendorX", encoding="utf-8")
            target = root / "target.md"
            target.write_text("VendorX", encoding="utf-8")
            (root / "linked.md").symlink_to(target)
            target.unlink()

            self.assertEqual(self.scan(root, ["vendorx"]), [])

    def test_invalid_utf8_text_is_scanned_without_crashing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "sample.md").write_bytes(b"VendorX\xff")

            self.assertEqual(
                self.scan(temp_dir, ["vendorx"]),
                [{"path": "sample.md", "term": "vendorx", "line": 1, "column": 1}],
            )

    def test_normalizes_empty_and_duplicate_terms_deterministically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "sample.md").write_text("VendorX", encoding="utf-8")

            self.assertEqual(
                self.scan(temp_dir, ["", "VendorX", "vendorx", "  "]),
                [{"path": "sample.md", "term": "VendorX", "line": 1, "column": 1}],
            )

    def test_cli_returns_json_with_one_trailing_newline_and_match_exit_code(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "sample.md").write_text("VendorX", encoding="utf-8")

            result = self.run_cli("--root", temp_dir, "--forbid", "vendorx")

            self.assertEqual(result.returncode, 1)
            self.assertTrue(result.stdout.endswith("\n"))
            self.assertFalse(result.stdout.endswith("\n\n"))
            self.assertEqual(json.loads(result.stdout)[0]["path"], "sample.md")

    def test_cli_returns_zero_for_no_matches_and_controlled_root_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_cli("--root", temp_dir, "--forbid", "vendorx")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "[]\n")

        result = self.run_cli("--root", "/does/not/exist", "--forbid", "vendorx")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
