#!/usr/bin/env python3
"""Render a valid chronic-disease certification standard as offline HTML."""

import argparse
import html
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "certification-template.html"
_VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "validate_certification", ROOT / "scripts" / "validate_certification.py"
)
validator = importlib.util.module_from_spec(_VALIDATOR_SPEC)
_VALIDATOR_SPEC.loader.exec_module(validator)
_TITLE_PLACEHOLDER = "{{TITLE}}"
_BODY_PLACEHOLDER = "{{BODY}}"


def _normalize_text(value):
    """Replace surrogates, unsafe C0 controls, and DEL; retain tab, LF, and CR."""
    text = "" if value is None else str(value)
    return "".join(
        "\ufffd"
        if 0xD800 <= ord(character) <= 0xDFFF
        or (ord(character) < 0x20 and character not in "\t\n\r")
        or ord(character) == 0x7F
        else character
        for character in text
    )


def esc(value):
    """Escape any business value for HTML text or quoted attribute contexts."""
    return html.escape(_normalize_text(value), quote=True)


def load_template_segments():
    """Validate the pristine template once and split it around its two markers."""
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(_TITLE_PLACEHOLDER) != 1 or template.count(_BODY_PLACEHOLDER) != 1:
        raise ValueError("Template must contain exactly one {{TITLE}} and one {{BODY}} placeholder.")
    title_index = template.index(_TITLE_PLACEHOLDER)
    body_index = template.index(_BODY_PLACEHOLDER)
    if title_index >= body_index:
        raise ValueError("Template {{TITLE}} placeholder must appear before {{BODY}}.")
    before_title, after_title = template.split(_TITLE_PLACEHOLDER, 1)
    between_title_and_body, after_body = after_title.split(_BODY_PLACEHOLDER, 1)
    return before_title, between_title_and_body, after_body


def render_meta(meta):
    labels = (
        ("version", "标准版本"),
        ("chronicDiseaseName", "病种名称"),
        ("chronicDiseaseCode", "病种编码"),
        ("createdAt", "创建时间"),
        ("description", "标准说明"),
        ("sourceFile", "来源文件"),
    )
    fields = "".join(
        f"<div><dt>{label}</dt><dd>{esc(meta[field])}</dd></div>" for field, label in labels
    )
    return f'<dl class="meta-grid">{fields}</dl>'


def render_options(options):
    if not options:
        return '<span class="empty">无</span>'
    return '<ul class="options">' + "".join(f"<li>{esc(option)}</li>" for option in options) + "</ul>"


