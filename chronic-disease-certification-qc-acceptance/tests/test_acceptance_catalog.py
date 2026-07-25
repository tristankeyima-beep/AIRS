import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "acceptance-cases.json"
BUILDER = ROOT / "build_acceptance_html.py"

EXPECTED_GENERATED_FILE = "慢特病认定标准与审核质控-验收测试用例.html"
SENSITIVE_DUPLICATE_KEY = "敏感业务字段_患者身份证号_DO_NOT_ECHO"
VALID_CATALOG = {
    "catalogVersion": "2026.07.25.1",
    "title": "门诊慢特病认定标准与智能审核质控验收测试用例",
    "description": "模式1、模式2、交互关口和安全产物的离线人工验收用例集",
    "generatedFile": EXPECTED_GENERATED_FILE,
    "cases": [],
}


@pytest.fixture(scope="module")
def builder_module():
    assert BUILDER.is_file(), f"missing builder: {BUILDER.name}"
    spec = importlib.util.spec_from_file_location("build_acceptance_html", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_catalog(tmp_path, value):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def test_repository_catalog_has_exact_initial_content():
    expected = (
        "{\n"
        '  "catalogVersion": "2026.07.25.1",\n'
        '  "title": "门诊慢特病认定标准与智能审核质控验收测试用例",\n'
        '  "description": "模式1、模式2、交互关口和安全产物的离线人工验收用例集",\n'
        f'  "generatedFile": "{EXPECTED_GENERATED_FILE}",\n'
        '  "cases": []\n'
        "}\n"
    )
    assert CATALOG.is_file(), f"missing catalog: {CATALOG.name}"
    assert CATALOG.read_bytes() == expected.encode("utf-8")


def test_valid_root_contract(builder_module, tmp_path):
    loaded = builder_module.load_catalog(write_catalog(tmp_path, VALID_CATALOG))

    assert loaded == VALID_CATALOG
    assert set(loaded) == builder_module.ROOT_FIELDS
    assert isinstance(loaded["cases"], list)


def test_duplicate_key_is_rejected_at_any_depth(builder_module, tmp_path):
    path = tmp_path / "catalog.json"
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
        """.replace("__SENSITIVE_DUPLICATE_KEY__", SENSITIVE_DUPLICATE_KEY),
        encoding="utf-8",
    )

    with pytest.raises(builder_module.CatalogError) as caught:
        builder_module.load_catalog(path)

    assert str(caught.value) == "duplicate_json_key"
    assert SENSITIVE_DUPLICATE_KEY not in str(caught.value)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"unexpected": "private-business-content"}),
        lambda value: value.pop("title"),
    ],
    ids=["unknown-field", "missing-field"],
)
def test_root_fields_must_be_exact(builder_module, tmp_path, mutate):
    value = dict(VALID_CATALOG)
    mutate(value)

    with pytest.raises(builder_module.CatalogError) as caught:
        builder_module.load_catalog(write_catalog(tmp_path, value))

    assert "private-business-content" not in str(caught.value)


def test_cases_must_be_an_array(builder_module, tmp_path):
    value = dict(VALID_CATALOG, cases={"content": "private-business-content"})

    with pytest.raises(builder_module.CatalogError) as caught:
        builder_module.load_catalog(write_catalog(tmp_path, value))

    assert "private-business-content" not in str(caught.value)


@pytest.mark.parametrize(
    "version",
    ["", "2026.7.25.1", "v2026.07.25.1", "2026.07.25"],
)
def test_catalog_version_must_match_contract(
    builder_module,
    tmp_path,
    version,
):
    value = dict(VALID_CATALOG, catalogVersion=version)

    with pytest.raises(builder_module.CatalogError) as caught:
        builder_module.load_catalog(write_catalog(tmp_path, value))

    if version:
        assert version not in str(caught.value)


def test_generated_file_must_match_contract(builder_module, tmp_path):
    wrong_name = "private-business-content.html"
    value = dict(VALID_CATALOG, generatedFile=wrong_name)

    with pytest.raises(builder_module.CatalogError) as caught:
        builder_module.load_catalog(write_catalog(tmp_path, value))

    assert wrong_name not in str(caught.value)


@pytest.mark.parametrize("field", ["title", "description", "generatedFile"])
def test_required_text_fields_must_be_non_empty_strings(
    builder_module,
    tmp_path,
    field,
):
    value = dict(VALID_CATALOG)
    value[field] = [] if field == "description" else ""

    with pytest.raises(builder_module.CatalogError):
        builder_module.load_catalog(write_catalog(tmp_path, value))


def test_invalid_utf8_is_a_controlled_error(builder_module, tmp_path):
    path = tmp_path / "catalog.json"
    path.write_bytes(b"\xff\xfeprivate-business-content")

    with pytest.raises(builder_module.CatalogError) as caught:
        builder_module.load_catalog(path)

    assert "private-business-content" not in str(caught.value)


def test_invalid_json_is_a_controlled_error_without_echo(
    builder_module,
    tmp_path,
):
    path = tmp_path / "catalog.json"
    path.write_text('{"title": "private-business-content"', encoding="utf-8")

    with pytest.raises(builder_module.CatalogError) as caught:
        builder_module.load_catalog(path)

    assert "private-business-content" not in str(caught.value)


def test_missing_file_is_a_controlled_error(builder_module, tmp_path):
    missing = tmp_path / "private-business-content.json"

    with pytest.raises(builder_module.CatalogError) as caught:
        builder_module.load_catalog(missing)

    assert "private-business-content" not in str(caught.value)


def test_cli_success(builder_module):
    del builder_module
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--catalog", str(CATALOG)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "catalog_valid"
    assert result.stderr == ""


def test_cli_catalog_error_is_generic_and_has_no_traceback(
    builder_module,
    tmp_path,
):
    del builder_module
    invalid = tmp_path / "private-business-content.json"
    invalid.write_text("private-business-content", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(BUILDER), "--catalog", str(invalid)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "catalog_error"
    assert "Traceback" not in result.stderr
    assert "private-business-content" not in result.stderr


def test_cli_duplicate_key_error_does_not_echo_sensitive_key(
    builder_module,
    tmp_path,
):
    del builder_module
    invalid = tmp_path / "duplicate.json"
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
        """.replace("__SENSITIVE_DUPLICATE_KEY__", SENSITIVE_DUPLICATE_KEY),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(BUILDER), "--catalog", str(invalid)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "catalog_error"
    assert "Traceback" not in result.stderr
    assert SENSITIVE_DUPLICATE_KEY not in result.stdout
    assert SENSITIVE_DUPLICATE_KEY not in result.stderr


def test_cli_argument_error_exits_two_without_traceback(builder_module):
    del builder_module
    result = subprocess.run(
        [sys.executable, str(BUILDER)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
