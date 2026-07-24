#!/usr/bin/env python3
"""Classify certification-standard input before quality-control processing."""

import argparse
import importlib.util
import json
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


class _NormalizationError(ValueError):
    """A controlled input-adapter error with a validator-compatible code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _issue(code, message):
    return {"path": "$", "code": code, "message": message, "severity": "error"}


def _blank_string(value):
    return isinstance(value, str) and not value.strip()


def _json_looking(value):
    """Only leading JSON containers turn text into a structured-input attempt."""
    return isinstance(value, str) and value.lstrip().startswith(("{", "["))


def _decode_json(value):
    try:
        return json.loads(value)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise _NormalizationError("invalid_json", "Input is not valid JSON.") from exc


def _unwrap(value):
    """Safely normalize compatible wrappers into a structured or text payload."""
    seen_wrappers = set()
    depth = 0
    while True:
        if isinstance(value, dict):
            if _FORMAL_ROOT_KEYS.issubset(value):
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
            if _blank_string(value):
                return "absent", None
            # A wrapper may hold an object JSON string or a JSON-string-encoded
            # natural-language standard. Ordinary text is never decoded.
            if value.lstrip().startswith(("{", "[", '"')):
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
            value = value.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise _NormalizationError("input_decode_error", "Input must be UTF-8 JSON.") from exc
        except OSError as exc:
            raise _NormalizationError("input_read_error", str(exc)) from exc
    if value is None or _blank_string(value):
        return "absent", None
    if isinstance(value, str):
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


def inspect_standard(value):
    """Classify a standard as absent, natural-language, or structured completeness.

    Natural-language Chinese standards are intentionally processable first-class
    inputs. Only strings that begin with a JSON container are treated as an
    attempted structured standard.
    """
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
    args = parser.parse_args()
    result = inspect_standard(args.path)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["kind"] in ("natural_language", "structured_complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
