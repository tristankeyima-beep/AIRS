#!/usr/bin/env python3
"""Classify certification-standard input before quality-control processing."""

import argparse
import importlib.util
import json
import re
from pathlib import Path


_VALIDATOR_PATH = Path(__file__).with_name("validate_certification.py")
_VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "_certification_validator", _VALIDATOR_PATH
)
_VALIDATOR = importlib.util.module_from_spec(_VALIDATOR_SPEC)
_VALIDATOR_SPEC.loader.exec_module(_VALIDATOR)
_WRAPPER_KEYS = _VALIDATOR.WRAPPER_KEYS
_FORMAL_ROOT_KEYS = _VALIDATOR.FORMAL_ROOT_KEYS
_MAX_WRAPPER_DEPTH = _VALIDATOR.MAX_WRAPPER_DEPTH
_BRACKET_HEADING_RE = re.compile(r"^\s*\[[^\]\r\n]*[\u4e00-\u9fff][^\]\r\n]*\]\s*\r?\n")


class _NormalizationError(ValueError):
    """A controlled input-adapter error with a validator-compatible code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _issue(code, message):
    return {"path": "$", "code": code, "message": message, "severity": "error"}


def _path_issue(path, code, message, severity="error"):
    return {"path": path, "code": code, "message": message, "severity": severity}


def _blank_string(value):
    return isinstance(value, str) and not value.strip()


def _json_looking(value):
    """Only leading JSON containers turn text into a structured-input attempt."""
    return isinstance(value, str) and value.lstrip().startswith(("{", "["))


def _strip_bom(value):
    return value.removeprefix("\ufeff")


def _bracketed_chinese_heading(value):
    """Recognize a common Markdown heading without stealing JSON arrays."""
    return isinstance(value, str) and bool(_BRACKET_HEADING_RE.match(value))


def _decode_json(value):
    try:
        return _VALIDATOR.decode_json_text(value)
    except _VALIDATOR.ParseError as exc:
        raise _NormalizationError(exc.code, str(exc)) from exc
    except RecursionError as exc:
        raise _NormalizationError("invalid_json", "Input is not valid JSON.") from exc


def _unwrap(value):
    """Safely normalize compatible wrappers into a structured or text payload."""
    seen_wrappers = set()
    depth = 0
    while True:
        if isinstance(value, dict):
            if _FORMAL_ROOT_KEYS.intersection(value):
                return "structured", value
            wrapper_key = next((key for key in _WRAPPER_KEYS if key in value), None)
            if wrapper_key is None:
                return "structured", value
            value_id = id(value)
            if value_id in seen_wrappers:
                raise _NormalizationError("wrapper_cycle", "Wrapper nesting contains a cycle.")
            if depth >= _MAX_WRAPPER_DEPTH:
                raise _NormalizationError(
                    "wrapper_depth_exceeded", "Wrapper nesting exceeds the supported depth."
                )
            seen_wrappers.add(value_id)
            depth += 1
            value = value[wrapper_key]
            continue
        if isinstance(value, str):
            value = _strip_bom(value)
            if _blank_string(value):
                return "absent", None
            # A wrapper may hold an object JSON string or a JSON-string-encoded
            # natural-language standard. Ordinary text is never decoded.
            if value.lstrip().startswith("["):
                try:
                    value = _decode_json(value)
                except _NormalizationError:
                    if _bracketed_chinese_heading(value):
                        return "natural_language", value
                    raise
                if depth >= _MAX_WRAPPER_DEPTH:
                    raise _NormalizationError(
                        "wrapper_depth_exceeded", "Wrapper nesting exceeds the supported depth."
                    )
                depth += 1
                continue
            if value.lstrip().startswith(("{", '"')):
                value = _decode_json(value)
                if depth >= _MAX_WRAPPER_DEPTH:
                    raise _NormalizationError(
                        "wrapper_depth_exceeded", "Wrapper nesting exceeds the supported depth."
                    )
                depth += 1
                continue
            return "natural_language", value
        return "structured", value


def _normalize(value):
    if isinstance(value, Path):
        try:
            value = value.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise _NormalizationError("input_decode_error", "Input must be UTF-8 JSON.") from exc
        except OSError as exc:
            raise _NormalizationError("input_read_error", str(exc)) from exc
    if value is None or _blank_string(value):
        return "absent", None
    if isinstance(value, str):
        value = _strip_bom(value)
        if value.lstrip().startswith("["):
            try:
                return _unwrap(_decode_json(value))
            except _NormalizationError:
                if _bracketed_chinese_heading(value):
                    return "natural_language", value
                raise
        if not _json_looking(value):
            return "natural_language", value
        return _unwrap(_decode_json(value))
    return _unwrap(value)


def _rule_completeness(standard):
    """Return semantic-review availability and source traceability without mutation."""
    if not isinstance(standard, dict):
        return False, False
    rules = standard.get("ruleRepository")
    if not isinstance(rules, list) or not rules:
        return False, False
    traceable = all(
        isinstance(rule, dict)
        and isinstance(rule.get("sourceRuleContent"), str)
        and bool(rule["sourceRuleContent"].strip())
        for rule in rules
    )
    return True, traceable


def _result(kind, structural, executable, traceable, issues, warnings, semantic_review_available):
    """Produce the entire public, JSON-serializable inspection contract."""
    return {
        "kind": kind,
        "completeness": {
            "structural": structural,
            "executable": executable,
            "traceable": traceable,
            "source_consistent": None,
        },
        "issues": issues,
        "warnings": warnings,
        "semantic_review_available": semantic_review_available,
    }


def _validate(value):
    """Contain unexpected parser-depth failures in a stable inspection response."""
    try:
        return _VALIDATOR.validate_certification(value)
    except (RecursionError, TypeError, ValueError) as exc:
        return {
            "valid": False,
            "errors": [_issue("inspection_error", str(exc) or "Input could not be inspected.")],
            "warnings": [],
            "standard": None,
        }


def _rule_code_scheme(code):
    if code.isdigit():
        return f"numeric:{len(code)}"
    return "pattern:" + "".join(
        "A" if char.isalpha() else "0" if char.isdigit() else char
        for char in code
    )


def _qc_traceable_rule(rule):
    return any(
        isinstance(rule.get(field), str) and bool(rule[field].strip())
        for field in ("sourceRuleContent", "ruleSource")
    )


def _validate_qc_topology(topology, rule_codes):
    errors = []
    references = set()
    if not isinstance(topology, dict):
        return [
            _path_issue(
                "logicTopology",
                "logic_topology_required",
                "A structured standard requires a parseable logicTopology.",
            )
        ]
    stack = [(topology, "logicTopology", 0, frozenset())]
    while stack:
        node, path, depth, ancestors = stack.pop()
        if depth > _MAX_WRAPPER_DEPTH:
            errors.append(
                _path_issue(path, "topology_depth_exceeded", "Logic topology is too deep.")
            )
            continue
        if not isinstance(node, dict):
            errors.append(_path_issue(path, "invalid_logic_node", "Logic node must be an object."))
            continue
        identity = id(node)
        if identity in ancestors:
            errors.append(_path_issue(path, "topology_cycle", "Logic topology contains a cycle."))
            continue
        node_type = node.get("type")
        if node_type == "RULE_REF":
            code = node.get("ruleCode")
            if not isinstance(code, str) or not code.strip():
                errors.append(
                    _path_issue(f"{path}.ruleCode", "rule_reference_required", "RULE_REF requires a nonempty ruleCode.")
                )
            elif code not in rule_codes:
                errors.append(
                    _path_issue(f"{path}.ruleCode", "unknown_rule_reference", "RULE_REF must reference an existing ruleCode.")
                )
            elif code in references:
                errors.append(
                    _path_issue(f"{path}.ruleCode", "duplicate_rule_reference", "Each rule may be referenced only once.")
                )
            else:
                references.add(code)
            continue
        if node_type != "GROUP":
            errors.append(
                _path_issue(f"{path}.type", "invalid_logic_node_type", "Logic node type must be GROUP or RULE_REF.")
            )
            continue
        if node.get("operator") not in {"AND", "OR"}:
            errors.append(
                _path_issue(f"{path}.operator", "invalid_logic_operator", "GROUP operator must be AND or OR.")
            )
        children = node.get("children")
        if not isinstance(children, list) or not children:
            errors.append(
                _path_issue(f"{path}.children", "logic_children_required", "GROUP requires at least one child.")
            )
            continue
        next_ancestors = ancestors | {identity}
        for index in range(len(children) - 1, -1, -1):
            stack.append((children[index], f"{path}.children[{index}]", depth + 1, next_ancestors))
    for code in sorted(rule_codes - references):
        errors.append(
            _path_issue("logicTopology", "unreferenced_rule", f"ruleCode {code!r} is not referenced by logicTopology.")
        )
    return errors


def _validate_qc_standard(standard):
    if not isinstance(standard, dict):
        return _result(
            "structured_incomplete",
            False,
            False,
            False,
            [_path_issue("$", "invalid_root", "Structured standard must be an object.")],
            [],
            False,
        )
    rules = standard.get("ruleRepository")
    if not isinstance(rules, list) or not rules:
        return _result(
            "structured_incomplete",
            False,
            False,
            False,
            [_path_issue("ruleRepository", "rule_repository_required", "At least one rule is required.")],
            [],
            False,
        )

    errors = []
    warnings = []
    rule_codes = set()
    schemes = set()
    keyword_codes = set()
    traceable = True
    semantic_review_available = False
    for index, rule in enumerate(rules):
        path = f"ruleRepository[{index}]"
        if not isinstance(rule, dict):
            errors.append(_path_issue(path, "invalid_rule", "Rule must be an object."))
            traceable = False
            continue
        code = rule.get("ruleCode")
        if not isinstance(code, str) or not code.strip():
            errors.append(_path_issue(f"{path}.ruleCode", "rule_code_required", "ruleCode must be a nonempty string."))
        else:
            if code in rule_codes:
                errors.append(_path_issue(f"{path}.ruleCode", "duplicate_rule_code", "ruleCode must be unique."))
            rule_codes.add(code)
            schemes.add(_rule_code_scheme(code))
        content = rule.get("ruleContent")
        if not isinstance(content, str) or not content.strip():
            errors.append(_path_issue(f"{path}.ruleContent", "rule_content_required", "ruleContent must be nonempty."))
        else:
            semantic_review_available = True
        guides = rule.get("ruleKeywordGuide")
        if not isinstance(guides, list) or not guides:
            errors.append(
                _path_issue(f"{path}.ruleKeywordGuide", "keyword_guide_required", "At least one keyword guide is required.")
            )
        else:
            for guide_index, guide in enumerate(guides):
                guide_path = f"{path}.ruleKeywordGuide[{guide_index}]"
                if not isinstance(guide, dict):
                    errors.append(_path_issue(guide_path, "invalid_keyword_guide", "Keyword guide must be an object."))
                    continue
                keyword_content = guide.get("keywordContent")
                if not isinstance(keyword_content, str) or not keyword_content.strip():
                    errors.append(
                        _path_issue(f"{guide_path}.keywordContent", "keyword_content_required", "keywordContent must be nonempty.")
                    )
                keyword_code = guide.get("keywordCode")
                if keyword_code is None:
                    warnings.append(
                        _path_issue(
                            f"{guide_path}.keywordCode",
                            "keyword_code_missing",
                            "keywordCode is absent; the guide remains usable for semantic QC.",
                            "warning",
                        )
                    )
                elif not isinstance(keyword_code, str) or not keyword_code.strip():
                    errors.append(
                        _path_issue(f"{guide_path}.keywordCode", "invalid_keyword_code", "keywordCode must be a nonempty string when provided.")
                    )
                elif keyword_code in keyword_codes:
                    errors.append(
                        _path_issue(f"{guide_path}.keywordCode", "duplicate_keyword_code", "keywordCode must be unique when provided.")
                    )
                else:
                    keyword_codes.add(keyword_code)
        traceable = traceable and _qc_traceable_rule(rule)

    if len(schemes) > 1:
        errors.append(
            _path_issue(
                "ruleRepository",
                "mixed_rule_code_scheme",
                "All ruleCode values in one standard must use one consistent format.",
            )
        )
    errors.extend(_validate_qc_topology(standard.get("logicTopology"), rule_codes))

    canonical = _validate(standard)
    if not canonical.get("valid"):
        warnings.insert(
            0,
            _path_issue(
                "$",
                "noncanonical_structure",
                "The standard is usable for QC but does not match the Mode 1 formal output contract.",
                "warning",
            ),
        )
    if errors:
        return _result(
            "structured_incomplete",
            False,
            False,
            traceable,
            errors + warnings,
            warnings,
            semantic_review_available,
        )
    return _result(
        "structured_complete",
        True,
        True,
        traceable,
        warnings,
        warnings,
        semantic_review_available,
    )


def inspect_standard(value, profile="canonical"):
    """Classify a standard as absent, natural-language, or structured completeness.

    Natural-language Chinese standards are intentionally processable first-class
    inputs. Only strings that begin with a JSON container are treated as an
    attempted structured standard.
    """
    if profile not in {"canonical", "qc"}:
        raise ValueError("profile must be canonical or qc")
    try:
        input_kind, normalized_value = _normalize(value)
    except _NormalizationError as exc:
        return _result(
            "structured_incomplete", False, False, False,
            [_issue(exc.code, str(exc))], [], False,
        )
    if input_kind == "absent":
        return _result("absent", False, False, False, [], [], False)
    if input_kind == "natural_language":
        return _result("natural_language", False, False, True, [], [], True)
    if profile == "qc":
        return _validate_qc_standard(normalized_value)

    validation = _validate(normalized_value)
    standard = validation.get("standard")
    errors = validation.get("errors", [])
    warnings = validation.get("warnings", [])
    issues = errors + warnings
    semantic_review_available, traceable = _rule_completeness(standard)
    if validation.get("valid"):
        return _result(
            "structured_complete",
            True,
            True,
            traceable,
            issues,
            warnings,
            semantic_review_available,
        )
    return _result(
        "structured_incomplete",
        False,
        False,
        traceable,
        issues,
        warnings,
        semantic_review_available,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="UTF-8 JSON certification-standard file")
    parser.add_argument("--profile", choices=("canonical", "qc"), default="canonical")
    args = parser.parse_args()
    result = inspect_standard(args.path, profile=args.profile)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["kind"] in ("natural_language", "structured_complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
