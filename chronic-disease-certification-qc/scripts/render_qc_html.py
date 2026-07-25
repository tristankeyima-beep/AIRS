#!/usr/bin/env python3
"""Validate a canonical audit-QC object and render offline text or HTML."""

import argparse
import copy
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import unicodedata
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
STANDARD_KINDS = {"structured_complete", "structured_incomplete", "natural_language", "absent"}
AUDIT_RESULT_KINDS = {"detailed", "brief", "conclusion_only"}
CONFIRMATION_STATEMENTS = {
    "确认没有更多内容", "没有更多内容", "无更多内容", "没有遗漏", "没有漏传", "已全部提供", "以上为全部", "确认完整",
    "我确认完整", "我确认没有更多内容", "材料已全部提供",
}
CANONICAL_CAPABILITIES = {"材料缺失判断准确性", "证据提取准确性", "过度推理", "审核条件与结论一致性", "规则维护质量"}
EVIDENCE_STATES = {"SUPPORTED", "CONTRADICTED", "NOT_FOUND", "INSUFFICIENT", "CONFLICTED", "NOT_APPLICABLE"}
CATEGORIES = {"材料缺失判断准确性", "证据提取准确性", "过度推理", "审核条件与结论一致性", "规则维护质量"}
ISSUE_CAPABILITY_BY_CATEGORY = {name: name for name in CATEGORIES}
SECTION_CATEGORIES = (("材料缺失复核", "材料缺失判断准确性"), ("证据准确性", "证据提取准确性"), ("过度推理", "过度推理"), ("条件一致性", "审核条件与结论一致性"), ("规则维护质量", "规则维护质量"))
RISK_LABELS = {"false_approval": "错误放行风险", "false_rejection": "错误拒绝风险", "both": "错误放行与错误拒绝风险", "none": "未发现明显风险"}
IMPACT_LABELS = {"changed": "已改变最终结论", "potentially_changed": "可能改变最终结论", "unchanged": "未改变最终结论", "unknown": "最终影响暂无法判断"}
_SENSITIVE_VALUE_RE = re.compile(
    r"\b(?:authorization\s*[:=]\s*)?bearer\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|\b(?:cookie|session(?:id)?)\s*[:=]\s*[A-Za-z0-9._~+/=-]{8,}",
    re.IGNORECASE,
)
_INLINE_ASSIGNMENT_KEY_RE = re.compile(
    r"""(?<![A-Za-z0-9_-])(?P<key>"[A-Za-z][A-Za-z0-9_-]*"|'[A-Za-z][A-Za-z0-9_-]*'|[A-Za-z][A-Za-z0-9_-]*)(?![A-Za-z0-9_-])\s*[:=]"""
)
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----",
    re.IGNORECASE,
)
_PLACEHOLDER_VALUES = {
    "",
    "null",
    "none",
    "***",
    "...",
    "redacted",
    "[redacted]",
    "<redacted>",
    "{{redacted}}",
    "placeholder",
    "[placeholder]",
    "<placeholder>",
    "{{placeholder}}",
}


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


def _sensitive_key_name(key):
    compact = re.sub(r"[^a-z0-9]", "", key.casefold())
    if compact in {
        "authorization",
        "cookie",
        "cookies",
        "sessionid",
        "jsessionid",
        "authsession",
        "loginsession",
        "password",
        "secret",
        "apikey",
        "accesstoken",
        "refreshtoken",
        "authtoken",
        "clientsecret",
        "privatekey",
        "awssecretaccesskey",
        "systemprompt",
        "systemconfig",
        "privatesystemprompt",
        "privatesystemconfig",
    }:
        return True
    return compact.endswith(("apikey", "token", "secret", "password", "privatekey"))


def _detection_normalize(value):
    """Fold only serialized quote escapes for detection; never mutate report data."""
    normalized = value
    for _ in range(4):
        folded = (
            normalized.replace(r"\u0022", '"')
            .replace(r"\u0027", "'")
            .replace(r'\"', '"')
            .replace(r"\'", "'")
        )
        if folded == normalized:
            break
        normalized = folded
    return normalized


def _placeholder_secret(value):
    if not isinstance(value, str):
        return False
    normalized = _detection_normalize(value).strip().casefold()
    return normalized in _PLACEHOLDER_VALUES


