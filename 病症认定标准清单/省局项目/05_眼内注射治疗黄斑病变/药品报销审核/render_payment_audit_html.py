#!/usr/bin/env python3
"""Render a payment-audit standard JSON as an offline rule-card HTML page."""

import html
import json
import sys
from pathlib import Path


def esc(value):
    return html.escape(str(value), quote=True)


def pretty(value):
    return esc(json.dumps(value, ensure_ascii=False, indent=2))


def render_guides(guides):
    rows = []
    for guide in guides:
        options = "、".join(esc(option) for option in guide["enumOptions"]) or "无"
        required = "是" if guide["required"] else "否"
        rows.append(
            "<tr>"
            f"<td>{esc(guide['keywordCode'])}</td>"
            f"<td>{esc(guide['keywordContent'])}</td>"
            f"<td>{esc(guide['dataType'])}</td><td>{required}</td><td>{options}</td>"
            f"<td><details class=\"inline-json\"><summary>展开</summary><pre>{pretty(guide)}</pre></details></td>"
            "</tr>"
        )
    return (
        "<table class=\"keyword-definition-table\"><thead><tr>"
        "<th>编号</th><th>内容</th><th>数据类型</th><th>是否必须</th><th>可选项</th><th>完整数据结构</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def render_rule(rule):
    section = rule["sourceSection"] or "未标注"
    return (
        "<details class=\"overview-rule logic-rule-detail\"><summary><span>"
        f"<strong>规则 {esc(rule['ruleCode'])}</strong>"
        f"<span class=\"logic-rule-title\">规则原文：{esc(rule['ruleContent'])}</span>"
        f"<span class=\"logic-rule-meta\">来源分项：{esc(section)} · 提取项 {len(rule['ruleKeywordGuide'])} 条</span>"
        "</span><span class=\"summary-actions\"><span class=\"pill good\">已维护</span></span></summary>"
        "<div class=\"overview-rule-body\"><div class=\"repo-detail\"><h4>规则库详情</h4>"
        "<div class=\"repo-grid\">"
        f"<div><h4>政策原文</h4><p>{esc(rule['ruleContent'])}</p></div>"
        f"<div><h4>政策依据</h4><p>{esc(rule['ruleSource'])}</p></div>"
        f"<div><h4>来源分项</h4><p>{esc(section)}</p></div></div>"
        f"<h4>规则原文留存</h4><div class=\"source-box\"><p>{esc(rule['sourceRuleContent'])}</p></div>"
        f"<h4>提取项说明</h4>{render_guides(rule['ruleKeywordGuide'])}"
        f"<details class=\"raw-block\"><summary>展开完整数据结构</summary><pre>{pretty(rule)}</pre></details>"
        "</div></div></details>"
    )


def render_topology(node, rule_map):
    if node["type"] == "RULE_REF":
        return f"<li class=\"logic-rule-ref logic-rule-item\">{render_rule(rule_map[node['ruleCode']])}</li>"
    label = "AND · 全部条件满足" if node["operator"] == "AND" else "OR · 任一条件满足"
    children = "".join(render_topology(child, rule_map) for child in node["children"])
    return f"<li class=\"logic-group\"><div class=\"logic-operator\">{label}</div><ul>{children}</ul></li>"


def render(standard):
    meta = standard["meta"]
    rule_map = {rule["ruleCode"]: rule for rule in standard["ruleRepository"]}
    guide_count = sum(len(rule["ruleKeywordGuide"]) for rule in standard["ruleRepository"])
    logic = render_topology(standard["logicTopology"], rule_map)
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(meta['chronicDiseaseName'])}（{esc(meta['version'])}）</title><style>
:root{{--bg:#eef4f9;--surface:#fff;--surface-2:#f6f9fc;--surface-3:#eaf1f7;--ink:#17293d;--muted:#617185;--line:#cfdeeb;--accent:#246bb2;--accent-soft:#dceeff;--good:#287149;--good-soft:#dcf4e3;--radius:10px}}*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(180deg,#f9fcff,var(--bg) 360px);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;line-height:1.56}}.page{{width:min(1320px,calc(100% - 36px));margin:0 auto;padding:16px 0 56px}}.panel{{border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);padding:20px;box-shadow:0 8px 22px rgba(31,63,96,.06)}}h1,h2,h3,h4,p{{margin:0}}h2{{font-size:19px;margin-bottom:8px}}h3{{font-size:16px;margin:18px 0 10px}}h4{{font-size:13px;margin-bottom:8px}}.eyebrow,.sub{{color:var(--muted);font-size:13px}}.eyebrow{{font-weight:800}}.panel-head{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px}}.panel-stats{{display:flex;gap:10px;align-items:flex-start;color:var(--muted);font-size:13px;font-weight:800;flex-wrap:wrap;justify-content:flex-end}}.pill{{display:inline-flex;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:800}}.pill.good{{color:var(--good);background:var(--good-soft);border:1px solid #a8d9b5}}.logic-topology{{margin-top:12px;padding:14px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface-2);overflow:hidden}}.logic-tree,.logic-tree ul{{list-style:none;margin:10px 0 0;padding-left:18px}}.logic-group,.logic-rule-ref{{position:relative;margin:8px 0}}.logic-group::before,.logic-rule-ref::before{{content:"";position:absolute;left:-12px;top:13px;width:8px;border-top:1px solid #adbed0}}.logic-operator{{display:inline-flex;padding:4px 9px;border-radius:999px;background:var(--accent-soft);color:#18558d;font-size:12px;font-weight:800}}.logic-rule-ref{{padding:0;min-width:0}}.overview-rule{{display:block;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);overflow:hidden}}.overview-rule summary{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:start;padding:13px 14px;cursor:pointer;list-style:none}}.overview-rule summary::-webkit-details-marker{{display:none}}.overview-rule summary::before{{content:"展开";grid-column:1;grid-row:1;justify-self:start;padding:3px 8px;border-radius:999px;background:var(--accent-soft);color:#18558d;font-size:12px;font-weight:800;border:1px solid #7ab2e3}}.overview-rule[open]>summary::before{{content:"收起"}}.overview-rule summary>span:first-of-type{{grid-column:1;grid-row:1;padding-left:76px}}.summary-actions{{grid-column:2;grid-row:1}}.logic-rule-title{{display:block;margin-top:5px;font-size:14px;font-weight:760}}.logic-rule-meta{{display:block;margin-top:5px;color:var(--muted);font-size:12px;font-weight:760}}.overview-rule-body{{padding:14px;border-top:1px solid var(--line);background:var(--surface-2)}}.repo-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:12px}}.repo-grid>div,.source-box{{padding:10px;border:1px solid var(--line);border-radius:7px;background:var(--surface)}}.source-box{{margin-bottom:12px;white-space:pre-wrap}}.keyword-definition-table{{width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed}}.keyword-definition-table th,.keyword-definition-table td{{padding:10px 9px;border-top:1px solid var(--line);text-align:left;vertical-align:top;overflow-wrap:anywhere;word-break:break-word}}.keyword-definition-table th{{color:var(--muted);font-weight:800;background:var(--surface-3)}}.keyword-definition-table th:nth-child(1){{width:11%}}.keyword-definition-table th:nth-child(3),.keyword-definition-table th:nth-child(4){{width:8%}}.keyword-definition-table th:nth-child(5){{width:13%}}.keyword-definition-table th:nth-child(6){{width:25%}}pre{{margin:0;padding:12px;border-radius:7px;background:#1e2d3d;color:#eff6fd;overflow:auto;font-size:12px;line-height:1.52;white-space:pre-wrap;word-break:break-word}}.inline-json summary,.raw-block summary{{cursor:pointer;color:#18558d;font-weight:800}}.raw-block{{margin-top:12px;border:1px solid var(--line);border-radius:7px;background:var(--surface);padding:10px 12px}}@media(max-width:900px){{.page{{width:min(100% - 20px,1320px)}}.panel-head,.repo-grid{{grid-template-columns:1fr}}.keyword-definition-table{{display:block;overflow:auto}}.overview-rule summary>span:first-of-type{{padding-left:0;margin-top:30px}}}}
</style></head><body><main class="page"><section class="panel"><div class="panel-head"><div><p class="eyebrow">{esc(meta['version'])} · {esc(meta['chronicDiseaseCode'])}</p><h2>{esc(meta['chronicDiseaseName'])}</h2><p class="sub">来源：{esc(meta['sourceFile'])}；规则性质：某类药品报销审核。</p></div><div class="panel-stats"><span class="pill good">可解析</span><span>{len(rule_map)} 条规则</span><span>{guide_count} 条提取项</span></div></div><h3>规则判定总览</h3><section class="logic-topology"><h4>逻辑拓扑</h4><p class="sub">按入参 logicTopology 展示规则之间的且或关系。</p><ul class="logic-tree">{logic}</ul></section></section></main></body></html>'''


def main(argv):
    if len(argv) != 3:
        raise SystemExit("usage: render_payment_audit_html.py INPUT_JSON OUTPUT_HTML")
    source, output = Path(argv[1]), Path(argv[2])
    standard = json.loads(source.read_text(encoding="utf-8"))
    output.write_text(render(standard), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv)
