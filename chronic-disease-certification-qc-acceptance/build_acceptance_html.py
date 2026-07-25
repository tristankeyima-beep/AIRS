#!/usr/bin/env python3

import argparse
import errno
import html
import json
import os
import re
import stat
import sys
import tempfile
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
CASE_FIELDS = frozenset(
    {
        "id",
        "title",
        "mode",
        "category",
        "priority",
        "inputKinds",
        "objective",
        "preconditions",
        "inputs",
        "steps",
        "expectedOutcome",
        "mustContain",
        "mustNotContain",
        "acceptanceChecks",
        "notes",
    }
)
INPUT_FIELDS = frozenset({"name", "format", "content"})
STEP_FIELDS = frozenset({"actor", "action", "expected"})
MODES = frozenset({"mode1", "mode2", "gate", "safety"})
PRIORITIES = frozenset({"P0", "P1", "P2"})
EXPECTED_IDS = (
    tuple(f"M1-{number:03d}" for number in range(1, 13))
    + tuple(f"M2-{number:03d}" for number in range(1, 17))
    + tuple(f"GATE-{number:03d}" for number in range(1, 7))
    + tuple(f"SAFE-{number:03d}" for number in range(1, 7))
)
GENERATED_FILE = "慢特病认定标准与审核质控-验收测试用例.html"
VERSION_PATTERN = re.compile(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}\.[0-9]+")
TEXT_FIELDS = ("catalogVersion", "title", "description", "generatedFile")
CASE_TEXT_FIELDS = (
    "id",
    "title",
    "mode",
    "category",
    "priority",
    "objective",
    "expectedOutcome",
    "notes",
)
CASE_TEXT_LIST_FIELDS = (
    "inputKinds",
    "preconditions",
    "mustContain",
    "mustNotContain",
    "acceptanceChecks",
)
MAX_CATALOG_DEPTH = 64
SCRIPT_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_CATALOG = SCRIPT_DIRECTORY / "acceptance-cases.json"
DEFAULT_OUTPUT = SCRIPT_DIRECTORY / GENERATED_FILE


class CatalogError(ValueError):
    pass


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        del message
        self.exit(2, "catalog_error\n")


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError("duplicate_json_key")
        result[key] = value
    return result


def _validate_root_contract(catalog):
    if type(catalog) is not dict:
        raise CatalogError("catalog_root_not_object")
    if frozenset(catalog) != ROOT_FIELDS:
        raise CatalogError("catalog_root_fields_error")
    for field in TEXT_FIELDS:
        value = catalog[field]
        if type(value) is not str or not value.strip():
            raise CatalogError("catalog_text_field_error")
    if not VERSION_PATTERN.fullmatch(catalog["catalogVersion"]):
        raise CatalogError("catalog_version_error")
    if catalog["generatedFile"] != GENERATED_FILE:
        raise CatalogError("catalog_generated_file_error")
    if type(catalog["cases"]) is not list:
        raise CatalogError("catalog_cases_error")


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
    except CatalogError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError):
        raise CatalogError("catalog_json_error") from None

    _validate_root_contract(catalog)
    return catalog


def _ensure_json_serializable(value):
    try:
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise CatalogError("catalog_json_value_error") from None


def _ensure_depth_limit(value):
    stack = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > MAX_CATALOG_DEPTH:
            raise CatalogError("catalog_depth_error")
        if type(current) is dict:
            stack.extend((item, depth + 1) for item in current.values())
        elif type(current) is list:
            stack.extend((item, depth + 1) for item in current)


def _require_non_empty_text(value):
    if type(value) is not str or not value.strip():
        raise CatalogError("catalog_case_value_error")


def _require_non_empty_text_list(value):
    if type(value) is not list or not value:
        raise CatalogError("catalog_case_list_error")
    for item in value:
        _require_non_empty_text(item)


def _iter_text_values(value):
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is str:
            yield current
        elif type(current) is dict:
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)


