#!/usr/bin/env python3
"""Validate and deterministically finalize chronic-disease certification standards."""

import argparse
import copy
import json
import re
from pathlib import Path


WRAPPER_KEYS = ("certification_list", "output", "result", "data")
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
            value = value.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ParseError("input_decode_error", "Input must be UTF-8 JSON.") from exc
        except OSError as exc:
            raise ParseError("input_read_error", str(exc)) from exc
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ParseError("invalid_json", "Input is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ParseError("invalid_root", "Certification standard root must be an object.")

    while isinstance(value, dict):
        wrapper_key = next((key for key in WRAPPER_KEYS if key in value), None)
        if wrapper_key is None:
            break
        value = value[wrapper_key]
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ParseError("invalid_json", "Input is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ParseError("invalid_root", "Wrapped certification standard must be an object.")
    return value


def _required_string(value, path, errors, nonempty=True):
    if not isinstance(value, str):
        errors.append(issue(path, "invalid_type", "Expected a string."))
        return
    if nonempty and not value.strip():
        errors.append(issue(path, "required_string", "Expected a nonempty string."))


def _validate_meta(meta, errors):
    if not isinstance(meta, dict):
        errors.append(issue("meta", "invalid_type", "Expected an object."))
        return
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


def _validate_topology(node, path, errors, rule_codes, references):
    if not isinstance(node, dict):
        errors.append(issue(path, "invalid_type", "Topology node must be an object."))
        return
    node_type = node.get("type")
    if node_type == "GROUP":
        if node.get("operator") not in ("AND", "OR"):
            errors.append(issue(path + ".operator", "invalid_operator", "GROUP operator must be AND or OR."))
        children = node.get("children")
        if not isinstance(children, list) or not children:
            errors.append(issue(path + ".children", "children_required", "GROUP must have nonempty children."))
            return
        for index, child in enumerate(children):
            _validate_topology(child, f"{path}.children[{index}]", errors, rule_codes, references)
    elif node_type == "RULE_REF":
        code = node.get("ruleCode")
        _required_string(code, path + ".ruleCode", errors)
        if isinstance(code, str) and code.strip():
            if code not in rule_codes:
                errors.append(issue(path + ".ruleCode", "unknown_rule_reference", "RULE_REF must reference an existing ruleCode."))
            elif code in references:
                errors.append(issue(path + ".ruleCode", "duplicate_rule_reference", "Each rule may be referenced only once."))
            references.add(code)
    else:
        errors.append(issue(path + ".type", "invalid_topology_node", "Topology node type must be GROUP or RULE_REF."))


def validate_certification(value):
    """Return a safe, serializable validation result for any supported input."""
    try:
        standard = parse_value(value)
    except ParseError as exc:
        errors = [issue("$", exc.code, str(exc))]
        return {"valid": False, "errors": errors, "warnings": [], "standard": None}

    errors = []
    _validate_meta(standard.get("meta"), errors)
    rule_codes = _validate_rules(standard.get("ruleRepository"), errors)
    references = set()
    _validate_topology(standard.get("logicTopology"), "logicTopology", errors, rule_codes, references)
    for rule_code in sorted(rule_codes - references):
        errors.append(issue("logicTopology", "unreferenced_rule", f"Rule {rule_code} is not referenced by logicTopology."))
    return {"valid": not errors, "errors": errors, "warnings": [], "standard": standard}


def _rewrite_topology(node, rule_codes):
    if not isinstance(node, dict):
        return
    if node.get("type") == "RULE_REF":
        old_code = node.get("ruleCode")
        if old_code not in rule_codes:
            raise ValueError(f"Unknown temp rule reference: {old_code}")
        node["ruleCode"] = rule_codes[old_code]
    elif node.get("type") == "GROUP":
        for child in node.get("children", []):
            _rewrite_topology(child, rule_codes)


def finalize_certification(draft_value, meta):
    """Turn temporary R001-style draft identifiers into deterministic formal codes."""
    draft = copy.deepcopy(parse_value(draft_value))
    output_meta = copy.deepcopy(meta)
    if not isinstance(output_meta, dict):
        raise ValueError("meta must be an object")
    disease_code = output_meta.get("chronicDiseaseCode")
    if not isinstance(disease_code, str) or not _DISEASE_CODE_RE.fullmatch(disease_code):
        raise ValueError("meta.chronicDiseaseCode must end in two digits")
    rules = draft.get("ruleRepository")
    if not isinstance(rules, list):
        raise ValueError("draft.ruleRepository must be a list")

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
        rule_code = f"{prefix}{index:03d}"
        code_by_temp_id[temp_rule_id] = rule_code
        rule["ruleCode"] = rule_code
        rule.pop("tempRuleId", None)
        guides = rule.get("ruleKeywordGuide")
        if not isinstance(guides, list):
            raise ValueError("ruleKeywordGuide must be a list")
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
    args.output.write_text(json.dumps(standard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
