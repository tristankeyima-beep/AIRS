import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "acceptance-cases.json"
BUILDER = ROOT / "build_acceptance_html.py"

EXPECTED_GENERATED_FILE = "慢特病认定标准与审核质控-验收测试用例.html"
EXPECTED_METADATA = {
    "catalogVersion": "2026.07.25.1",
    "title": "门诊慢特病认定标准与智能审核质控验收测试用例",
    "description": "模式1、模式2、交互关口和安全产物的离线人工验收用例集",
    "generatedFile": EXPECTED_GENERATED_FILE,
}
SENSITIVE_DUPLICATE_KEY = "敏感业务字段_患者身份证号_DO_NOT_ECHO"
SENSITIVE_RECURSIVE_VALUE = "敏感业务内容_患者病历_DO_NOT_ECHO"
VALID_CATALOG = {**EXPECTED_METADATA, "cases": []}


def load_builder_module():
    if not BUILDER.is_file():
        raise AssertionError(f"missing builder: {BUILDER.name}")
    spec = importlib.util.spec_from_file_location("build_acceptance_html", BUILDER)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER_MODULE = load_builder_module()


class AcceptanceCatalogTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self._temp_dir.name)

    def tearDown(self):
        self._temp_dir.cleanup()

    def write_catalog(self, value):
        path = self.temp_path / "catalog.json"
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def run_cli(self, catalog=None):
        command = [sys.executable, str(BUILDER)]
        if catalog is not None:
            command.extend(["--catalog", str(catalog)])
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_repository_catalog_locks_metadata_and_list_contract(self):
        loaded = BUILDER_MODULE.load_catalog(CATALOG)

        self.assertEqual(
            {field: loaded[field] for field in EXPECTED_METADATA},
            EXPECTED_METADATA,
        )
        self.assertIsInstance(loaded["cases"], list)

    def test_valid_root_contract(self):
        loaded = BUILDER_MODULE.load_catalog(
            self.write_catalog(VALID_CATALOG)
        )

        self.assertEqual(loaded, VALID_CATALOG)
        self.assertEqual(set(loaded), BUILDER_MODULE.ROOT_FIELDS)
        self.assertIsInstance(loaded["cases"], list)

    def test_duplicate_key_is_rejected_at_any_depth(self):
        path = self.temp_path / "catalog.json"
        path.write_text(
            """
            {
              "catalogVersion": "2026.07.25.1",
              "title": "title",
              "description": "description",
              "generatedFile": "慢特病认定标准与审核质控-验收测试用例.html",
              "cases": [
                {
                  "steps": [
                    {
                      "__SENSITIVE_DUPLICATE_KEY__": "one",
                      "__SENSITIVE_DUPLICATE_KEY__": "two"
                    }
                  ]
                }
              ]
            }
            """.replace(
                "__SENSITIVE_DUPLICATE_KEY__",
                SENSITIVE_DUPLICATE_KEY,
            ),
            encoding="utf-8",
        )

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(path)

        self.assertEqual(str(caught.exception), "duplicate_json_key")
        self.assertNotIn(SENSITIVE_DUPLICATE_KEY, str(caught.exception))

    def test_root_fields_must_be_exact(self):
        values = []
        with_unknown = dict(VALID_CATALOG)
        with_unknown["unexpected"] = "private-business-content"
        values.append(("unknown-field", with_unknown))
        without_title = dict(VALID_CATALOG)
        without_title.pop("title")
        values.append(("missing-field", without_title))

        for label, value in values:
            with self.subTest(label=label):
                with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                    BUILDER_MODULE.load_catalog(self.write_catalog(value))
                self.assertNotIn(
                    "private-business-content",
                    str(caught.exception),
                )

    def test_cases_must_be_an_array(self):
        value = dict(
            VALID_CATALOG,
            cases={"content": "private-business-content"},
        )

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(self.write_catalog(value))

        self.assertNotIn("private-business-content", str(caught.exception))

    def test_catalog_version_must_use_ascii_contract(self):
        versions = [
            "",
            "2026.7.25.1",
            "v2026.07.25.1",
            "2026.07.25",
            "２０２６.０７.２５.１",
        ]
        for version in versions:
            with self.subTest(version=version):
                value = dict(VALID_CATALOG, catalogVersion=version)
                with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                    BUILDER_MODULE.load_catalog(self.write_catalog(value))
                if version:
                    self.assertNotIn(version, str(caught.exception))

    def test_generated_file_must_match_contract(self):
        wrong_name = "private-business-content.html"
        value = dict(VALID_CATALOG, generatedFile=wrong_name)

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(self.write_catalog(value))

        self.assertNotIn(wrong_name, str(caught.exception))

    def test_required_text_fields_must_be_non_empty_strings(self):
        invalid_values = {
            "title": "",
            "description": [],
            "generatedFile": "",
        }
        for field, invalid_value in invalid_values.items():
            with self.subTest(field=field):
                value = dict(VALID_CATALOG)
                value[field] = invalid_value
                with self.assertRaises(BUILDER_MODULE.CatalogError):
                    BUILDER_MODULE.load_catalog(self.write_catalog(value))

    def test_invalid_utf8_is_a_controlled_error(self):
        path = self.temp_path / "catalog.json"
        path.write_bytes(b"\xff\xfeprivate-business-content")

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(path)

        self.assertNotIn(
            "private-business-content",
            str(caught.exception),
        )

    def test_invalid_json_is_a_controlled_error_without_echo(self):
        path = self.temp_path / "catalog.json"
        path.write_text(
            '{"title": "private-business-content"',
            encoding="utf-8",
        )

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(path)

        self.assertEqual(str(caught.exception), "catalog_json_error")
        self.assertNotIn(
            "private-business-content",
            str(caught.exception),
        )

    def test_deeply_nested_json_is_a_controlled_error_without_echo(self):
        path = self.temp_path / "catalog.json"
        nested = (
            "[" * 10_000
            + json.dumps(SENSITIVE_RECURSIVE_VALUE, ensure_ascii=False)
            + "]" * 10_000
        )
        path.write_text(nested, encoding="utf-8")

        try:
            BUILDER_MODULE.load_catalog(path)
        except BUILDER_MODULE.CatalogError as error:
            caught = error
        except RecursionError:
            self.fail("deeply nested JSON leaked RecursionError")
        else:
            self.fail("deeply nested JSON was accepted")

        self.assertEqual(str(caught), "catalog_json_error")
        self.assertNotIn(SENSITIVE_RECURSIVE_VALUE, str(caught))

    def test_missing_file_is_a_controlled_error(self):
        missing = self.temp_path / "private-business-content.json"

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(missing)

        self.assertNotIn(
            "private-business-content",
            str(caught.exception),
        )

    def test_cli_success(self):
        result = self.run_cli(CATALOG)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "catalog_valid")
        self.assertEqual(result.stderr, "")

    def test_cli_catalog_error_is_generic_and_has_no_traceback(self):
        invalid = self.temp_path / "private-business-content.json"
        invalid.write_text("private-business-content", encoding="utf-8")

        result = self.run_cli(invalid)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "catalog_error")
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("private-business-content", result.stderr)

    def test_cli_duplicate_key_error_does_not_echo_sensitive_key(self):
        invalid = self.temp_path / "duplicate.json"
        invalid.write_text(
            """
            {
              "catalogVersion": "2026.07.25.1",
              "title": "title",
              "description": "description",
              "generatedFile": "慢特病认定标准与审核质控-验收测试用例.html",
              "cases": [
                {
                  "__SENSITIVE_DUPLICATE_KEY__": "one",
                  "__SENSITIVE_DUPLICATE_KEY__": "two"
                }
              ]
            }
            """.replace(
                "__SENSITIVE_DUPLICATE_KEY__",
                SENSITIVE_DUPLICATE_KEY,
            ),
            encoding="utf-8",
        )

        result = self.run_cli(invalid)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "catalog_error")
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn(SENSITIVE_DUPLICATE_KEY, result.stdout)
        self.assertNotIn(SENSITIVE_DUPLICATE_KEY, result.stderr)

    def test_cli_deeply_nested_json_is_generic_without_traceback(self):
        invalid = self.temp_path / "recursive.json"
        nested = (
            "[" * 10_000
            + json.dumps(SENSITIVE_RECURSIVE_VALUE, ensure_ascii=False)
            + "]" * 10_000
        )
        invalid.write_text(nested, encoding="utf-8")

        result = self.run_cli(invalid)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "catalog_error")
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn(SENSITIVE_RECURSIVE_VALUE, result.stdout)
        self.assertNotIn(SENSITIVE_RECURSIVE_VALUE, result.stderr)

    def test_cli_argument_error_exits_two_without_traceback(self):
        result = self.run_cli()

        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
