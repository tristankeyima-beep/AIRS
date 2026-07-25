#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path


ROOT_FIELDS = frozenset(
    {
        "catalogVersion",
        "title",
        "description",
        "generatedFile",
        "cases",
    }
)
GENERATED_FILE = "慢特病认定标准与审核质控-验收测试用例.html"
VERSION_PATTERN = re.compile(r"\d{4}\.\d{2}\.\d{2}\.\d+")
TEXT_FIELDS = ("catalogVersion", "title", "description", "generatedFile")


class CatalogError(ValueError):
    pass


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError("duplicate_json_key")
        result[key] = value
    return result


def load_catalog(path):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError:
        raise CatalogError("catalog_read_error") from None

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CatalogError("catalog_encoding_error") from None

    try:
        catalog = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError:
        raise CatalogError("catalog_json_error") from None

    if not isinstance(catalog, dict):
        raise CatalogError("catalog_root_not_object")
    if set(catalog) != ROOT_FIELDS:
        raise CatalogError("catalog_root_fields_error")
    for field in TEXT_FIELDS:
        value = catalog[field]
        if not isinstance(value, str) or not value:
            raise CatalogError(f"catalog_text_field_error:{field}")
    if not VERSION_PATTERN.fullmatch(catalog["catalogVersion"]):
        raise CatalogError("catalog_version_error")
    if catalog["generatedFile"] != GENERATED_FILE:
        raise CatalogError("catalog_generated_file_error")
    if not isinstance(catalog["cases"], list):
        raise CatalogError("catalog_cases_error")

    return catalog


def _parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    try:
        load_catalog(args.catalog)
    except CatalogError:
        print("catalog_error", file=sys.stderr)
        return 1
    print("catalog_valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