def render_guides(rule_code, guides):
    rows = []
    for guide in guides:
        required = '<span class="required">是</span>' if guide["required"] else '<span class="optional">否</span>'
        guide_json = esc(json.dumps(guide, ensure_ascii=False, indent=2, sort_keys=True))
        rows.append(
            "<tr>"
            f"<td><code title=\"{esc(guide['keywordCode'])}\">{esc(guide['keywordCode'])}</code></td>"
            f"<td>{esc(guide['keywordContent'])}</td>"
            f"<td>{esc(guide['dataType'])}</td>"
            f"<td>{required}</td>"
            f"<td>{render_options(guide['enumOptions'])}</td>"
            '<td><details class="guide-data"><summary>展开完整数据</summary>'
            f"<pre>{guide_json}</pre></details></td>"
            "</tr>"
        )
    return (
        '<div class="guide-table-wrap"><table>'
        f"<caption>规则 {esc(rule_code)} 的取证与判断指引</caption><thead><tr>"
        '<th scope="col">关键词编码</th><th scope="col">取证/判断指引</th><th scope="col">数据类型</th>'
        '<th scope="col">是否必填</th><th scope="col">枚举选项</th><th scope="col">完整数据结构</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def render_rule(rule):
    fields = (
        ("ruleContent", "认定条件", "wide"),
        ("ruleSource", "政策依据", ""),
        ("experience", "业务经验", ""),
        ("sourceRuleContent", "来源规则原文", "wide"),
        ("sourceMdFile", "来源 Markdown 文件", ""),
        ("sourceSection", "来源章节", ""),
    )
    rendered_fields = "".join(
        f'<div class="{css_class}"><p class="field-label">{label}</p><p>{esc(rule[field])}</p></div>'
        for field, label, css_class in fields
    )
    return (
        f'<article class="rule-card" data-rule-code="{esc(rule["ruleCode"])}">'
        "<details>"
        f'<summary><span class="rule-title" title="{esc(rule["ruleCode"])}">{esc(rule["ruleCode"])}</span>{esc(rule["ruleContent"])}</summary>'
        f'<div class="rule-fields">{rendered_fields}</div>'
        "<h3>取证与判断指引</h3>"
        f"{render_guides(rule['ruleCode'], rule['ruleKeywordGuide'])}"
        "</details></article>"
    )


def render_topology(node, rule_map):
    if node["type"] == "RULE_REF":
        return f"<li>{render_rule(rule_map[node['ruleCode']])}</li>"
    operator = node["operator"]
    label = "AND · 全部条件满足" if operator == "AND" else "OR · 任一条件满足"
    children = "".join(render_topology(child, rule_map) for child in node["children"])
    return (
        '<li class="logic-group">'
        f'<span class="logic-operator">{label}</span><ul>{children}</ul>'
        "</li>"
    )


def render_certification_html(source):
    """Validate supported input adapters and return deterministic offline HTML."""
    validation = validator.validate_certification(source)
    if not validation["valid"]:
        raise ValueError(json.dumps(validation["errors"], ensure_ascii=False))
    standard = validation["standard"]
    meta = standard["meta"]
    rule_map = {rule["ruleCode"]: rule for rule in standard["ruleRepository"]}
    raw_json = esc(json.dumps(standard, ensure_ascii=False, indent=2, sort_keys=True))
    body = (
        '<header class="page-header"><div class="header-inner">'
        '<p class="eyebrow">门诊慢特病 · 认定标准</p>'
        f"<h1>{esc(meta['chronicDiseaseName'])}</h1>"
        f'<p class="lede">{esc(meta["description"])}</p>'
        "</div></header>"
        '<main id="document-main">'
        '<section class="panel" aria-labelledby="meta-heading"><h2 id="meta-heading">标准信息</h2>'
        f"{render_meta(meta)}</section>"
        '<section class="panel" aria-labelledby="logic-heading"><h2 id="logic-heading">认定逻辑</h2>'
        '<p class="lede">沿蓝色逻辑脊柱读取条件组合；每个规则均保留完整来源与取证指引。</p>'
        f'<ul class="logic-tree">{render_topology(standard["logicTopology"], rule_map)}</ul></section>'
        '<section class="panel" aria-labelledby="raw-heading"><h2 id="raw-heading">原始标准数据</h2>'
        '<details class="raw-data"><summary>展开完整 JSON（已转义，仅供核对）</summary>'
        f"<pre>{raw_json}</pre></details></section>"
        "</main>"
    )
    before_title, between_title_and_body, after_body = load_template_segments()
    return before_title + esc(meta["chronicDiseaseName"]) + between_title_and_body + body + after_body


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Certification JSON input file")
    parser.add_argument("output", type=Path, help="HTML output file")
    args = parser.parse_args(argv)
    try:
        validator.ensure_output_not_alias(args.output, (args.input,))
    except ValueError as exc:
        print(f"output_error: {exc}", file=sys.stderr)
        return 1
    try:
        rendered = render_certification_html(args.input)
    except (OSError, ValueError) as exc:
        print(f"render_error: {exc}", file=sys.stderr)
        return 1
    try:
        validator.atomic_write_text(args.output, rendered.rstrip("\n") + "\n")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"output_error: {exc}", file=sys.stderr)
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