def _validate_forbidden_terms(catalog, forbidden_terms):
    try:
        terms = tuple(forbidden_terms)
    except TypeError:
        raise CatalogError("catalog_forbidden_terms_error") from None
    folded_terms = []
    for term in terms:
        if type(term) is not str or not term:
            raise CatalogError("catalog_forbidden_terms_error")
        folded_terms.append(term.casefold())
    if not folded_terms:
        return
    for text in _iter_text_values(catalog):
        folded_text = text.casefold()
        if any(term in folded_text for term in folded_terms):
            raise CatalogError("catalog_forbidden_term_error")


def validate_catalog(catalog, forbidden_terms=()):
    _ensure_json_serializable(catalog)
    _ensure_depth_limit(catalog)
    _validate_root_contract(catalog)

    cases = catalog["cases"]
    if len(cases) != len(EXPECTED_IDS):
        raise CatalogError("catalog_case_count_error")

    actual_ids = []
    for case in cases:
        if type(case) is not dict or frozenset(case) != CASE_FIELDS:
            raise CatalogError("catalog_case_fields_error")
        for field in CASE_TEXT_FIELDS:
            _require_non_empty_text(case[field])
        for field in CASE_TEXT_LIST_FIELDS:
            _require_non_empty_text_list(case[field])
        if case["mode"] not in MODES:
            raise CatalogError("catalog_case_mode_error")
        if case["priority"] not in PRIORITIES:
            raise CatalogError("catalog_case_priority_error")

        inputs = case["inputs"]
        if type(inputs) is not list or not inputs:
            raise CatalogError("catalog_case_inputs_error")
        for item in inputs:
            if type(item) is not dict or frozenset(item) != INPUT_FIELDS:
                raise CatalogError("catalog_input_fields_error")
            for field in INPUT_FIELDS:
                _require_non_empty_text(item[field])

        steps = case["steps"]
        if type(steps) is not list or not steps:
            raise CatalogError("catalog_case_steps_error")
        for step in steps:
            if type(step) is not dict or frozenset(step) != STEP_FIELDS:
                raise CatalogError("catalog_step_fields_error")
            for field in STEP_FIELDS:
                _require_non_empty_text(step[field])
        actual_ids.append(case["id"])

    if tuple(actual_ids) != EXPECTED_IDS:
        raise CatalogError("catalog_case_ids_error")
    _validate_forbidden_terms(catalog, forbidden_terms)
    return catalog


def safe_json_for_script(value):
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise CatalogError("catalog_json_value_error") from None
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _html_text(value):
    return (
        html.escape(value, quote=True)
        .replace("/", "&#x2F;")
        .replace("\u2028", "&#8232;")
        .replace("\u2029", "&#8233;")
    )


def _render_text_list(title, values):
    items = "".join(f"<li>{_html_text(value)}</li>" for value in values)
    return f"<section><h4>{title}</h4><ul>{items}</ul></section>"


def _render_case(case):
    parts = [
        '<article class="acceptance-case">',
        "<header>",
        f"<p class=\"case-id\">{_html_text(case['id'])}</p>",
        f"<h2>{_html_text(case['title'])}</h2>",
        '<p class="case-meta">',
        f"模式：{_html_text(case['mode'])} · ",
        f"优先级：{_html_text(case['priority'])} · ",
        f"分类：{_html_text(case['category'])}",
        "</p>",
        "</header>",
        f"<section><h3>目标</h3><p>{_html_text(case['objective'])}</p></section>",
        _render_text_list("输入类型", case["inputKinds"]),
        _render_text_list("前置条件", case["preconditions"]),
        "<section><h3>输入</h3>",
    ]
    for item in case["inputs"]:
        parts.extend(
            (
                '<div class="case-input">',
                f"<h4>{_html_text(item['name'])}</h4>",
                f"<p>格式：{_html_text(item['format'])}</p>",
                f"<pre>{_html_text(item['content'])}</pre>",
                "</div>",
            )
        )
    parts.extend(("</section>", "<section><h3>步骤</h3><ol>"))
    for step in case["steps"]:
        parts.extend(
            (
                "<li>",
                f"<p><strong>{_html_text(step['actor'])}</strong>："
                f"{_html_text(step['action'])}</p>",
                f"<p>预期：{_html_text(step['expected'])}</p>",
                "</li>",
            )
        )
    parts.extend(
        (
            "</ol></section>",
            "<section><h3>预期结果</h3>",
            f"<p>{_html_text(case['expectedOutcome'])}</p></section>",
            _render_text_list("必须包含", case["mustContain"]),
            _render_text_list("不得包含", case["mustNotContain"]),
            _render_text_list("验收项", case["acceptanceChecks"]),
            f"<section><h3>备注</h3><p>{_html_text(case['notes'])}</p></section>",
            "</article>",
        )
    )
    return "".join(parts)


