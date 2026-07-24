#!/usr/bin/env python3
"""Validate a canonical audit-QC object and render offline text or HTML."""

import argparse
import copy
import html
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "qc-report-template.html"
TITLE = "{{TITLE}}"
BODY = "{{BODY}}"
MAX_DEPTH = 64
ROOT_FIELDS = {"case", "inputScope", "capabilities", "originalResult", "qcConclusion", "riskDirection", "recommendedAction", "issues", "ruleReviews", "unperformedChecks", "rawInput"}
CAPABILITY_STATUSES = {"completed", "partial", "not_run"}
SEVERITIES = {"high", "medium", "low"}
CONFIDENCES = SEVERITIES
IMPACTS = {"changed", "potentially_changed", "unchanged", "unknown"}
ISSUE_RISKS = {"false_approval", "false_rejection", "both", "none"}
ROOT_RISKS = {"错误放行风险", "错误拒绝风险", "局部判断错误", "仅影响规则质量", "暂时无法判断", "未发现明显风险"}
RELIABILITY = {"可靠", "基本可靠", "存在重大疑点", "不可靠", "无法确定"}
RULE_RESULTS = {"满足", "不满足", "无法判断", "不适用"}
EVIDENCE_STATES = {"SUPPORTED", "CONTRADICTED", "NOT_FOUND", "INSUFFICIENT", "CONFLICTED", "NOT_APPLICABLE"}
CATEGORIES = {"材料缺失判断准确性", "证据提取准确性", "过度推理", "审核条件与结论一致性", "规则维护质量"}
SECTION_CATEGORIES = (("材料缺失复核", "材料缺失判断准确性"), ("证据准确性", "证据提取准确性"), ("过度推理", "过度推理"), ("条件一致性", "审核条件与结论一致性"), ("规则维护质量", "规则维护质量"))
RISK_LABELS = {"false_approval": "错误放行风险", "false_rejection": "错误拒绝风险", "both": "错误放行与错误拒绝风险", "none": "未发现明显风险"}
IMPACT_LABELS = {"changed": "已改变最终结论", "potentially_changed": "可能改变最终结论", "unchanged": "未改变最终结论", "unknown": "最终影响暂无法判断"}


def _error(path, message):
    raise ValueError(f"qc_report_invalid: {path}: {message}")


def _safe_text(value):
    return "".join("\ufffd" if 0xD800 <= ord(char) <= 0xDFFF or (ord(char) < 0x20 and char not in "\t\n\r") or ord(char) == 0x7F else char for char in value)


def _json_safe(value, path="root", depth=0, ancestors=None):
    """Copy arbitrary JSON after rejecting cycles, excessive depth and invalid values."""
    if depth > MAX_DEPTH:
        _error(path, "input is too deep")
    if ancestors is None:
        ancestors = set()
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _error(path, "non-finite number is not JSON serializable")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        identity = id(value)
        if identity in ancestors:
            _error(path, "cycle detected")
        return [_json_safe(item, f"{path}[{index}]", depth + 1, ancestors | {identity}) for index, item in enumerate(value)]
    if isinstance(value, dict):
        identity = id(value)
        if identity in ancestors:
            _error(path, "cycle detected")
        copied = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _error(path, "object keys must be strings")
            if key in copied:
                _error(path, "duplicate object keys")
            copied[key] = _json_safe(item, f"{path}.{key}", depth + 1, ancestors | {identity})
        return copied
    _error(path, f"unsupported non-JSON value {type(value).__name__}")


