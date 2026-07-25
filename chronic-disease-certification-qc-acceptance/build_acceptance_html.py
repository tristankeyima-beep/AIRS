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
                f"<pre><code>{_html_text(item['content'])}</code></pre>",
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


CONSOLE_CSS = r"""
:root {
  color-scheme: light;
  --color-bg: #edf1f4;
  --color-surface: #ffffff;
  --color-surface-subtle: #f6f8fa;
  --color-surface-strong: #172a3a;
  --color-surface-strong-2: #20384b;
  --color-ink: #17232d;
  --color-muted: #60717e;
  --color-border: #ccd6dd;
  --color-border-strong: #91a2ad;
  --color-success: #087f6d;
  --color-success-soft: #e4f4f0;
  --color-warning: #b76012;
  --color-warning-soft: #fff0df;
  --color-danger: #b83a3a;
  --color-danger-soft: #fbe9e9;
  --color-not-run: #6c7881;
  --color-not-run-soft: #eef1f3;
  --color-on-strong: #f7fafb;
  --color-on-strong-muted: #d7e1e7;
  --color-strong-accent: #8bd5c9;
  --color-strong-border: #4a6477;
  --color-strong-control: #7e93a2;
  --color-success-hover: #066b5d;
  --color-success-border-hover: #0aa68d;
  --color-code-bg: #eef2f4;
  --color-code-ink: #192630;
  --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: ui-monospace, "SFMono-Regular", Consolas, monospace;
  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-md: 1rem;
  --text-lg: 1.2rem;
  --text-xl: clamp(1.55rem, 3vw, 2.15rem);
  --line-body: 1.65;
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.5rem;
  --space-6: 2rem;
  --radius-sm: 0.35rem;
  --radius-md: 0.7rem;
  --radius-lg: 1rem;
  --shadow-card: 0 0.3rem 1.2rem rgba(23, 42, 58, 0.08);
  --focus-ring: 0 0 0 3px rgba(8, 127, 109, 0.28);
  --motion-fast: 160ms;
  --motion-reveal: 260ms;
}

* {
  box-sizing: border-box;
}

html {
  scroll-behavior: smooth;
}

body {
  margin: 0;
  min-width: 0;
  overflow-x: hidden;
  background: var(--color-bg);
  color: var(--color-ink);
  font-family: var(--font-sans);
  font-size: var(--text-md);
  line-height: var(--line-body);
}

button,
input,
select,
textarea {
  color: inherit;
  font: inherit;
}

button,
select,
input[type="search"] {
  min-height: 44px;
}

button {
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  cursor: pointer;
  font-weight: 700;
  transition: border-color var(--motion-fast), background-color var(--motion-fast), color var(--motion-fast), transform var(--motion-fast);
}

button:hover {
  border-color: var(--color-ink);
}

button:active {
  transform: translateY(1px);
}

:focus-visible {
  outline: 2px solid var(--color-success);
  outline-offset: 2px;
  box-shadow: var(--focus-ring);
}

.skip-link {
  position: fixed;
  z-index: 100;
  top: var(--space-3);
  left: var(--space-3);
  padding: var(--space-2) var(--space-4);
  background: var(--color-surface);
  color: var(--color-ink);
  border-radius: var(--radius-sm);
  transform: translateY(-180%);
}

.skip-link:focus {
  transform: translateY(0);
}

.visually-hidden {
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  padding: 0 !important;
  margin: -1px !important;
  overflow: hidden !important;
  clip: rect(0, 0, 0, 0) !important;
  white-space: nowrap !important;
  border: 0 !important;
}

.catalog-header {
  background: var(--color-surface-strong);
  color: var(--color-on-strong);
  border-bottom: 4px solid var(--color-success);
}

.header-inner,
main,
.page-footer {
  width: min(1440px, calc(100% - 32px));
  margin-inline: auto;
}

.header-inner {
  display: grid;
  gap: var(--space-5);
  padding-block: var(--space-6);
}

.eyebrow,
.case-id {
  margin: 0;
  color: var(--color-strong-accent);
  font-size: var(--text-xs);
  font-weight: 800;
  letter-spacing: 0.08em;
}

.catalog-header h1 {
  max-width: 24ch;
  margin: var(--space-1) 0 var(--space-2);
  font-size: var(--text-xl);
  line-height: 1.2;
}

.catalog-description {
  max-width: 76ch;
  margin: 0;
  color: var(--color-on-strong-muted);
}

.catalog-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: var(--space-4) 0 0;
  padding: 0;
  list-style: none;
}

.catalog-facts li {
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--color-strong-border);
  border-radius: 999px;
  color: var(--color-on-strong);
  font-size: var(--text-sm);
}

.action-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.action-bar button {
  padding: var(--space-2) var(--space-4);
  border-color: var(--color-strong-control);
  background: transparent;
  color: var(--color-on-strong);
}

.action-bar .primary-action {
  border-color: var(--color-success);
  background: var(--color-success);
  color: var(--color-on-strong);
}

.action-bar .primary-action:hover {
  border-color: var(--color-success-border-hover);
  background: var(--color-success-hover);
}

main {
  padding-block: var(--space-5) var(--space-6);
}

.summary-dashboard {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  margin-bottom: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-border);
  box-shadow: var(--shadow-card);
}

.metric {
  min-width: 0;
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface);
}

.metric dt {
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 700;
}

.metric dd {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 850;
}

.metric-passed dd {
  color: var(--color-success);
}

.metric-failed dd {
  color: var(--color-danger);
}

.metric-blocked dd {
  color: var(--color-warning);
}

.workspace-grid {
  display: grid;
  gap: var(--space-5);
  min-width: 0;
}

.filter-panel {
  align-self: start;
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.filter-panel h2,
.case-section-heading h2 {
  margin: 0;
  font-size: var(--text-lg);
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.filter-field {
  display: grid;
  flex: 1 1 12rem;
  gap: var(--space-1);
  min-width: 0;
}

.filter-field label {
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 800;
}

.filter-field input,
.filter-field select {
  width: 100%;
  min-width: 0;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
}

.clear-filter {
  width: 100%;
  margin-top: var(--space-4);
  padding-inline: var(--space-4);
}

.case-column {
  min-width: 0;
}

.case-section-heading {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.result-count {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
  font-weight: 700;
}

.case-list {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
}

.acceptance-case {
  min-width: 0;
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-surface-strong-2);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.acceptance-case.is-revealing {
  animation: case-reveal var(--motion-reveal) ease-out both;
}

@keyframes case-reveal {
  from {
    opacity: 0;
    transform: translateY(5px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.case-header {
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.case-header-top,
.case-meta,
.status-selector,
.input-heading {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.case-id {
  color: var(--color-surface-strong-2);
}

.risk-tag,
.case-meta span {
  padding: 0.15rem var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface-subtle);
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 700;
}

.case-header h2 {
  margin: var(--space-2) 0;
  font-size: var(--text-lg);
  line-height: 1.35;
}

.acceptance-case h3 {
  margin: var(--space-5) 0 var(--space-2);
  color: var(--color-surface-strong);
  font-size: var(--text-md);
}

.acceptance-case h4 {
  margin: var(--space-3) 0 var(--space-1);
  font-size: var(--text-sm);
}

.acceptance-case p {
  margin: var(--space-2) 0;
}

.acceptance-case ul {
  margin-block: var(--space-2);
  padding-left: 1.35rem;
}

.case-input {
  min-width: 0;
  margin-top: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-subtle);
}

.input-heading {
  justify-content: space-between;
}

.input-heading h4 {
  margin: 0;
}

.input-format {
  color: var(--color-muted);
  font-size: var(--text-sm);
}

.copy-button {
  min-height: 36px;
  padding-inline: var(--space-3);
  font-size: var(--text-sm);
}

pre {
  max-width: 100%;
  margin: var(--space-3) 0 0;
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-code-bg);
  color: var(--color-code-ink);
  line-height: 1.55;
  tab-size: 2;
}

code {
  display: block;
  min-width: max-content;
  padding: var(--space-3);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  white-space: pre;
}

.gate-timeline {
  position: relative;
  margin: var(--space-3) 0;
  padding: 0;
  list-style: none;
  counter-reset: gate-step;
}

.gate-timeline::before {
  position: absolute;
  top: 1rem;
  bottom: 1rem;
  left: 0.72rem;
  width: 2px;
  background: var(--color-border-strong);
  content: "";
}

.gate-step {
  position: relative;
  min-width: 0;
  margin: 0 0 var(--space-3);
  padding: var(--space-3) var(--space-3) var(--space-3) 2.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-subtle);
  counter-increment: gate-step;
}

.gate-step::before {
  position: absolute;
  z-index: 1;
  top: 0.78rem;
  left: 0.25rem;
  display: grid;
  width: 1.85rem;
  height: 1.85rem;
  place-items: center;
  border: 2px solid var(--color-surface-strong-2);
  border-radius: 50%;
  background: var(--color-surface);
  color: var(--color-surface-strong-2);
  content: counter(gate-step);
  font-size: var(--text-xs);
  font-weight: 850;
}

.gate-step.is-gate {
  border-left: 4px solid var(--color-warning);
  background: var(--color-warning-soft);
}

.gate-step.is-gate::before {
  border-color: var(--color-warning);
  color: var(--color-warning);
}

.step-label {
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 800;
}

.step-expected {
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-border);
}

.result-editor {
  margin-top: var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-surface-subtle);
}

.result-editor h3 {
  margin-top: 0;
}

.status-selector {
  margin-bottom: var(--space-4);
}

.status-button {
  flex: 1 1 7rem;
  padding-inline: var(--space-3);
}

.status-button[aria-pressed="true"][data-status="not-run"] {
  border-color: var(--color-not-run);
  background: var(--color-not-run-soft);
  color: var(--color-not-run);
}

.status-button[aria-pressed="true"][data-status="passed"] {
  border-color: var(--color-success);
  background: var(--color-success-soft);
  color: var(--color-success);
}

.status-button[aria-pressed="true"][data-status="failed"] {
  border-color: var(--color-danger);
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.status-button[aria-pressed="true"][data-status="blocked"] {
  border-color: var(--color-warning);
  background: var(--color-warning-soft);
  color: var(--color-warning);
}

.result-field {
  display: grid;
  gap: var(--space-1);
  margin-top: var(--space-3);
}

.result-field label {
  font-size: var(--text-sm);
  font-weight: 800;
}

.result-field textarea {
  width: 100%;
  min-height: 7rem;
  resize: vertical;
  padding: var(--space-3);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  line-height: 1.55;
}

.notice {
  position: sticky;
  z-index: 10;
  bottom: var(--space-3);
  width: min(720px, calc(100% - 32px));
  margin: 0 auto var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-surface-strong);
  color: var(--color-on-strong);
  box-shadow: var(--shadow-card);
}

.notice[hidden],
.empty-state[hidden] {
  display: none;
}

.empty-state {
  padding: var(--space-6);
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  text-align: center;
}

.page-footer {
  padding-block: var(--space-4) var(--space-6);
  border-top: 1px solid var(--color-border);
  color: var(--color-muted);
  font-size: var(--text-sm);
}

@media (min-width: 1100px) {
  .header-inner {
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: end;
  }

  .summary-dashboard {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }

  .workspace-grid {
    grid-template-columns: 280px minmax(0, 1fr);
  }

  .filter-panel {
    position: sticky;
    top: var(--space-4);
  }

  .filter-form {
    display: grid;
  }
}

@media (min-width: 600px) and (max-width: 1099px) {
  .summary-dashboard {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .filter-form {
    flex-flow: row wrap;
  }
}

@media (max-width: 599px) {
  .header-inner,
  main,
  .page-footer {
    width: min(100% - 20px, 1440px);
  }

  .header-inner {
    padding-block: var(--space-5);
  }

  .action-bar,
  .action-bar button,
  .clear-filter,
  .status-selector,
  .status-button {
    width: 100%;
  }

  .acceptance-case {
    padding: var(--space-4);
  }

  .case-section-heading {
    align-items: start;
    flex-direction: column;
  }

  .input-heading {
    align-items: start;
    flex-direction: column;
  }

  .copy-button {
    width: 100%;
    min-height: 44px;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
  }
}

@media print {
  :root {
    --color-bg: #ffffff;
    --color-surface: #ffffff;
    --color-ink: #000000;
  }

  .skip-link,
  .interactive-controls,
  #case-filters,
  .copy-button,
  .status-selector,
  .result-editor,
  .notice,
  .empty-state {
    display: none !important;
  }

  .catalog-header {
    border: 1px solid #777777;
    background: #ffffff;
    color: #000000;
  }

  .catalog-description,
  .catalog-facts li,
  .eyebrow {
    color: #000000;
  }

  .catalog-facts li {
    border-color: #777777;
  }

  .header-inner,
  main,
  .page-footer {
    width: 100%;
  }

  .workspace-grid {
    display: block;
  }

  .acceptance-case {
    break-inside: avoid;
    margin-bottom: 12mm;
    border-color: #777777;
    box-shadow: none;
    animation: none;
  }

  pre {
    overflow: visible;
    white-space: pre-wrap;
  }

  code {
    min-width: 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
}
"""