def _inline_assignment_value(tail):
    tail = tail.lstrip()
    if not tail:
        return ""
    if tail[0] in {"'", '"'}:
        closing = tail.find(tail[0], 1)
        return tail[1:] if closing < 0 else tail[1:closing]
    end = len(tail)
    for delimiter in (",", "}", "\r", "\n"):
        position = tail.find(delimiter)
        if position >= 0:
            end = min(end, position)
    return tail[:end].strip()


def _has_sensitive_inline_assignment(value):
    for match in _INLINE_ASSIGNMENT_KEY_RE.finditer(value):
        key = match.group("key").strip("'\"")
        if _sensitive_key_name(key) and not _placeholder_secret(
            _inline_assignment_value(value[match.end() :])
        ):
            return True
    return False


def _contains_suspected_secret(value, sensitive_context=False):
    if isinstance(value, dict):
        for key, item in value.items():
            key_is_sensitive = _sensitive_key_name(key)
            if _SENSITIVE_VALUE_RE.search(key):
                return True
            if key_is_sensitive:
                if item is not None and not _placeholder_secret(item):
                    return True
                continue
            if _contains_suspected_secret(item, sensitive_context or key_is_sensitive):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_suspected_secret(item, sensitive_context) for item in value)
    if not isinstance(value, str):
        return False
    detection_value = _detection_normalize(value)
    if _PRIVATE_KEY_BLOCK_RE.search(detection_value):
        return True
    if _SENSITIVE_VALUE_RE.search(detection_value):
        return True
    if _has_sensitive_inline_assignment(detection_value):
        return True
    return sensitive_context and not _placeholder_secret(detection_value)


def _reject_suspected_secrets(value):
    if _contains_suspected_secret(value):
        raise ValueError("qc_report_unsafe_input: suspected credential or secret in report input")


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


def _exact_object(value, path, fields):
    _object(value, path, fields)
    extra = set(value) - fields
    if extra:
        _error(path, f"unexpected field {sorted(extra)[0]}")


def _sha256(value, path):
    _text(value, path)
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        _error(path, "must be 64 lowercase hexadecimal characters")