def _reject_duplicate_pairs(pairs):
    """JSON hook that rejects a duplicate before JSON silently overwrites it."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"qc_report_input: duplicate JSON key {key!r}")
        result[key] = value
    return result


def _parse_json(text, label):
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except ValueError as exc:
        message = str(exc)
        if message.startswith("qc_report_input:"):
            raise
        raise ValueError(f"qc_report_input: invalid JSON {label}: {message}") from None
    except RecursionError:
        raise ValueError(f"qc_report_input: JSON {label} is too deep or recursive") from None


def _load_source(source):
    if isinstance(source, Path):
        try:
            return _parse_json(source.read_text(encoding="utf-8-sig"), "file")
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError(f"qc_report_input: {exc}") from None
    if isinstance(source, str):
        return _parse_json(source.lstrip("\ufeff"), "string")
    if isinstance(source, dict):
        return source
    _error("root", "source must be a dict, JSON string, or pathlib.Path")


def _object(value, path, fields):
    if not isinstance(value, dict):
        _error(path, "must be an object")
    missing = fields - set(value)
    if missing:
        _error(path, f"missing required field {sorted(missing)[0]}")


def _text(value, path):
    if not isinstance(value, str) or not value.strip():
        _error(path, "must be a non-empty string")


def _enum(value, path, choices):
    _text(value, path)
    if value not in choices:
        _error(path, f"must be one of {', '.join(sorted(choices))}")


def _evidence(items, path, material_sources):
    if not isinstance(items, list):
        _error(path, "must be an array")
    for index, item in enumerate(items):
        point = f"{path}[{index}]"
        _object(item, point, {"materialId", "materialName", "page", "section", "rawText", "normalizedText", "location"})
        for field in ("materialId", "materialName", "section", "rawText"):
            _text(item[field], f"{point}.{field}")
        if not isinstance(item["normalizedText"], str): _error(f"{point}.normalizedText", "must be a string")
        if type(item["page"]) is not int or item["page"] <= 0: _error(f"{point}.page", "must be a positive integer")
        location = item["location"]
        if location is None:
            continue
        _object(location, f"{point}.location", {"start", "end"})
        start, end = location["start"], location["end"]
        if type(start) is not int or type(end) is not int or start < 0 or end < 0 or start > end:
            _error(f"{point}.location", "start/end must be nonnegative integers with start <= end")
        source = material_sources.get(item["materialId"])
        if source is not None and (end > len(source) or source[start:end] != item["rawText"]):
            _error(f"{point}.location", "must locate rawText in the source material")


def _material_sources(raw_input):
    if not isinstance(raw_input, dict) or not isinstance(raw_input.get("materials"), list):
        return {}
    sources = {}
    for item in raw_input["materials"]:
        if isinstance(item, dict) and isinstance(item.get("materialId"), str) and isinstance(item.get("content"), str):
            sources[item["materialId"]] = item["content"]
    return sources


def _validate_evidence_state(status, evidence, path):
    if status in {"SUPPORTED", "CONTRADICTED", "INSUFFICIENT", "CONFLICTED"} and not evidence:
        _error(path, "requires at least one materialEvidence")
    if status in {"NOT_FOUND", "NOT_APPLICABLE"} and evidence:
        _error(path, "requires empty materialEvidence")


def _validate_report(report):
    if not isinstance(report, dict):
        _error("root", "must be an object")
    missing, extra = ROOT_FIELDS - set(report), set(report) - ROOT_FIELDS
    if missing:
        _error("root", f"missing required field {sorted(missing)[0]}")
    if extra:
        _error("root", f"unexpected field {sorted(extra)[0]}")
    _object(report["case"], "case", {"patientName", "diseaseName", "auditId"})
    for field in ("patientName", "diseaseName", "auditId"):
        _text(report["case"][field], f"case.{field}")
    _object(report["inputScope"], "inputScope", {"confirmedByUser", "materials", "standardKind", "auditResultKind"})
    if type(report["inputScope"]["confirmedByUser"]) is not bool:
        _error("inputScope.confirmedByUser", "must be boolean")
    if not report["inputScope"]["confirmedByUser"]:
        _error("inputScope.confirmedByUser", "输入清单尚未得到用户确认；must be true before formal output")
    if not isinstance(report["inputScope"]["materials"], list):
        _error("inputScope.materials", "must be an array")
    for index, item in enumerate(report["inputScope"]["materials"]):
        _text(item, f"inputScope.materials[{index}]")
    _text(report["inputScope"]["standardKind"], "inputScope.standardKind")
    _text(report["inputScope"]["auditResultKind"], "inputScope.auditResultKind")
    if not isinstance(report["capabilities"], list):
        _error("capabilities", "must be an array")
    capabilities_by_name = {}
    for index, capability in enumerate(report["capabilities"]):
        point = f"capabilities[{index}]"; _object(capability, point, {"name", "status", "reason"})
        _text(capability["name"], f"{point}.name"); _enum(capability["status"], f"{point}.status", CAPABILITY_STATUSES)
        if not isinstance(capability["reason"], str): _error(f"{point}.reason", "must be a string")
        if capability["status"] in {"partial", "not_run"} and not capability["reason"].strip():
            _error(f"{point}.reason", "must be non-empty when status is partial or not_run")
        if capability["name"] in capabilities_by_name: _error(point, "capability name must be unique")
        capabilities_by_name[capability["name"]] = capability
    _text(report["originalResult"], "originalResult")
    _enum(report["qcConclusion"], "qcConclusion", RELIABILITY); _enum(report["riskDirection"], "riskDirection", ROOT_RISKS); _text(report["recommendedAction"], "recommendedAction")
    if not isinstance(report["issues"], list): _error("issues", "must be an array")
    issue_fields = {"category", "issueType", "severity", "ruleCode", "keywordCode", "modelClaim", "evidenceStatus", "materialEvidence", "qcFinding", "possibleImpact", "impactOnFinalResult", "riskDirection", "recommendation", "confidence"}
    for index, issue in enumerate(report["issues"]):
        point = f"issues[{index}]"; _object(issue, point, issue_fields)
        _enum(issue["category"], f"{point}.category", CATEGORIES); _text(issue["issueType"], f"{point}.issueType")
        for field in ("ruleCode", "modelClaim", "qcFinding", "possibleImpact", "recommendation"):
            _text(issue[field], f"{point}.{field}")
        if not isinstance(issue["keywordCode"], str): _error(f"{point}.keywordCode", "must be a string")
        _enum(issue["severity"], f"{point}.severity", SEVERITIES); _enum(issue["confidence"], f"{point}.confidence", CONFIDENCES); _enum(issue["impactOnFinalResult"], f"{point}.impactOnFinalResult", IMPACTS); _enum(issue["riskDirection"], f"{point}.riskDirection", ISSUE_RISKS); _enum(issue["evidenceStatus"], f"{point}.evidenceStatus", EVIDENCE_STATES)
        if issue["impactOnFinalResult"] in {"changed", "potentially_changed"} and issue["severity"] != "high": _error(f"{point}.severity", "must be high when final result may change")
        _validate_evidence_state(issue["evidenceStatus"], issue["materialEvidence"], f"{point}.materialEvidence")
        _evidence(issue["materialEvidence"], f"{point}.materialEvidence", _material_sources(report["rawInput"]))
    if not isinstance(report["ruleReviews"], list): _error("ruleReviews", "must be an array")
    review_fields = {"ruleCode", "result", "modelClaim", "evidenceStatus", "materialEvidence", "qcFinding", "recommendation"}
    for index, review in enumerate(report["ruleReviews"]):
        point = f"ruleReviews[{index}]"; _object(review, point, review_fields)
        for field in ("ruleCode", "modelClaim", "qcFinding", "recommendation"): _text(review[field], f"{point}.{field}")
        _enum(review["result"], f"{point}.result", RULE_RESULTS); _enum(review["evidenceStatus"], f"{point}.evidenceStatus", EVIDENCE_STATES)
        _validate_evidence_state(review["evidenceStatus"], review["materialEvidence"], f"{point}.materialEvidence")
        _evidence(review["materialEvidence"], f"{point}.materialEvidence", _material_sources(report["rawInput"]))
    if not isinstance(report["unperformedChecks"], list): _error("unperformedChecks", "must be an array")
    unperformed_by_name = {}
    for index, check in enumerate(report["unperformedChecks"]):
        point = f"unperformedChecks[{index}]"; _object(check, point, {"name", "reason"})
        _text(check["name"], f"{point}.name"); _text(check["reason"], f"{point}.reason")
        if "status" in check and check["status"] != "not_run": _error(f"{point}.status", "must be not_run")
        if check["name"] in unperformed_by_name: _error(point, "unperformed check name must be unique")
        unperformed_by_name[check["name"]] = check
    not_run = {name: item for name, item in capabilities_by_name.items() if item["status"] == "not_run"}
    if set(not_run) != set(unperformed_by_name): _error("unperformedChecks", "must exactly match not_run capability names")
    for name, capability in not_run.items():
        if capability["reason"] != unperformed_by_name[name]["reason"]:
            _error("unperformedChecks", f"reason must match capability {name}")


def validate_qc_report(source):
    """Return a normalized deep copy, or raise a stable ValueError without mutation."""
    report = _json_safe(_load_source(source))
    try:
        json.dumps(report, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"qc_report_invalid: root: not JSON serializable: {exc}") from None
    _validate_report(report)
    return copy.deepcopy(report)


def _text_scalar(value):
    """Display a scalar as one JSON-quoted line, never as report structure."""
    return json.dumps(_safe_text(str(value)), ensure_ascii=False)


def _evidence_text(evidence):
    if not evidence: return "无证据。"
    entries = []
    for item in evidence:
        location = item["location"]
        location_text = "无精确定位" if location is None else f"start={location['start']}，end={location['end']}"
        entries.append("材料编号：{}；材料名称：{}；页：{}；章节：{}；定位：{}；原文：{}；规范化：{}".format(
            _text_scalar(item["materialId"]), _text_scalar(item["materialName"]), _text_scalar(item["page"]), _text_scalar(item["section"]), location_text, _text_scalar(item["rawText"]), _text_scalar(item["normalizedText"])))
    return "\n".join(entries)


def _issue_text(issue):
    return "- 严重度：{}；问题类型：{}；规则：{}；关键词：{}；证据状态：{}；风险：{}；最终影响：{}；置信度：{}\n  模型主张：{}\n  材料/标准证据：{}\n  质控发现：{}\n  可能影响：{}\n  建议：{}".format(
        _text_scalar(issue["severity"]), _text_scalar(issue["issueType"]), _text_scalar(issue["ruleCode"]), _text_scalar(issue["keywordCode"]), _text_scalar(issue["evidenceStatus"]), _text_scalar(RISK_LABELS[issue["riskDirection"]]), _text_scalar(IMPACT_LABELS[issue["impactOnFinalResult"]]), _text_scalar(issue["confidence"]), _text_scalar(issue["modelClaim"]), _evidence_text(issue["materialEvidence"]), _text_scalar(issue["qcFinding"]), _text_scalar(issue["possibleImpact"]), _text_scalar(issue["recommendation"]))


def render_qc_text(source):
    report = validate_qc_report(source)
    issue_groups = {category: [item for item in report["issues"] if item["category"] == category] for _, category in SECTION_CATEGORIES}
    changed = [item for item in report["issues"] if item["impactOnFinalResult"] in {"changed", "potentially_changed"}]
    lines = ["# 质控结论", f"结论：{_text_scalar(report['qcConclusion'])}", f"风险方向：{_text_scalar(report['riskDirection'])}", f"原审核结论：{_text_scalar(report['originalResult'])}", f"问题数量：{len(report['issues'])}", "", "# 输入与检查范围", "案例：{}／{}／{}".format(_text_scalar(report["case"]["patientName"]), _text_scalar(report["case"]["diseaseName"]), _text_scalar(report["case"]["auditId"])), "材料：{}".format(_text_scalar("、".join(report["inputScope"]["materials"]) or "无")), f"标准格式：{_text_scalar(report['inputScope']['standardKind'])}", f"审核结果类型：{_text_scalar(report['inputScope']['auditResultKind'])}"]
    if report["capabilities"]:
        lines += ["- 名称：{}；状态：{}；原因：{}".format(_text_scalar(item["name"]), _text_scalar(item["status"]), _text_scalar(item["reason"])) for item in report["capabilities"]]
    else: lines.append("无能力检查记录")
    lines += ["", "# 影响最终结论的问题"]
    lines += [_issue_text(item) for item in changed] if changed else ["无相关问题"]
    for heading, category in SECTION_CATEGORIES:
        lines += ["", f"# {heading}"]
        lines += [_issue_text(item) for item in issue_groups[category]] if issue_groups[category] else ["无相关问题"]
    lines += ["", "# 逐规则复核"]
    if report["ruleReviews"]:
        for review in report["ruleReviews"]:
            lines += ["- 规则：{}；结果：{}；证据状态：{}".format(_text_scalar(review["ruleCode"]), _text_scalar(review["result"]), _text_scalar(review["evidenceStatus"])), f"  模型主张：{_text_scalar(review['modelClaim'])}", f"  材料/标准证据：{_evidence_text(review['materialEvidence'])}", f"  质控发现：{_text_scalar(review['qcFinding'])}", f"  建议：{_text_scalar(review['recommendation'])}"]
    else: lines.append("无逐规则复核")
    lines += ["", "# 建议", f"总体建议：{_text_scalar(report['recommendedAction'])}"]
    for issue in report["issues"]: lines.append(f"- {_text_scalar(issue['recommendation'])}")
    lines += ["", "# 未执行检查"]
    lines += ["- 名称：{}；原因：{}".format(_text_scalar(check["name"]), _text_scalar(check["reason"])) for check in report["unperformedChecks"]] if report["unperformedChecks"] else ["无未执行检查"]
    lines += ["", "# 原始输入", json.dumps(report["rawInput"], ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False)]
    return "\n".join(lines) + "\n"


def esc(value): return html.escape(_safe_text(str(value)), quote=True)


def _evidence_html(evidence):
    if not evidence: return '<p class="empty">无证据。</p>'
    cards = []
    for item in evidence:
        location = item["location"]
        location_fields = (("定位", "未提供精确定位"),) if location is None else (("定位起点", location["start"]), ("定位终点", location["end"]))
        fields = (("材料编号", item["materialId"]), ("材料名称", item["materialName"]), ("页码", item["page"]), ("章节", item["section"]), *location_fields)
        cards.append('<div class="evidence"><div class="grid">' + ''.join(f'<div class="field"><b>{esc(label)}</b>{esc(value)}</div>' for label, value in fields) + '</div><p class="label">原始文本</p><blockquote>' + esc(item["rawText"]) + '</blockquote><p class="label">规范化文本</p><blockquote>' + esc(item["normalizedText"]) + '</blockquote></div>')
    return ''.join(cards)


def _issue_html(issue):
    tags = (("规则", issue["ruleCode"]), ("关键词", issue["keywordCode"]), ("证据状态", issue["evidenceStatus"]), ("严重度", issue["severity"]), ("风险", RISK_LABELS[issue["riskDirection"]]), ("最终影响", IMPACT_LABELS[issue["impactOnFinalResult"]]), ("置信度", issue["confidence"]))
    return f'<article class="issue {esc(issue["severity"])}"><h3>{esc(issue["issueType"])} <span class="muted">· {esc(issue["category"])}</span></h3>' + ''.join(f'<span class="tag">{esc(key)}：{esc(value)}</span>' for key, value in tags) + f'<dl><dt>模型主张</dt><dd>{esc(issue["modelClaim"])}</dd><dt>实际材料或标准证据</dt><dd>{_evidence_html(issue["materialEvidence"])}</dd><dt>为何错误或存在问题</dt><dd>{esc(issue["qcFinding"])}</dd><dt>可能影响</dt><dd>{esc(issue["possibleImpact"])}</dd><dt>建议</dt><dd>{esc(issue["recommendation"])}</dd></dl></article>'


def _template_parts():
    try: template = TEMPLATE.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc: raise ValueError(f"qc_report_template: {exc}") from None
    if template.count(TITLE) != 1 or template.count(BODY) != 1: raise ValueError("qc_report_template: requires exactly one {{TITLE}} and one {{BODY}}")
    before, rest = template.split(TITLE, 1); middle, after = rest.split(BODY, 1)
    return before, middle, after


def render_qc_html(source):
    report = validate_qc_report(source)
    changed = [item for item in report["issues"] if item["impactOnFinalResult"] in {"changed", "potentially_changed"}]
    section = lambda heading, content: f'<section class="panel" aria-labelledby="{esc(heading)}"><h2 id="{esc(heading)}">{esc(heading)}</h2>{content}</section>'
    scope = f'<div class="grid"><div class="field"><b>案例</b>{esc(report["case"]["patientName"])}／{esc(report["case"]["diseaseName"])}／{esc(report["case"]["auditId"])} </div><div class="field"><b>材料</b>{esc("、".join(report["inputScope"]["materials"]) or "无")}</div><div class="field"><b>标准格式</b>{esc(report["inputScope"]["standardKind"])}</div><div class="field"><b>审核结果类型</b>{esc(report["inputScope"]["auditResultKind"])}</div></div>'
    capabilities = ''.join(f'<div class="field"><b>{esc(item["name"])}</b><span class="status {"not-run" if item["status"] == "not_run" else ""}">{esc(item["status"])}</span><br>{esc(item["reason"])}</div>' for item in report["capabilities"]) or '<p class="empty">无能力检查记录</p>'
    body = '<header class="page-header"><div class="header-inner"><p class="eyebrow">门诊慢特病 · 审核质控</p><h1>智能审核质控报告</h1><p class="lede">案例 ' + esc(report["case"]["auditId"]) + ' · 由同一规范对象生成文本与本报告</p></div></header><main id="qc-report-main">'
    body += section("质控结论", f'<div class="grid"><div class="field"><b>质控结论</b>{esc(report["qcConclusion"])}</div><div class="field"><b>风险方向</b>{esc(report["riskDirection"])}</div><div class="field"><b>原审核结论</b>{esc(report["originalResult"])}</div><div class="field"><b>问题数量</b>{len(report["issues"])}</div></div>')
    body += section("输入与检查范围", scope + '<h3>检查能力</h3><div class="grid">' + capabilities + '</div>')
    body += section("影响最终结论的问题", ''.join(_issue_html(item) for item in changed) or '<p class="empty">无相关问题</p>')
    for heading, category in SECTION_CATEGORIES:
        selected = [item for item in report["issues"] if item["category"] == category]
        body += section(heading, ''.join(_issue_html(item) for item in selected) or '<p class="empty">无相关问题</p>')
    reviews = ''.join(f'<article class="evidence"><h3>规则 {esc(item["ruleCode"])}：{esc(item["result"])}</h3><dl><dt>证据状态</dt><dd>{esc(item["evidenceStatus"])}</dd><dt>模型主张</dt><dd>{esc(item["modelClaim"])}</dd><dt>材料或标准证据</dt><dd>{_evidence_html(item["materialEvidence"])}</dd><dt>质控发现</dt><dd>{esc(item["qcFinding"])}</dd><dt>建议</dt><dd>{esc(item["recommendation"])}</dd></dl></article>' for item in report["ruleReviews"])
    body += section("逐规则复核", reviews or '<p class="empty">无逐规则复核</p>')
    body += section("建议", '<p><b>总体建议：</b>' + esc(report["recommendedAction"]) + '</p>' + ('<ul>' + ''.join(f'<li>{esc(item["recommendation"])}</li>' for item in report["issues"]) + '</ul>' if report["issues"] else '<p class="empty">无额外问题建议</p>'))
    checks = ''.join(f'<div class="field"><b>{esc(item["name"])}</b><span class="status not-run">not_run</span><br>{esc(item["reason"])}</div>' for item in report["unperformedChecks"])
    body += section("未执行的检查", '<div class="grid">' + (checks or '<p class="empty">无未执行检查</p>') + '</div>')
    raw = esc(json.dumps(report["rawInput"], ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False))
    body += section("原始输入", '<details class="raw-data"><summary>展开原始输入 JSON（已转义，仅供核对）</summary><pre>' + raw + '</pre></details>') + '</main>'
    before, middle, after = _template_parts()
    return before + esc("智能审核质控报告 · " + report["case"]["auditId"]) + middle + body + after


def _canonical_path(path):
    """Resolve normal aliases and existing symlinks without requiring the leaf to exist."""
    try:
        return Path(path).expanduser().resolve(strict=False)
    except OSError as exc:
        raise ValueError(f"output path cannot be resolved: {exc}") from None


def _reject_output_collisions(input_path, html_output, text_output=None):
    named = [("input", _canonical_path(input_path)), ("HTML output", _canonical_path(html_output))]
    if text_output is not None:
        named.append(("text output", _canonical_path(text_output)))
    for index, (name, path) in enumerate(named):
        for other_name, other_path in named[index + 1:]:
            if path == other_path:
                raise ValueError(f"output collision: {name} and {other_name} resolve to the same path")
    return {name: path for name, path in named}


def _stage_output(destination, data):
    with tempfile.NamedTemporaryFile(prefix=".qc-report-stage-", dir=destination.parent, delete=False) as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        return Path(handle.name)


def _write_outputs_atomically(outputs):
    """Commit byte outputs together, restoring pre-existing files after a failed replace."""
    staged, backups, committed = {}, {}, []
    try:
        for destination, data in outputs.items():
            staged[destination] = _stage_output(destination, data)
        for destination in outputs:
            if destination.exists():
                with tempfile.NamedTemporaryFile(prefix=".qc-report-backup-", dir=destination.parent, delete=False) as handle:
                    handle.write(destination.read_bytes())
                    handle.flush()
                    os.fsync(handle.fileno())
                    backups[destination] = Path(handle.name)
        for destination, stage in list(staged.items()):
            os.replace(stage, destination)
            committed.append(destination)
            staged.pop(destination, None)
    except Exception:
        for destination in reversed(committed):
            backup = backups.get(destination)
            try:
                if backup is not None:
                    os.replace(backup, destination)
                    backups.pop(destination, None)
                elif destination.exists():
                    destination.unlink()
            except OSError:
                pass
        raise
    finally:
        for temporary in (*staged.values(), *backups.values()):
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="QC report JSON input")
    parser.add_argument("output", type=Path, help="HTML output")
    parser.add_argument("--text-output", type=Path, help="optional text report output")
    args = parser.parse_args(argv)
    try:
        paths = _reject_output_collisions(args.input, args.output, args.text_output)
        report = validate_qc_report(paths["input"]); rendered = render_qc_html(report); text = render_qc_text(report)
        outputs = {paths["HTML output"]: (rendered.rstrip("\n") + "\n").encode("utf-8")}
        if args.text_output:
            outputs[paths["text output"]] = (text.rstrip("\n") + "\n").encode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"render_error: {exc}", file=sys.stderr); return 1
    try:
        _write_outputs_atomically(outputs)
    except (OSError, UnicodeError) as exc:
        print(f"output_error: {exc}", file=sys.stderr); return 1
    print(args.output); return 0


if __name__ == "__main__":
    raise SystemExit(main())