CONSOLE_JS = r"""
"use strict";

const acceptanceCatalog = JSON.parse(document.getElementById("catalog-data").textContent);
Object.defineProperty(window, "acceptanceCatalog", {
  value: acceptanceCatalog,
  writable: false,
  configurable: false
});

const STATUS_VALUES = ["not-run", "passed", "failed", "blocked"];
const STATUS_LABELS = {
  "not-run": "未执行",
  "passed": "通过",
  "failed": "失败",
  "blocked": "阻塞"
};
const knownIds = new Set(acceptanceCatalog.cases.map((caseData) => caseData.id));
const storageKey = "chronic-disease-certification-qc-acceptance:" + acceptanceCatalog.catalogVersion;
const caseList = document.getElementById("case-list");
const resultCount = document.getElementById("result-count");
const notice = document.getElementById("page-notice");
const emptyState = document.getElementById("empty-state");
const filterControls = {
  query: document.getElementById("filter-query"),
  mode: document.getElementById("filter-mode"),
  category: document.getElementById("filter-category"),
  priority: document.getElementById("filter-priority"),
  inputKind: document.getElementById("filter-input-kind"),
  risk: document.getElementById("filter-risk"),
  status: document.getElementById("filter-status")
};
let results = createDefaultResults();
let noticeTimer = 0;
let isInitialRender = true;

function createDefaultResults() {
  const defaults = {};
  acceptanceCatalog.cases.forEach((caseData) => {
    defaults[caseData.id] = {
      status: "not-run",
      actual: "",
      notes: ""
    };
  });
  return defaults;
}

function createElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) {
    element.className = className;
  }
  if (text !== undefined) {
    element.textContent = text;
  }
  return element;
}

function showNotice(message) {
  window.clearTimeout(noticeTimer);
  notice.textContent = message;
  notice.hidden = false;
  noticeTimer = window.setTimeout(() => {
    notice.hidden = true;
  }, 5000);
}

function exactKeys(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const keys = Object.keys(value).sort();
  return (
    keys.length === expected.length &&
    keys.every((key, index) => key === expected[index])
  );
}

function validateResultsDocument(value) {
  if (!exactKeys(value, ["results", "updatedAt", "version"])) {
    throw new Error("invalid-root");
  }
  if (
    value.version !== acceptanceCatalog.catalogVersion ||
    typeof value.updatedAt !== "string" ||
    !value.updatedAt
  ) {
    throw new Error("invalid-metadata");
  }
  if (
    !value.results ||
    typeof value.results !== "object" ||
    Array.isArray(value.results)
  ) {
    throw new Error("invalid-results");
  }
  const ids = Object.keys(value.results);
  if (
    ids.length !== knownIds.size ||
    ids.some((id) => !knownIds.has(id))
  ) {
    throw new Error("invalid-ids");
  }
  const candidateResults = {};
  ids.forEach((id) => {
    const item = value.results[id];
    if (
      !exactKeys(item, ["actual", "notes", "status"]) ||
      !STATUS_VALUES.includes(item.status) ||
      typeof item.actual !== "string" ||
      typeof item.notes !== "string"
    ) {
      throw new Error("invalid-result");
    }
    candidateResults[id] = {
      status: item.status,
      actual: item.actual,
      notes: item.notes
    };
  });
  return candidateResults;
}

function serializeResults() {
  const version = acceptanceCatalog.catalogVersion;
  const updatedAt = new Date().toISOString();
  const exportedResults = {};
  acceptanceCatalog.cases.forEach((caseData) => {
    const item = results[caseData.id];
    exportedResults[caseData.id] = {
      status: item.status,
      actual: item.actual,
      notes: item.notes
    };
  });
  return stringifyResultsDocument(version, updatedAt, exportedResults);
}

function stringifyResultsDocument(version, updatedAt, results) {
  return JSON.stringify({ version, updatedAt, results });
}

function persistResults() {
  try {
    localStorage.setItem(storageKey, serializeResults());
  } catch (error) {
    showNotice("本地记录暂时无法保存；当前页面中的内容仍会保留。");
  }
}

function loadSavedResults() {
  let saved;
  try {
    saved = localStorage.getItem(storageKey);
  } catch (error) {
    showNotice("无法读取本地记录，已使用未执行状态继续。");
    return;
  }
  if (!saved) {
    return;
  }
  try {
    const candidateResults = validateResultsDocument(JSON.parse(saved));
    results = candidateResults;
  } catch (error) {
    showNotice("已忽略损坏或不兼容的本地记录；当前页面内容未被清空。");
  }
}

function appendTextList(parent, title, values) {
  const section = createElement("section");
  section.append(createElement("h3", "", title));
  const list = createElement("ul");
  values.forEach((value) => {
    list.append(createElement("li", "", value));
  });
  section.append(list);
  parent.append(section);
}

function deriveRisk(caseData) {
  const riskText = [
    caseData.title,
    caseData.objective,
    caseData.expectedOutcome,
    ...caseData.mustContain
  ].join(" ");
  if (riskText.includes("错误放行风险")) {
    return "错误放行风险";
  }
  if (riskText.includes("错误拒绝风险")) {
    return "错误拒绝风险";
  }
  return "其他";
}

function isGateStep(step) {
  const text = [step.action, step.expected].join(" ");
  return ["确认", "同意", "不得", "暂停", "阻止", "拒绝", "等待", "关口"]
    .some((marker) => text.includes(marker));
}

async function copyInput(content, codeElement) {
  try {
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      throw new Error("clipboard-unavailable");
    }
    await navigator.clipboard.writeText(content);
    showNotice("输入内容已复制。");
    return;
  } catch (error) {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(codeElement);
    if (selection) {
      selection.removeAllRanges();
      selection.addRange(range);
    }
    showNotice("自动复制不可用，已选中对应代码内容，请手动复制。");
  }
}

function appendInputs(parent, caseData) {
  const section = createElement("section");
  section.append(createElement("h3", "", "输入"));
  caseData.inputs.forEach((input, index) => {
    const wrapper = createElement("div", "case-input");
    const heading = createElement("div", "input-heading");
    heading.append(createElement("h4", "", input.name));
    const copyButton = createElement("button", "copy-button", "复制输入");
    copyButton.type = "button";
    copyButton.setAttribute(
      "aria-label",
      "复制 " + caseData.id + " 的输入 " + (index + 1)
    );
    const pre = createElement("pre");
    const code = createElement("code");
    code.textContent = input.content;
    copyButton.addEventListener("click", () => {
      copyInput(input.content, code);
    });
    heading.append(copyButton);
    wrapper.append(heading);
    wrapper.append(createElement("p", "input-format", "格式：" + input.format));
    pre.append(code);
    wrapper.append(pre);
    section.append(wrapper);
  });
  parent.append(section);
}

function appendTimeline(parent, caseData) {
  const section = createElement("section");
  section.append(createElement("h3", "", "关口时间线"));
  const timeline = createElement("ol", "gate-timeline");
  caseData.steps.forEach((step) => {
    const gate = isGateStep(step);
    const item = createElement("li", "gate-step" + (gate ? " is-gate" : ""));
    item.append(
      createElement("p", "step-label", gate ? "关键确认 / 阻断点" : "操作节点")
    );
    const action = createElement("p");
    const actor = createElement("strong", "", step.actor + "：");
    action.append(actor, document.createTextNode(step.action));
    item.append(action);
    item.append(createElement("p", "step-expected", "预期：" + step.expected));
    timeline.append(item);
  });
  section.append(timeline);
  parent.append(section);
}

function setCaseStatus(caseData, status) {
  results[caseData.id].status = status;
  persistResults();
  updateDashboard();
  renderCases();
}

function appendResultEditor(parent, caseData) {
  const editor = createElement("section", "result-editor");
  editor.append(createElement("h3", "", "验收记录"));
  const statusGroup = createElement("div", "status-selector");
  statusGroup.setAttribute("role", "group");
  statusGroup.setAttribute("aria-label", caseData.id + " 验收状态");
  STATUS_VALUES.forEach((status) => {
    const button = createElement(
      "button",
      "status-button",
      STATUS_LABELS[status]
    );
    button.type = "button";
    button.dataset.status = status;
    button.setAttribute("aria-label", caseData.id + " 标记为" + STATUS_LABELS[status]);
    button.setAttribute(
      "aria-pressed",
      String(results[caseData.id].status === status)
    );
    button.addEventListener("click", () => {
      setCaseStatus(caseData, status);
    });
    statusGroup.append(button);
  });
  editor.append(statusGroup);

  [
    ["actual", "实际结果", "记录实际观察、输出或差异"],
    ["notes", "验收备注", "记录复现信息、阻塞原因或后续动作"]
  ].forEach(([field, labelText, placeholder]) => {
    const fieldWrapper = createElement("div", "result-field");
    const fieldId = caseData.id + "-" + field;
    const label = createElement("label", "", labelText);
    label.setAttribute("for", fieldId);
    const textarea = createElement("textarea");
    textarea.id = fieldId;
    textarea.name = field;
    textarea.value = results[caseData.id][field];
    textarea.placeholder = placeholder;
    textarea.setAttribute("aria-label", caseData.id + " " + labelText);
    textarea.addEventListener("input", () => {
      results[caseData.id][field] = textarea.value;
      persistResults();
      updateDashboard();
    });
    fieldWrapper.append(label, textarea);
    editor.append(fieldWrapper);
  });
  parent.append(editor);
}

function renderCase(caseData) {
  const article = createElement(
    "article",
    "acceptance-case" + (isInitialRender ? " is-revealing" : "")
  );
  article.setAttribute("data-case-id", caseData.id);
  article.setAttribute("data-status", results[caseData.id].status);

  const header = createElement("header", "case-header");
  const headerTop = createElement("div", "case-header-top");
  headerTop.append(createElement("p", "case-id", caseData.id));
  headerTop.append(createElement("span", "risk-tag", deriveRisk(caseData)));
  header.append(headerTop);
  header.append(createElement("h2", "", caseData.title));
  const meta = createElement("p", "case-meta");
  [caseData.mode, caseData.priority, caseData.category].forEach((value) => {
    meta.append(createElement("span", "", value));
  });
  header.append(meta);
  article.append(header);

  const objective = createElement("section");
  objective.append(createElement("h3", "", "目标"));
  objective.append(createElement("p", "", caseData.objective));
  article.append(objective);
  appendTextList(article, "输入类型", caseData.inputKinds);
  appendTextList(article, "前置条件", caseData.preconditions);
  appendInputs(article, caseData);
  appendTimeline(article, caseData);

  const expectedOutcome = createElement("section");
  expectedOutcome.append(createElement("h3", "", "预期结果"));
  expectedOutcome.append(createElement("p", "", caseData.expectedOutcome));
  article.append(expectedOutcome);
  appendTextList(article, "必须包含", caseData.mustContain);
  appendTextList(article, "不得包含", caseData.mustNotContain);
  appendTextList(article, "验收项", caseData.acceptanceChecks);

  const caseNotes = createElement("section");
  caseNotes.append(createElement("h3", "", "用例备注"));
  caseNotes.append(createElement("p", "", caseData.notes));
  article.append(caseNotes);
  appendResultEditor(article, caseData);
  return article;
}

function searchText(caseData) {
  return [
    caseData.id,
    caseData.title,
    caseData.objective,
    caseData.category,
    ...caseData.inputs.map((input) => input.content)
  ].join(" ").toLocaleLowerCase("zh-CN");
}

function matchesFilters(caseData) {
  const query = filterControls.query.value.trim().toLocaleLowerCase("zh-CN");
  const result = results[caseData.id];
  return (
    (!query || searchText(caseData).includes(query)) &&
    (filterControls.mode.value === "all" ||
      caseData.mode === filterControls.mode.value) &&
    (filterControls.category.value === "all" ||
      caseData.category === filterControls.category.value) &&
    (filterControls.priority.value === "all" ||
      caseData.priority === filterControls.priority.value) &&
    (filterControls.inputKind.value === "all" ||
      caseData.inputKinds.includes(filterControls.inputKind.value)) &&
    (filterControls.risk.value === "all" ||
      deriveRisk(caseData) === filterControls.risk.value) &&
    (filterControls.status.value === "all" ||
      result.status === filterControls.status.value)
  );
}

function renderCases() {
  const visibleCases = acceptanceCatalog.cases.filter(matchesFilters);
  const fragment = document.createDocumentFragment();
  visibleCases.forEach((caseData) => {
    fragment.append(renderCase(caseData));
  });
  caseList.replaceChildren(fragment);
  isInitialRender = false;
  resultCount.textContent =
    "当前显示 " + visibleCases.length + " / " +
    acceptanceCatalog.cases.length + " 条";
  emptyState.hidden = visibleCases.length !== 0;
}

function updateDashboard() {
  const counts = {
    "not-run": 0,
    "passed": 0,
    "failed": 0,
    "blocked": 0
  };
  acceptanceCatalog.cases.forEach((caseData) => {
    counts[results[caseData.id].status] += 1;
  });
  const completed = counts.passed + counts.failed + counts.blocked;
  const rate = acceptanceCatalog.cases.length
    ? Math.round((completed / acceptanceCatalog.cases.length) * 100)
    : 0;
  document.getElementById("metric-total").textContent =
    String(acceptanceCatalog.cases.length);
  document.getElementById("metric-passed").textContent = String(counts.passed);
  document.getElementById("metric-failed").textContent = String(counts.failed);
  document.getElementById("metric-blocked").textContent = String(counts.blocked);
  document.getElementById("metric-not-run").textContent = String(counts["not-run"]);
  document.getElementById("metric-rate").textContent = rate + "%";
}

function clearFilters() {
  Object.values(filterControls).forEach((control) => {
    control.value = control === filterControls.query ? "" : "all";
  });
  renderCases();
  filterControls.query.focus();
}

function exportResults() {
  const serialized = serializeResults();
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  const stamp =
    now.getFullYear() +
    pad(now.getMonth() + 1) +
    pad(now.getDate()) +
    "-" +
    pad(now.getHours()) +
    pad(now.getMinutes()) +
    pad(now.getSeconds());
  const blob = new Blob([serialized], { type: "application/json;charset=utf-8" });
  const link = document.createElement("a");
  const objectUrl = URL.createObjectURL(blob);
  link.href = objectUrl;
  link.download = "慢特病Skill验收结果-" + stamp + ".json";
  link.click();
  URL.revokeObjectURL(objectUrl);
  showNotice("验收结果已导出。");
}

async function importResults(file) {
  try {
    if (!file || !file.name.toLocaleLowerCase("zh-CN").endsWith(".json")) {
      throw new Error("invalid-file-type");
    }
    const text = await file.text();
    const candidateResults = validateResultsDocument(JSON.parse(text));
    results = candidateResults;
    persistResults();
    updateDashboard();
    renderCases();
    showNotice("验收结果已导入并替换当前版本记录。");
  } catch (error) {
    showNotice("导入失败：文件合同、版本或用例结果不匹配，原记录未覆盖。");
  }
}

function resetResults() {
  if (!window.confirm("确定重置当前版本的全部验收记录吗？此操作不可撤销。")) {
    return;
  }
  results = createDefaultResults();
  try {
    localStorage.removeItem(storageKey);
  } catch (error) {
    showNotice("记录已在页面中重置，但本地存储暂时无法删除。");
  }
  updateDashboard();
  renderCases();
  showNotice("当前版本的验收记录已重置。");
}

Object.values(filterControls).forEach((control) => {
  const eventName = control === filterControls.query ? "input" : "change";
  control.addEventListener(eventName, renderCases);
});
document.getElementById("clear-filters").addEventListener("click", clearFilters);
document.getElementById("export-results").addEventListener("click", exportResults);
document.getElementById("import-results").addEventListener("click", () => {
  document.getElementById("result-file").click();
});
document.getElementById("result-file").addEventListener("change", (event) => {
  const file = event.target.files && event.target.files[0];
  importResults(file);
  event.target.value = "";
});
document.getElementById("reset-results").addEventListener("click", resetResults);
document.getElementById("print-results").addEventListener("click", () => {
  window.print();
});

loadSavedResults();
updateDashboard();
renderCases();
"""


