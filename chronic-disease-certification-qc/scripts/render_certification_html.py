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


def esc(value):
    """Escape any business value for HTML text or quoted attribute contexts."""
    return html.escape("" if value is None else str(value), quote=True)


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


def render_guides(guides):
    rows = []
    for guide in guides:
        required = '<span class="required">是</span>' if guide["required"] else '<span class="optional">否</span>'
        rows.append(
            "<tr>"
            f"<td><code title=\"{esc(guide['keywordCode'])}\">{esc(guide['keywordCode'])}</code></td>"
            f"<td>{esc(guide['keywordContent'])}</td>"
            f"<td>{esc(guide['dataType'])}</td>"
            f"<td>{required}</td>"
            f"<td>{render_options(guide['enumOptions'])}</td>"
            "</tr>"
        )
    return (
        '<div class="guide-table-wrap"><table><thead><tr>'
        "<th>关键词编码</th><th>取证/判断指引</th><th>数据类型</th><th>是否必填</th><th>枚举选项</th>"
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
        f'<div class="{css_class}"><h4>{label}</h4><p>{esc(rule[field])}</p></div>'
        for field, label, css_class in fields
    )
    return (
        f'<article class="rule-card" data-rule-code="{esc(rule["ruleCode"])}">'
        "<details open>"
        f'<summary><span class="rule-title" title="{esc(rule["ruleCode"])}">{esc(rule["ruleCode"])}</span>{esc(rule["ruleContent"])}</summary>'
        f'<div class="rule-fields">{rendered_fields}</div>'
        "<h4>取证与判断指引</h4>"
        f"{render_guides(rule['ruleKeywordGuide'])}"
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
    template = TEMPLATE.read_text(encoding="utf-8")
    rendered = template.replace("{{TITLE}}", esc(meta["chronicDiseaseName"])).replace("{{BODY}}", body)
    if "{{TITLE}}" in rendered or "{{BODY}}" in rendered:
        raise ValueError("Template placeholders could not be fully rendered.")
    return rendered


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Certification JSON input file")
    parser.add_argument("output", type=Path, help="HTML output file")
    args = parser.parse_args(argv)
    try:
        rendered = render_certification_html(args.input)
    except (OSError, ValueError) as exc:
        print(f"render_error: {exc}", file=sys.stderr)
        return 1
    try:
        args.output.write_text(rendered.rstrip("\n") + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"output_error: {exc}", file=sys.stderr)
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