def render_acceptance_html(catalog, forbidden_terms=()):
    validate_catalog(catalog, forbidden_terms=forbidden_terms)
    catalog_json = safe_json_for_script(catalog).replace("/", "\\/")
    cases_html = "\n".join(_render_case(case) for case in catalog["cases"])
    title = _html_text(catalog["title"])
    description = _html_text(catalog["description"])
    version = _html_text(catalog["catalogVersion"])
    count = len(catalog["cases"])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: light; font-family: system-ui, sans-serif; background: #f5f7fa; color: #172033; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; }}
main {{ width: min(1080px, calc(100% - 32px)); margin: 0 auto; padding: 40px 0 64px; }}
.catalog-header {{ background: #17324d; color: #fff; border-radius: 16px; padding: 28px; margin-bottom: 24px; }}
.catalog-header h1 {{ margin: 0 0 12px; font-size: clamp(1.55rem, 4vw, 2.35rem); }}
.catalog-header p {{ margin: 6px 0 0; line-height: 1.65; }}
.acceptance-case {{ background: #fff; border: 1px solid #d9e1ea; border-radius: 14px; margin: 18px 0; padding: 24px; box-shadow: 0 3px 14px rgba(23, 50, 77, .06); }}
.acceptance-case h2 {{ margin: 4px 0 8px; font-size: 1.35rem; }}
.acceptance-case h3 {{ margin: 22px 0 8px; font-size: 1.05rem; }}
.acceptance-case h4 {{ margin: 14px 0 6px; font-size: .95rem; }}
.acceptance-case p, .acceptance-case li {{ line-height: 1.7; }}
.case-id {{ color: #0b6b68; font-weight: 750; letter-spacing: .04em; margin: 0; }}
.case-meta {{ color: #536579; margin: 0; }}
pre {{ margin: 10px 0; padding: 14px; background: #f2f5f8; border-radius: 8px; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.55; }}
ul, ol {{ padding-left: 1.45rem; }}
@media print {{
  :root {{ background: #fff; }}
  main {{ width: 100%; padding: 0; }}
  .catalog-header {{ color: #000; background: #fff; border: 1px solid #999; }}
  .acceptance-case {{ break-inside: avoid; box-shadow: none; }}
}}
</style>
</head>
<body>
<main>
<header class="catalog-header">
<h1>{title}</h1>
<p>{description}</p>
<p>共 {count} 条 · 版本 {version}</p>
</header>
<section aria-label="验收测试用例">
{cases_html}
</section>
</main>
<script id="catalog-data" type="application/json">{catalog_json}</script>
<script>
"use strict";
const acceptanceCatalog = JSON.parse(document.getElementById("catalog-data").textContent);
Object.defineProperty(window, "acceptanceCatalog", {{
  value: acceptanceCatalog,
  writable: false,
  configurable: false
}});
</script>
</body>
</html>
"""


def _same_path_or_alias(destination, source):
    try:
        if destination.resolve(strict=False) == source.resolve(strict=False):
            return True
    except (OSError, RuntimeError):
        raise CatalogError("output_path_check_error") from None
    if not os.path.lexists(destination) or not os.path.lexists(source):
        return False
    try:
        return os.path.samefile(destination, source)
    except OSError:
        raise CatalogError("output_path_check_error") from None


def _source_path_tuple(source_paths):
    if source_paths is None:
        return ()
    if isinstance(source_paths, (str, bytes, os.PathLike)):
        return (source_paths,)
    try:
        return tuple(source_paths)
    except TypeError:
        raise CatalogError("output_source_paths_error") from None


def _destination_mode(destination):
    try:
        destination_stat = destination.stat(follow_symlinks=False)
    except FileNotFoundError:
        return 0o644
    except OSError:
        raise CatalogError("output_path_check_error") from None
    if not stat.S_ISREG(destination_stat.st_mode):
        raise CatalogError("output_not_regular")
    return stat.S_IMODE(destination_stat.st_mode)


def _directory_fsync_is_unsupported(error):
    unsupported = {
        errno.EINVAL,
        getattr(errno, "ENOSYS", -1),
        getattr(errno, "ENOTSUP", -1),
        getattr(errno, "EOPNOTSUPP", -1),
    }
    if error.errno in unsupported:
        return True
    return os.name == "nt" and error.errno in {errno.EACCES, errno.EPERM}


def _fsync_directory(directory):
    flags = os.O_RDONLY
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = None
    try:
        try:
            descriptor = os.open(directory, flags)
        except OSError as error:
            if _directory_fsync_is_unsupported(error):
                return
            raise CatalogError("output_directory_sync_error") from None
        try:
            os.fsync(descriptor)
        except OSError as error:
            if not _directory_fsync_is_unsupported(error):
                raise CatalogError("output_directory_sync_error") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                raise CatalogError("output_directory_sync_error") from None


def write_text_atomically(destination, text, source_paths=()):
    try:
        destination = Path(destination)
    except TypeError:
        raise CatalogError("output_path_error") from None
    if type(text) is not str:
        raise CatalogError("output_text_error")
    if destination.is_symlink():
        raise CatalogError("output_symlink_forbidden")
    parent = destination.parent
    if not parent.is_dir():
        raise CatalogError("output_parent_missing")

    for source_path in _source_path_tuple(source_paths):
        try:
            source = Path(source_path)
        except TypeError:
            raise CatalogError("output_source_paths_error") from None
        if _same_path_or_alias(destination, source):
            raise CatalogError("output_input_alias_forbidden")

    target_mode = _destination_mode(destination)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.rstrip("\n") + "\n"
    file_descriptor = None
    temporary = None
    operation_error = None
    cleanup_error = False
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=parent,
        )
        temporary = Path(temporary_name)
        if hasattr(os, "fchmod"):
            os.fchmod(file_descriptor, 0o600)
        else:
            os.chmod(temporary, 0o600)
        handle = os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
            newline="\n",
        )
        file_descriptor = None
        with handle:
            handle.write(normalized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        temporary = None
        os.chmod(destination, target_mode)
        _fsync_directory(parent)
    except CatalogError as error:
        operation_error = error
    except (OSError, UnicodeError, TypeError, ValueError):
        operation_error = CatalogError("output_write_error")
    finally:
        if file_descriptor is not None:
            try:
                os.close(file_descriptor)
            except OSError:
                cleanup_error = True
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                cleanup_error = True
    if cleanup_error:
        raise CatalogError("output_cleanup_error")
    if operation_error is not None:
        raise operation_error from None


def _parse_args(argv=None):
    parser = _SafeArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--forbid", action="append", default=[])
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        rendered = render_acceptance_html(
            catalog,
            forbidden_terms=args.forbid,
        )
        write_text_atomically(
            args.output,
            rendered,
            source_paths=(args.catalog,),
        )
    except CatalogError:
        print("catalog_error", file=sys.stderr)
        return 1
    print("catalog_built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