def _render_options(values):
    return "".join(
        f'<option value="{_html_text(value)}">{_html_text(value)}</option>'
        for value in values
    )


def render_acceptance_html(catalog, forbidden_terms=()):
    validate_catalog(catalog, forbidden_terms=forbidden_terms)
    catalog_json = safe_json_for_script(catalog).replace("/", "\\/")
    cases_html = "\n".join(_render_case(case) for case in catalog["cases"])
    title = _html_text(catalog["title"])
    description = _html_text(catalog["description"])
    version = _html_text(catalog["catalogVersion"])
    count = len(catalog["cases"])
    categories = sorted({case["category"] for case in catalog["cases"]})
    input_kinds = sorted(
        {
            input_kind
            for case in catalog["cases"]
            for input_kind in case["inputKinds"]
        }
    )
    category_options = _render_options(categories)
    input_kind_options = _render_options(input_kinds)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{CONSOLE_CSS}
</style>
</head>
<body>
<a class="skip-link" href="#main-content">跳到主要内容</a>
<header class="catalog-header">
<div class="header-inner">
<div>
<p class="eyebrow">离线验收控制台</p>
<h1>{title}</h1>
<p class="catalog-description">{description}</p>
<ul class="catalog-facts" aria-label="用例集信息">
<li>版本 {version}</li>
<li>共 {count} 条</li>
<li>四类覆盖：模式1、模式2、交互关口、安全产物</li>
<li>完全离线：数据仅保存在当前浏览器</li>
</ul>
</div>
<div class="action-bar interactive-controls" aria-label="结果操作">
<button id="export-results" class="primary-action" type="button" aria-label="导出当前验收结果">导出结果</button>
<label class="visually-hidden" for="result-file">选择要导入的验收结果 JSON 文件</label>
<input id="result-file" class="visually-hidden" type="file" accept=".json,application/json" aria-label="选择验收结果 JSON 文件">
<button id="import-results" type="button" aria-label="导入验收结果">导入</button>
<button id="print-results" type="button" aria-label="打印验收用例">打印</button>
<button id="reset-results" type="button" aria-label="重置当前版本验收结果">重置</button>
</div>
</div>
</header>
<main id="main-content">
<section id="summary-dashboard" class="summary-dashboard" aria-label="验收汇总" aria-live="polite">
<dl class="metric"><dt>总数</dt><dd id="metric-total">{count}</dd></dl>
<dl class="metric metric-passed"><dt>通过</dt><dd id="metric-passed">0</dd></dl>
<dl class="metric metric-failed"><dt>失败</dt><dd id="metric-failed">0</dd></dl>
<dl class="metric metric-blocked"><dt>阻塞</dt><dd id="metric-blocked">0</dd></dl>
<dl class="metric"><dt>未执行</dt><dd id="metric-not-run">{count}</dd></dl>
<dl class="metric"><dt>完成率</dt><dd id="metric-rate">0%</dd></dl>
</section>
<div class="workspace-grid">
<section id="case-filters" class="filter-panel" aria-labelledby="filter-heading">
<h2 id="filter-heading">筛选用例</h2>
<div class="filter-form">
<div class="filter-field">
<label for="filter-query">关键词</label>
<input id="filter-query" type="search" placeholder="ID、标题、目标或输入内容" aria-label="按关键词筛选用例">
</div>
<div class="filter-field">
<label for="filter-mode">模式</label>
<select id="filter-mode" aria-label="按模式筛选"><option value="all">全部</option><option value="mode1">mode1</option><option value="mode2">mode2</option><option value="gate">gate</option><option value="safety">safety</option></select>
</div>
<div class="filter-field">
<label for="filter-category">分类</label>
<select id="filter-category" aria-label="按分类筛选"><option value="all">全部</option>{category_options}</select>
</div>
<div class="filter-field">
<label for="filter-priority">优先级</label>
<select id="filter-priority" aria-label="按优先级筛选"><option value="all">全部</option><option value="P0">P0</option><option value="P1">P1</option><option value="P2">P2</option></select>
</div>
<div class="filter-field">
<label for="filter-input-kind">输入类型</label>
<select id="filter-input-kind" aria-label="按输入类型筛选"><option value="all">全部</option>{input_kind_options}</select>
</div>
<div class="filter-field">
<label for="filter-risk">风险</label>
<select id="filter-risk" aria-label="按风险筛选"><option value="all">全部</option><option value="错误放行风险">错误放行风险</option><option value="错误拒绝风险">错误拒绝风险</option><option value="其他">其他</option></select>
</div>
<div class="filter-field">
<label for="filter-status">状态</label>
<select id="filter-status" aria-label="按状态筛选"><option value="all">全部</option><option value="not-run">未执行</option><option value="passed">通过</option><option value="failed">失败</option><option value="blocked">阻塞</option></select>
</div>
</div>
<button id="clear-filters" class="clear-filter" type="button" aria-label="清除全部筛选条件">清除筛选</button>
</section>
<section class="case-column" aria-labelledby="case-list-heading">
<div class="case-section-heading">
<h2 id="case-list-heading">验收用例</h2>
<p id="result-count" class="result-count" aria-live="polite">当前显示 {count} / {count} 条</p>
</div>
<div id="case-list" class="case-list">
{cases_html}
</div>
<p id="empty-state" class="empty-state" hidden>没有符合当前条件的用例，请调整或清除筛选。</p>
</section>
</div>
</main>
<p id="page-notice" class="notice" role="status" aria-live="polite" hidden></p>
<footer class="page-footer">
本页不连接外部服务；验收记录按用例集版本保存在当前浏览器，可随时导出为 JSON。
</footer>
<script id="catalog-data" type="application/json">{catalog_json}</script>
<script>
{CONSOLE_JS}
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
        os.chmod(temporary, target_mode)
        os.replace(temporary, destination)
        temporary = None
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
                os.chmod(temporary, 0o600)
            except OSError:
                cleanup_error = True
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