def _canonical_sha256(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_raw_input_sha256(raw_input):
    """Hash the normalized canonical raw-input JSON bound to the inventory."""
    return _canonical_sha256(raw_input)


def compute_inventory_sha256(inventory):
    """Hash the canonical inventory JSON used by the post-inventory confirmation."""
    return _canonical_sha256(inventory)


def compute_independent_review_sha256(artifact):
    """Hash the frozen independent-review artifact before comparison."""
    return _canonical_sha256(artifact)


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
        if type(start) is not int or type(end) is not int or start < 0 or end < 0 or start >= end:
            _error(f"{point}.location", "start/end must be nonnegative integers with start < end")
        source = material_sources.get(item["materialId"])
        if source is not None and (end > len(source) or source[start:end] != item["rawText"]):
            _error(f"{point}.location", "must locate rawText in the source material")


def _material_sources(raw_input):
    if not isinstance(raw_input, dict) or not isinstance(raw_input.get("materials"), list):
        return {}
    sources = {}
    for item in raw_input["materials"]:
        if isinstance(item, dict) and isinstance(item.get("materialId"), str):
            if item["materialId"] in sources:
                _error("rawInput.materials", "materialId must be unique")
            sources[item["materialId"]] = item["content"] if isinstance(item.get("content"), str) else None
    return sources


def _validate_evidence_state(status, evidence, path):
    if status in {"SUPPORTED", "CONTRADICTED", "INSUFFICIENT", "CONFLICTED"} and not evidence:
        _error(path, "requires at least one materialEvidence")
    if status in {"NOT_FOUND", "NOT_APPLICABLE"} and evidence:
        _error(path, "requires empty materialEvidence")


def _validate_interpretation_paths(input_scope, qc_conclusion, recommended_action):
    """Validate outcome-changing natural-language interpretation alternatives."""
    if "interpretationPaths" not in input_scope:
        return
    paths = input_scope["interpretationPaths"]
    if not isinstance(paths, list) or len(paths) < 2:
        _error("inputScope.interpretationPaths", "must be an array with at least 2 paths")
    if input_scope["standardKind"] != "natural_language":
        _error("inputScope.standardKind", "must be natural_language when interpretationPaths is present")
    path_ids, final_results, shared_rule_codes = set(), [], None
    for index, path in enumerate(paths):
        point = f"inputScope.interpretationPaths[{index}]"
        required = {"pathId", "interpretation", "ruleResults", "finalResult"}
        _object(path, point, required)
        extra = set(path) - required
        if extra:
            _error(point, f"unexpected field {sorted(extra)[0]}")
        _text(path["pathId"], f"{point}.pathId")
        _text(path["interpretation"], f"{point}.interpretation")
        if path["pathId"] in path_ids:
            _error(f"{point}.pathId", "must be unique")
        path_ids.add(path["pathId"])
        if not isinstance(path["ruleResults"], list) or not path["ruleResults"]:
            _error(f"{point}.ruleResults", "must be a nonempty array")
        rule_codes = set()
        for rule_index, rule_result in enumerate(path["ruleResults"]):
            rule_point = f"{point}.ruleResults[{rule_index}]"
            _object(rule_result, rule_point, {"ruleCode", "result"})
            extra = set(rule_result) - {"ruleCode", "result"}
            if extra:
                _error(rule_point, f"unexpected field {sorted(extra)[0]}")
            _text(rule_result["ruleCode"], f"{rule_point}.ruleCode")
            _enum(rule_result["result"], f"{rule_point}.result", RULE_RESULTS)
            if rule_result["ruleCode"] in rule_codes:
                _error(f"{rule_point}.ruleCode", "must be unique within the interpretation path")
            rule_codes.add(rule_result["ruleCode"])
        if shared_rule_codes is None:
            shared_rule_codes = rule_codes
        elif rule_codes != shared_rule_codes:
            _error(f"{point}.ruleResults", "must use the same ruleCode set as every interpretation path")
        _enum(path["finalResult"], f"{point}.finalResult", RULE_RESULTS)
        final_results.append(path["finalResult"])
    if len(set(final_results)) == 1:
        _error("inputScope.interpretationPaths", "finalResult values must not all be identical")
    if qc_conclusion != "无法确定":
        _error("qcConclusion", "must be 无法确定 when interpretationPaths has different final results")
    if "人工确认" not in recommended_action:
        _error("recommendedAction", "must recommend 人工确认 when interpretationPaths has different final results")


def _valid_confirmation_statement(statement):
    normalized = statement.strip()
    grammar = "|".join(re.escape(item) for item in sorted(CONFIRMATION_STATEMENTS, key=len, reverse=True))
    return bool(re.fullmatch(rf"(?:{grammar})(?:了)?[。！.!]*", normalized))


def _validate_input_scope(input_scope, raw_input):
    required = {"confirmedByUser", "materials", "standardKind", "auditResultKind", "inventory", "confirmation", "independentReview"}
    allowed = required | {"interpretationPaths"}
    _object(input_scope, "inputScope", required)
    extra = set(input_scope) - allowed
    if extra:
        _error("inputScope", f"unexpected field {sorted(extra)[0]}")
    if type(input_scope["confirmedByUser"]) is not bool or not input_scope["confirmedByUser"]:
        _error("inputScope.confirmedByUser", "输入清单尚未得到用户确认；must be true before formal output")
    if not isinstance(input_scope["materials"], list):
        _error("inputScope.materials", "must be an array")
    for index, item in enumerate(input_scope["materials"]):
        _text(item, f"inputScope.materials[{index}]")
    _enum(input_scope["standardKind"], "inputScope.standardKind", STANDARD_KINDS)
    _enum(input_scope["auditResultKind"], "inputScope.auditResultKind", AUDIT_RESULT_KINDS)

    inventory_fields = {"revision", "materials", "standardKind", "auditResultKind", "hasAuditProcess", "hasFinalConclusion", "referencedButMissing", "rawInputSha256"}
    inventory = input_scope["inventory"]
    _exact_object(inventory, "inputScope.inventory", inventory_fields)
    if type(inventory["revision"]) is not int or inventory["revision"] <= 0:
        _error("inputScope.inventory.revision", "must be a positive integer")
    if not isinstance(inventory["materials"], list):
        _error("inputScope.inventory.materials", "must be an array")
    for index, item in enumerate(inventory["materials"]):
        _text(item, f"inputScope.inventory.materials[{index}]")
    if inventory["materials"] != input_scope["materials"]:
        _error("inputScope.inventory.materials", "must exactly match inputScope.materials")
    for field, choices in (("standardKind", STANDARD_KINDS), ("auditResultKind", AUDIT_RESULT_KINDS)):
        _enum(inventory[field], f"inputScope.inventory.{field}", choices)
        if inventory[field] != input_scope[field]:
            _error(f"inputScope.inventory.{field}", f"must match inputScope.{field}")
    if type(inventory["hasAuditProcess"]) is not bool:
        _error("inputScope.inventory.hasAuditProcess", "must be boolean")
    if inventory["hasFinalConclusion"] is not True:
        _error("inputScope.inventory.hasFinalConclusion", "must be true")
    if not isinstance(inventory["referencedButMissing"], list):
        _error("inputScope.inventory.referencedButMissing", "must be an array")
    for index, item in enumerate(inventory["referencedButMissing"]):
        _text(item, f"inputScope.inventory.referencedButMissing[{index}]")
    _sha256(inventory["rawInputSha256"], "inputScope.inventory.rawInputSha256")
    if inventory["rawInputSha256"] != compute_raw_input_sha256(raw_input):
        _error("inputScope.inventory.rawInputSha256", "must match report.rawInput")
    if input_scope["auditResultKind"] == "detailed" and not inventory["hasAuditProcess"]:
        _error("inputScope.inventory.hasAuditProcess", "must be true for detailed audit result")
    if input_scope["auditResultKind"] in {"brief", "conclusion_only"} and inventory["hasAuditProcess"]:
        _error("inputScope.inventory.hasAuditProcess", "must be false for brief or conclusion_only audit result")

    confirmation = input_scope["confirmation"]
    _exact_object(confirmation, "inputScope.confirmation", {"confirmedRevision", "inventorySha256", "userStatement", "outcome", "confirmedAfterInventory"})
    if type(confirmation["confirmedRevision"]) is not int or confirmation["confirmedRevision"] <= 0:
        _error("inputScope.confirmation.confirmedRevision", "must be a positive integer")
    if confirmation["confirmedRevision"] != inventory["revision"]:
        _error("inputScope.confirmation.confirmedRevision", "must match current inventory revision")
    _sha256(confirmation["inventorySha256"], "inputScope.confirmation.inventorySha256")
    if confirmation["inventorySha256"] != compute_inventory_sha256(inventory):
        _error("inputScope.confirmation.inventorySha256", "must match current inventory")
    _text(confirmation["userStatement"], "inputScope.confirmation.userStatement")
    if not _valid_confirmation_statement(confirmation["userStatement"]):
        _error("inputScope.confirmation.userStatement", "must explicitly confirm completeness after inventory")
    _enum(confirmation["outcome"], "inputScope.confirmation.outcome", {"confirmed_complete"})
    if confirmation["confirmedAfterInventory"] is not True:
        _error("inputScope.confirmation.confirmedAfterInventory", "must be true")

    independent = input_scope["independentReview"]
    _exact_object(independent, "inputScope.independentReview", {"mode", "completedBeforeComparison", "artifact", "artifactSha256"})
    _enum(independent["mode"], "inputScope.independentReview.mode", {"isolated_blind", "independent_non_blind"})
    if independent["completedBeforeComparison"] is not True:
        _error("inputScope.independentReview.completedBeforeComparison", "must be true")
    artifact = independent["artifact"]
    _exact_object(artifact, "inputScope.independentReview.artifact", {"materialFacts", "standardKind", "ruleResults", "finalResult"})
    if not isinstance(artifact["materialFacts"], list):
        _error("inputScope.independentReview.artifact.materialFacts", "must be an array")
    _enum(artifact["standardKind"], "inputScope.independentReview.artifact.standardKind", STANDARD_KINDS)
    if artifact["standardKind"] != input_scope["standardKind"]:
        _error("inputScope.independentReview.artifact.standardKind", "must match inputScope.standardKind")
    if not isinstance(artifact["ruleResults"], list):
        _error("inputScope.independentReview.artifact.ruleResults", "must be an array")
    artifact_rule_codes = set()
    for index, rule_result in enumerate(artifact["ruleResults"]):
        point = f"inputScope.independentReview.artifact.ruleResults[{index}]"
        _exact_object(rule_result, point, {"ruleCode", "result"})
        _text(rule_result["ruleCode"], f"{point}.ruleCode")
        _enum(rule_result["result"], f"{point}.result", RULE_RESULTS)
        if rule_result["ruleCode"] in artifact_rule_codes:
            _error(f"{point}.ruleCode", "must be unique")
        artifact_rule_codes.add(rule_result["ruleCode"])
    _enum(artifact["finalResult"], "inputScope.independentReview.artifact.finalResult", RULE_RESULTS)
    _sha256(independent["artifactSha256"], "inputScope.independentReview.artifactSha256")
    if independent["artifactSha256"] != compute_independent_review_sha256(artifact):
        _error("inputScope.independentReview.artifactSha256", "must match frozen artifact")


def _validate_capability_matrix(capabilities, input_scope, rule_reviews):
    by_name = {item["name"]: item for item in capabilities}
    if set(by_name) != CANONICAL_CAPABILITIES or len(by_name) != len(capabilities):
        _error("capabilities", "must contain each of the five canonical capability names exactly once")
    kind, audit_kind = input_scope["standardKind"], input_scope["auditResultKind"]
    if audit_kind == "conclusion_only":
        for name in ("材料缺失判断准确性", "证据提取准确性", "过度推理"):
            capability = by_name[name]
            if capability["status"] != "not_run":
                _error(f"capabilities.{name}", "must be not_run without detailed audit claims")
        if by_name["证据提取准确性"]["reason"] != "未提供原审核证据或规则过程":
            _error("capabilities.证据提取准确性.reason", "must be 未提供原审核证据或规则过程")
        condition = by_name["审核条件与结论一致性"]
        if kind == "absent" and condition["status"] != "not_run":
            _error("capabilities.审核条件与结论一致性", "must be not_run without a usable standard")
        if kind != "absent" and condition["status"] not in {"partial", "not_run"}:
            _error("capabilities.审核条件与结论一致性", "may only be partial or not_run for brief/conclusion_only")
        if rule_reviews:
            _error("ruleReviews", "must be empty for brief or conclusion_only audit result")
    if audit_kind == "brief":
        evidence = by_name["证据提取准确性"]
        if evidence["status"] != "not_run" or evidence["reason"] != "未提供原审核证据或规则过程":
            _error("capabilities.证据提取准确性", "must be not_run with reason 未提供原审核证据或规则过程 for brief")
        if by_name["审核条件与结论一致性"]["status"] != "not_run":
            _error("capabilities.审核条件与结论一致性", "must be not_run without detailed rule process")
        if rule_reviews:
            _error("ruleReviews", "must be empty for brief or conclusion_only audit result")
    if kind == "absent":
        if by_name["规则维护质量"]["status"] != "not_run":
            _error("capabilities.规则维护质量", "must be not_run when standardKind is absent")
        if rule_reviews:
            _error("ruleReviews", "must be empty when standardKind is absent")
        condition = by_name["审核条件与结论一致性"]
        if condition["status"] == "completed":
            _error("capabilities.审核条件与结论一致性", "cannot be completed when standardKind is absent")
        if audit_kind != "detailed" and condition["status"] != "not_run":
            _error("capabilities.审核条件与结论一致性", "must be not_run without detailed audit output")
    if kind == "structured_incomplete" and by_name["审核条件与结论一致性"]["status"] == "completed":
        _error("capabilities.审核条件与结论一致性", "cannot be completed when standardKind is structured_incomplete")
    if kind == "natural_language" and by_name["规则维护质量"]["status"] == "completed":
        _error("capabilities.规则维护质量", "cannot be completed when standardKind is natural_language")


def _validate_outcome_risk(report):
    changing = [item for item in report["issues"] if item["impactOnFinalResult"] in {"changed", "potentially_changed"}]
    if (
        report["riskDirection"] == "未发现明显风险"
        and any(item["severity"] in {"medium", "high"} for item in report["issues"])
    ):
        _error(
            "riskDirection",
            "cannot be 未发现明显风险 when medium/high issues exist; use a visible risk direction such as 局部判断错误",
        )
    if not changing:
        return
    if report["qcConclusion"] in {"可靠", "基本可靠"}:
        _error("qcConclusion", "cannot be reliable when an issue changes or may change the final result")
    for index, issue in enumerate(changing):
        if issue["riskDirection"] == "none":
            _error(f"issues[{index}].riskDirection", "cannot be none when final result changes or may change")
    directions = {item["riskDirection"] for item in changing}
    if directions == {"false_approval"}:
        expected = "错误放行风险"
    elif directions == {"false_rejection"}:
        expected = "错误拒绝风险"
    else:
        expected = "暂时无法判断"
    if report["riskDirection"] != expected:
        _error("riskDirection", f"must be {expected} for outcome-changing issue directions")


def _validate_independent_artifact_requirements(input_scope, capabilities_by_name):
    artifact = input_scope["independentReview"]["artifact"]
    if input_scope["standardKind"] == "absent":
        if artifact["ruleResults"]:
            _error("inputScope.independentReview.artifact.ruleResults", "must be empty when standardKind is absent")
        if artifact["finalResult"] != "无法判断":
            _error("inputScope.independentReview.artifact.finalResult", "must be 无法判断 when standardKind is absent")
    elif not artifact["ruleResults"] and capabilities_by_name["审核条件与结论一致性"]["status"] != "not_run":
        _error("inputScope.independentReview.artifact.ruleResults", "may be empty only when the condition capability is not_run")


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
    _validate_input_scope(report["inputScope"], report["rawInput"])
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
    _validate_interpretation_paths(report["inputScope"], report["qcConclusion"], report["recommendedAction"])
    material_sources = _material_sources(report["rawInput"])
    if not isinstance(report["issues"], list): _error("issues", "must be an array")
    issue_fields = {"category", "issueType", "severity", "ruleCode", "keywordCode", "modelClaim", "evidenceStatus", "materialEvidence", "qcFinding", "possibleImpact", "impactOnFinalResult", "riskDirection", "recommendation", "confidence"}
    optional_issue_fields = {"issueId", "relatedCapabilities"}
    issue_ids = set()
    for index, issue in enumerate(report["issues"]):
        point = f"issues[{index}]"; _object(issue, point, issue_fields)
        extra = set(issue) - issue_fields - optional_issue_fields
        if extra:
            _error(point, f"unexpected field {sorted(extra)[0]}")
        if "issueId" in issue:
            _text(issue["issueId"], f"{point}.issueId")
            if issue["issueId"] in issue_ids:
                _error(f"{point}.issueId", "must be unique")
            issue_ids.add(issue["issueId"])
        _enum(issue["category"], f"{point}.category", CATEGORIES); _text(issue["issueType"], f"{point}.issueType")
        if "relatedCapabilities" in issue:
            related = issue["relatedCapabilities"]
            if not isinstance(related, list):
                _error(f"{point}.relatedCapabilities", "must be an array")
            if len(related) != len(set(related)):
                _error(f"{point}.relatedCapabilities", "must not contain duplicates")
            for related_index, name in enumerate(related):
                _enum(name, f"{point}.relatedCapabilities[{related_index}]", CANONICAL_CAPABILITIES)
            if issue["category"] in related:
                _error(f"{point}.relatedCapabilities", "must not repeat the primary category")
        capability = capabilities_by_name.get(ISSUE_CAPABILITY_BY_CATEGORY[issue["category"]])
        if capability and capability["status"] == "not_run":
            _error(f"{point}.category", "cannot contain issues when its capability is not_run")
        if not isinstance(issue["ruleCode"], str):
            _error(f"{point}.ruleCode", "must be a string")
        for field in ("modelClaim", "qcFinding", "possibleImpact", "recommendation"):
            _text(issue[field], f"{point}.{field}")
        if not isinstance(issue["keywordCode"], str): _error(f"{point}.keywordCode", "must be a string")
        _enum(issue["severity"], f"{point}.severity", SEVERITIES); _enum(issue["confidence"], f"{point}.confidence", CONFIDENCES); _enum(issue["impactOnFinalResult"], f"{point}.impactOnFinalResult", IMPACTS); _enum(issue["riskDirection"], f"{point}.riskDirection", ISSUE_RISKS); _enum(issue["evidenceStatus"], f"{point}.evidenceStatus", EVIDENCE_STATES)
        if issue["impactOnFinalResult"] in {"changed", "potentially_changed"} and issue["severity"] != "high": _error(f"{point}.severity", "must be high when final result may change")
        _validate_evidence_state(issue["evidenceStatus"], issue["materialEvidence"], f"{point}.materialEvidence")
        _evidence(issue["materialEvidence"], f"{point}.materialEvidence", material_sources)
    if not isinstance(report["ruleReviews"], list): _error("ruleReviews", "must be an array")
    review_fields = {"ruleCode", "result", "modelClaim", "evidenceStatus", "materialEvidence", "qcFinding", "recommendation"}
    for index, review in enumerate(report["ruleReviews"]):
        point = f"ruleReviews[{index}]"; _object(review, point, review_fields)
        for field in ("ruleCode", "modelClaim", "qcFinding", "recommendation"): _text(review[field], f"{point}.{field}")
        _enum(review["result"], f"{point}.result", RULE_RESULTS); _enum(review["evidenceStatus"], f"{point}.evidenceStatus", EVIDENCE_STATES)
        _validate_evidence_state(review["evidenceStatus"], review["materialEvidence"], f"{point}.materialEvidence")
        _evidence(review["materialEvidence"], f"{point}.materialEvidence", material_sources)
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
    _validate_capability_matrix(report["capabilities"], report["inputScope"], report["ruleReviews"])
    _validate_independent_artifact_requirements(report["inputScope"], capabilities_by_name)
    _validate_outcome_risk(report)


def validate_qc_report(source):
    """Return a normalized deep copy, or raise a stable ValueError without mutation."""
    report = _json_safe(_load_source(source))
    _reject_suspected_secrets(report)
    try:
        json.dumps(report, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"qc_report_invalid: root: not JSON serializable: {exc}") from None
    _validate_report(report)
    return copy.deepcopy(report)


def _text_scalar(value):
    """Display a scalar as one JSON-quoted line, never as report structure."""
    displayed = _safe_text(str(value))
    for separator in ("\u0085", "\u2028", "\u2029"):
        displayed = displayed.replace(separator, f"\\u{ord(separator):04x}")
    return json.dumps(displayed, ensure_ascii=False)


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


def _interpretation_paths_text(paths):
    lines = ["解释路径："]
    for path in paths:
        results = "；".join(
            "规则：{}；结果：{}".format(
                _text_scalar(item["ruleCode"]), _text_scalar(item["result"])
            )
            for item in path["ruleResults"]
        ) or "无逐规则结果"
        lines.append(
            "- 路径：{}；解释：{}；最终结果：{}；{}".format(
                _text_scalar(path["pathId"]),
                _text_scalar(path["interpretation"]),
                _text_scalar(path["finalResult"]),
                results,
            )
        )
    return lines


def _attestation_text(scope):
    inventory, confirmation, independent = scope["inventory"], scope["confirmation"], scope["independentReview"]
    lines = [
        "输入清单修订：{}；清单摘要：{}；原始输入摘要：{}；用户确认：{}；确认结果：{}；清点后确认：{}".format(
            _text_scalar(inventory["revision"]),
            _text_scalar(confirmation["inventorySha256"]),
            _text_scalar(inventory["rawInputSha256"]),
            _text_scalar(confirmation["userStatement"]),
            _text_scalar(confirmation["outcome"]),
            _text_scalar(confirmation["confirmedAfterInventory"]),
        ),
        "审核引用但未提供：{}".format(_text_scalar("、".join(inventory["referencedButMissing"]) or "无")),
        "独立复核：模式：{}；比较前完成：{}；冻结产物摘要：{}".format(
            _text_scalar(independent["mode"]),
            _text_scalar(independent["completedBeforeComparison"]),
            _text_scalar(independent["artifactSha256"]),
        ),
        "冻结独立复核产物：{}".format(_text_scalar(json.dumps(independent["artifact"], ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False))),
    ]
    if independent["mode"] == "independent_non_blind":
        lines.append("限制：独立二次复核（非盲）；原审核结果已暴露或隔离不可用，存在确认偏差限制。")
    return lines


def render_qc_text(source):
    report = validate_qc_report(source)
    issue_groups = {category: [item for item in report["issues"] if item["category"] == category] for _, category in SECTION_CATEGORIES}
    changed = [item for item in report["issues"] if item["impactOnFinalResult"] in {"changed", "potentially_changed"}]
    lines = ["# 质控结论", f"结论：{_text_scalar(report['qcConclusion'])}", f"风险方向：{_text_scalar(report['riskDirection'])}", f"原审核结论：{_text_scalar(report['originalResult'])}", f"问题数量：{len(report['issues'])}", "", "# 输入与检查范围", "案例：{}／{}／{}".format(_text_scalar(report["case"]["patientName"]), _text_scalar(report["case"]["diseaseName"]), _text_scalar(report["case"]["auditId"])), "材料：{}".format(_text_scalar("、".join(report["inputScope"]["materials"]) or "无")), f"标准格式：{_text_scalar(report['inputScope']['standardKind'])}", f"审核结果类型：{_text_scalar(report['inputScope']['auditResultKind'])}"]
    if "interpretationPaths" in report["inputScope"]:
        lines += _interpretation_paths_text(report["inputScope"]["interpretationPaths"])
    lines += _attestation_text(report["inputScope"])
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


def _interpretation_paths_html(paths):
    cards = []
    for path in paths:
        results = ''.join(
            '<li>规则：{}；结果：{}</li>'.format(
                esc(item["ruleCode"]), esc(item["result"])
            )
            for item in path["ruleResults"]
        ) or '<li>无逐规则结果</li>'
        cards.append(
            '<article class="evidence"><h4>路径 {}</h4><dl><dt>解释</dt><dd>{}</dd>'
            '<dt>最终结果</dt><dd>{}</dd></dl><p class="label">逐规则结果</p><ul>{}</ul></article>'.format(
                esc(path["pathId"]), esc(path["interpretation"]), esc(path["finalResult"]), results
            )
        )
    return '<h3>解释路径</h3>' + ''.join(cards)


def _attestation_html(scope):
    inventory, confirmation, independent = scope["inventory"], scope["confirmation"], scope["independentReview"]
    fields = (
        ("输入清单修订", inventory["revision"]),
        ("清单摘要", confirmation["inventorySha256"]),
        ("原始输入摘要", inventory["rawInputSha256"]),
        ("用户确认", confirmation["userStatement"]),
        ("确认结果", confirmation["outcome"]),
        ("清点后确认", confirmation["confirmedAfterInventory"]),
        ("审核引用但未提供", "、".join(inventory["referencedButMissing"]) or "无"),
        ("独立复核模式", independent["mode"]),
        ("比较前完成", independent["completedBeforeComparison"]),
        ("冻结产物摘要", independent["artifactSha256"]),
    )
    rendered = '<div class="grid">' + ''.join(
        f'<div class="field"><b>{esc(label)}</b>{esc(value)}</div>' for label, value in fields
    ) + '</div>'
    if independent["mode"] == "independent_non_blind":
        rendered += '<p class="empty">限制：独立二次复核（非盲）；存在确认偏差限制。</p>'
    artifact = esc(json.dumps(independent["artifact"], ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False))
    rendered += '<details class="raw-data"><summary>冻结独立复核产物（已转义，仅供核对）</summary><pre>' + artifact + '</pre></details>'
    return rendered


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
    if "interpretationPaths" in report["inputScope"]:
        scope += _interpretation_paths_html(report["inputScope"]["interpretationPaths"])
    scope += '<h3>输入与独立复核证明</h3>' + _attestation_html(report["inputScope"])
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


def _collision_key(path):
    resolved = _canonical_path(path)
    parent = _canonical_path(resolved.parent)
    leaf = unicodedata.normalize("NFC", resolved.name).casefold()
    return unicodedata.normalize("NFC", str(parent / leaf)).casefold()


def _paths_collide(left, right):
    left, right = _canonical_path(left), _canonical_path(right)
    if left.exists() and right.exists():
        try:
            if os.path.samefile(left, right):
                return True
        except OSError:
            pass
    return _collision_key(left) == _collision_key(right)


def _reject_output_collisions(input_path, html_output, text_output=None):
    named = [("input", _canonical_path(input_path)), ("HTML output", _canonical_path(html_output))]
    if text_output is not None:
        named.append(("text output", _canonical_path(text_output)))
    for index, (name, path) in enumerate(named):
        for other_name, other_path in named[index + 1:]:
            if _paths_collide(path, other_path):
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
    except Exception as commit_error:
        rollback_errors = []
        for destination in reversed(committed):
            backup = backups.get(destination)
            try:
                if backup is not None:
                    os.replace(backup, destination)
                    backups.pop(destination, None)
                elif destination.exists():
                    destination.unlink()
            except OSError as exc:
                rollback_errors.append(f"{destination}: {exc}")
        if rollback_errors:
            detail = "; ".join(rollback_errors)
            raise OSError(f"{commit_error}; rollback failed; outputs may be inconsistent: {detail}") from commit_error
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
