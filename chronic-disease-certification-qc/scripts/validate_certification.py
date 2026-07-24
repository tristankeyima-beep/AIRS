#!/usr/bin/env python3
"""Validate and deterministically finalize chronic-disease certification standards."""

import argparse
import copy
import json
import re
import sys
from pathlib import Path


WRAPPER_KEYS = ("certification_list", "output", "result", "data")
FORMAL_ROOT_KEYS = frozenset(("meta", "ruleRepository", "logicTopology"))
META_KEYS = frozenset(("version", "chronicDiseaseName", "chronicDiseaseCode", "createdAt", "description", "sourceFile"))
RULE_KEYS = frozenset(("ruleCode", "ruleContent", "ruleSource", "experience", "sourceRuleContent", "sourceMdFile", "sourceSection", "ruleKeywordGuide"))
GUIDE_KEYS = frozenset(("keywordCode", "dataType", "required", "keywordContent", "enumOptions"))
GROUP_KEYS = frozenset(("type", "operator", "children"))
RULE_REF_KEYS = frozenset(("type", "ruleCode"))
MAX_WRAPPER_DEPTH = 32
MAX_TOPOLOGY_DEPTH = 64
MAX_CODE_SEQUENCE = 999
_DISEASE_CODE_RE = re.compile(r".*\d{2}$")
_TEMP_RULE_ID_RE = re.compile(r"R\d{3}$")


class ParseError(ValueError):
    """A JSON or wrapper parsing error with a stable issue code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def issue(path, code, message, severity="error"):
    """Create one serializable validation issue."""
    return {"path": path, "code": code, "message": message, "severity": severity}


def parse_value(value):
    """Load a Path, JSON string, object, or compatible nested wrapper."""
    if isinstance(value, Path):
        try:
            value = value.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ParseError("input_decode_error", "Input must be UTF-8 JSON.") from exc
        except OSError as exc:
            raise ParseError("input_read_error", str(exc)) from exc
    if isinstance(value, str):
        value = value.removeprefix("\ufeff")
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ParseError("invalid_json", "Input is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ParseError("invalid_root", "Certification standard root must be an object.")

    seen_wrappers = []
    wrapper_depth = 0
    while True:
        if not isinstance(value, dict):
            raise ParseError("invalid_root", "Wrapped certification standard must be an object.")
        if FORMAL_ROOT_KEYS.intersection(value):
            return value
        wrapper_key = next((key for key in WRAPPER_KEYS if key in value), None)
        if wrapper_key is None:
            return value
        if any(value is seen_wrapper for seen_wrapper in seen_wrappers):
            raise ParseError("wrapper_cycle", "Wrapper nesting contains a cycle.")
        if wrapper_depth >= MAX_WRAPPER_DEPTH:
            raise ParseError("wrapper_depth_exceeded", "Wrapper nesting exceeds the supported depth.")
        seen_wrappers.append(value)
        wrapper_depth += 1
        value = value[wrapper_key]
        if isinstance(value, str):
            value = value.removeprefix("\ufeff")
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ParseError("invalid_json", "Input is not valid JSON.") from exc


def _required_string(value, path, errors, nonempty=True):
    if not isinstance(value, str):
        errors.append(issue(path, "invalid_type", "Expected a string."))
        return
    if nonempty and not value.strip():
        errors.append(issue(path, "required_string", "Expected a nonempty string."))


def _reject_unknown_fields(value, allowed_keys, path, errors):
    for field in sorted(set(value) - allowed_keys, key=str):
        field_path = f"{path}.{field}" if path else str(field)
        errors.append(issue(field_path, "unknown_field", "Field is not declared by the formal contract."))


def _validate_meta(meta, errors):
    if not isinstance(meta, dict):
        errors.append(issue("meta", "invalid_type", "Expected an object."))
        return
    _reject_unknown_fields(meta, META_KEYS, "meta", errors)
    for field in (
        "version",
        "chronicDiseaseName",
        "chronicDiseaseCode",
        "createdAt",
        "description",
        "sourceFile",
    ):
        _required_string(meta.get(field), "meta." + field, errors)
    disease_code = meta.get("chronicDiseaseCode")
    if isinstance(disease_code, str) and disease_code.strip() and not _DISEASE_CODE_RE.fullmatch(disease_code):
        errors.append(issue("meta.chronicDiseaseCode", "invalid_disease_code", "Disease code must end in two digits."))


def _validate_guides(guides, rule_path, errors, keyword_codes):
    path = rule_path + ".ruleKeywordGuide"
    if not isinstance(guides, list):
        errors.append(issue(path, "invalid_type", "Expected a list."))
        return
    if not guides:
        errors.append(issue(path, "keyword_guide_required", "At least one keyword guide is required."))
        return
    for index, guide in enumerate(guides):
        guide_path = f"{path}[{index}]"
        if not isinstance(guide, dict):
            errors.append(issue(guide_path, "invalid_type", "Expected an object."))
            continue
        _reject_unknown_fields(guide, GUIDE_KEYS, guide_path, errors)
        keyword_code = guide.get("keywordCode")
        _required_string(keyword_code, guide_path + ".keywordCode", errors)
        if isinstance(keyword_code, str) and keyword_code.strip():
            if keyword_code in keyword_codes:
                errors.append(issue(guide_path + ".keywordCode", "duplicate_keyword_code", "keywordCode must be unique."))
            keyword_codes.add(keyword_code)
        data_type = guide.get("dataType")
        if data_type not in ("enum", "string"):
            errors.append(issue(guide_path + ".dataType", "invalid_data_type", "dataType must be enum or string."))
        if not isinstance(guide.get("required"), bool):
            errors.append(issue(guide_path + ".required", "invalid_type", "required must be a boolean."))
        _required_string(guide.get("keywordContent"), guide_path + ".keywordContent", errors)
        options = guide.get("enumOptions")
        options_path = guide_path + ".enumOptions"
        if data_type == "enum":
            if not isinstance(options, list) or not options or any(not isinstance(option, str) or not option.strip() for option in options):
                errors.append(issue(options_path, "enum_options_required", "enumOptions must be a nonempty list of nonempty strings for enum guides."))
        elif data_type == "string":
            if options != []:
                errors.append(issue(options_path, "string_enum_options_must_be_empty", "enumOptions must be [] for string guides."))


def _validate_rules(rules, errors):
    rule_codes = set()
    if not isinstance(rules, list):
        errors.append(issue("ruleRepository", "invalid_type", "Expected a list."))
        return rule_codes
    if not rules:
        errors.append(issue("ruleRepository", "rule_repository_required", "At least one rule is required."))
        return rule_codes
    keyword_codes = set()
    for index, rule in enumerate(rules):
        path = f"ruleRepository[{index}]"
        if not isinstance(rule, dict):
            errors.append(issue(path, "invalid_type", "Expected an object."))
            continue
        _reject_unknown_fields(rule, RULE_KEYS, path, errors)
        rule_code = rule.get("ruleCode")
        _required_string(rule_code, path + ".ruleCode", errors)
        if isinstance(rule_code, str) and rule_code.strip():
            if rule_code in rule_codes:
                errors.append(issue(path + ".ruleCode", "duplicate_rule_code", "ruleCode must be unique."))
            rule_codes.add(rule_code)
        for field in ("ruleContent", "ruleSource", "experience", "sourceRuleContent", "sourceMdFile", "sourceSection"):
            _required_string(rule.get(field), path + "." + field, errors, nonempty=field in ("ruleContent", "sourceRuleContent"))
        _validate_guides(rule.get("ruleKeywordGuide"), path, errors, keyword_codes)
    return rule_codes


def _validate_topology(root, path, errors, rule_codes, references):
    stack = [(root, path, 0, frozenset())]
    while stack:
        node, node_path, depth, ancestors = stack.pop()
        if depth > MAX_TOPOLOGY_DEPTH:
            errors.append(issue(node_path, "topology_depth_exceeded", "Topology exceeds the supported depth."))
            continue
        if not isinstance(node, dict):
            errors.append(issue(node_path, "invalid_type", "Topology node must be an object."))
            continue
        node_id = id(node)
        if node_id in ancestors:
            errors.append(issue(node_path, "topology_cycle", "Topology must not contain a cycle."))
            continue
        child_ancestors = ancestors | {node_id}
        node_type = node.get("type")
        if node_type == "GROUP":
            _reject_unknown_fields(node, GROUP_KEYS, node_path, errors)
            if node.get("operator") not in ("AND", "OR"):
                errors.append(issue(node_path + ".operator", "invalid_operator", "GROUP operator must be AND or OR."))
            children = node.get("children")
            if not isinstance(children, list) or not children:
                errors.append(issue(node_path + ".children", "children_required", "GROUP must have nonempty children."))
                continue
            for index in reversed(range(len(children))):
                stack.append((children[index], f"{node_path}.children[{index}]", depth + 1, child_ancestors))
        elif node_type == "RULE_REF":
            _reject_unknown_fields(node, RULE_REF_KEYS, node_path, errors)
            code = node.get("ruleCode")
            _required_string(code, node_path + ".ruleCode", errors)
            if isinstance(code, str) and code.strip():
                if code not in rule_codes:
                    errors.append(issue(node_path + ".ruleCode", "unknown_rule_reference", "RULE_REF must reference an existing ruleCode."))
                elif code in references:
                    errors.append(issue(node_path + ".ruleCode", "duplicate_rule_reference", "Each rule may be referenced only once."))
                references.add(code)
        else:
            _reject_unknown_fields(node, frozenset(("type",)), node_path, errors)
            errors.append(issue(node_path + ".type", "invalid_topology_node", "Topology node type must be GROUP or RULE_REF."))


def validate_certification(value):
    """Return a safe, serializable validation result for any supported input."""
    try:
        standard = parse_value(value)
    except ParseError as exc:
        errors = [issue("$", exc.code, str(exc))]
        return {"valid": False, "errors": errors, "warnings": [], "standard": None}

    errors = []
    _reject_unknown_fields(standard, FORMAL_ROOT_KEYS, "", errors)
    _validate_meta(standard.get("meta"), errors)
    rule_codes = _validate_rules(standard.get("ruleRepository"), errors)
    references = set()
    _validate_topology(standard.get("logicTopology"), "logicTopology", errors, rule_codes, references)
    for rule_code in sorted(rule_codes - references):
        errors.append(issue("logicTopology", "unreferenced_rule", f"Rule {rule_code} is not referenced by logicTopology."))
    try:
        json.dumps(standard, ensure_ascii=False)
    except (TypeError, ValueError, RecursionError):
        standard = None
    return {"valid": not errors, "errors": errors, "warnings": [], "standard": standard}


def _guard_topology(root):
    """Reject cyclic or over-deep topology before any recursive copying occurs."""
    stack = [(root, 0, frozenset())]
    while stack:
        node, depth, ancestors = stack.pop()
        if depth > MAX_TOPOLOGY_DEPTH:
            raise ValueError("Topology exceeds the supported depth")
        if not isinstance(node, dict):
            continue
        node_id = id(node)
        if node_id in ancestors:
            raise ValueError("Topology must not contain a cycle")
        if node.get("type") == "GROUP":
            children = node.get("children")
            if isinstance(children, list):
                child_ancestors = ancestors | {node_id}
                for child in reversed(children):
                    stack.append((child, depth + 1, child_ancestors))


def _rewrite_topology(root, rule_codes):
    stack = [(root, 0, frozenset())]
    while stack:
        node, depth, ancestors = stack.pop()
        if depth > MAX_TOPOLOGY_DEPTH:
            raise ValueError("Topology exceeds the supported depth")
        if not isinstance(node, dict):
            continue
        node_id = id(node)
        if node_id in ancestors:
            raise ValueError("Topology must not contain a cycle")
        child_ancestors = ancestors | {node_id}
        if node.get("type") == "RULE_REF":
            old_code = node.get("ruleCode")
            if old_code not in rule_codes:
                raise ValueError(f"Unknown temp rule reference: {old_code}")
            node["ruleCode"] = rule_codes[old_code]
        elif node.get("type") == "GROUP":
            children = node.get("children")
            if isinstance(children, list):
                for child in reversed(children):
                    stack.append((child, depth + 1, child_ancestors))


def finalize_certification(draft_value, meta):
    """Turn temporary R001-style draft identifiers into deterministic formal codes."""
    draft_input = parse_value(draft_value)
    if isinstance(draft_input, dict):
        _guard_topology(draft_input.get("logicTopology"))
    try:
        draft = copy.deepcopy(draft_input)
        output_meta = copy.deepcopy(meta)
    except RecursionError as exc:
        raise ValueError("Draft or meta is too deeply nested") from exc
    if not isinstance(output_meta, dict):
        raise ValueError("meta must be an object")
    disease_code = output_meta.get("chronicDiseaseCode")
    if not isinstance(disease_code, str) or not _DISEASE_CODE_RE.fullmatch(disease_code):
        raise ValueError("meta.chronicDiseaseCode must end in two digits")
    rules = draft.get("ruleRepository")
    if not isinstance(rules, list):
        raise ValueError("draft.ruleRepository must be a list")
    if len(rules) > MAX_CODE_SEQUENCE:
        raise ValueError("ruleRepository may not contain more than 999 rules")

    prefix = disease_code[-2:]
    code_by_temp_id = {}
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise ValueError("Each draft rule must be an object")
        temp_rule_id = rule.get("tempRuleId")
        if not isinstance(temp_rule_id, str) or not _TEMP_RULE_ID_RE.fullmatch(temp_rule_id):
            raise ValueError("tempRuleId must match R followed by three digits")
        if temp_rule_id in code_by_temp_id:
            raise ValueError("tempRuleId must be unique")
        guides = rule.get("ruleKeywordGuide")
        if not isinstance(guides, list):
            raise ValueError("ruleKeywordGuide must be a list")
        if len(guides) > MAX_CODE_SEQUENCE:
            raise ValueError("ruleKeywordGuide may not contain more than 999 guides")
        rule_code = f"{prefix}{index:03d}"
        code_by_temp_id[temp_rule_id] = rule_code
        rule["ruleCode"] = rule_code
        rule.pop("tempRuleId", None)
        for guide_index, guide in enumerate(guides, start=1):
            if not isinstance(guide, dict):
                raise ValueError("Each keyword guide must be an object")
            guide["keywordCode"] = f"{rule_code}{guide_index:03d}"

    topology = copy.deepcopy(draft.get("logicTopology"))
    _rewrite_topology(topology, code_by_temp_id)
    standard = {"meta": output_meta, "ruleRepository": rules, "logicTopology": topology}
    result = validate_certification(standard)
    if not result["valid"]:
        raise ValueError(json.dumps(result["errors"], ensure_ascii=False))
    return standard


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate a formal standard")
    validate_parser.add_argument("input", type=Path)
    finalize_parser = subparsers.add_parser("finalize", help="finalize a draft standard")
    finalize_parser.add_argument("draft", type=Path)
    finalize_parser.add_argument("meta", type=Path)
    finalize_parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)

    if args.command == "validate":
        result = validate_certification(args.input)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 1
    try:
        meta = parse_value(args.meta)
        standard = finalize_certification(args.draft, meta)
    except (ParseError, ValueError) as exc:
        parser.error(str(exc))
    try:
        args.output.write_text(json.dumps(standard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"output_error: {exc}", file=sys.stderr)
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
