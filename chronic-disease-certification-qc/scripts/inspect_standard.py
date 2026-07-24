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


def _issue(code, message):
    return {"path": "$", "code": code, "message": message, "severity": "error"}


def _blank_string(value):
    return isinstance(value, str) and not value.strip()


def _json_looking(value):
    """Only leading JSON containers turn text into a structured-input attempt."""
    return isinstance(value, str) and value.lstrip().startswith(("{", "["))


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


def _result(kind, structural, executable, traceable, issues, semantic_review_available):
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
            "standard": None,
        }


def inspect_standard(value):
    """Classify a standard as absent, natural-language, or structured completeness.

    Natural-language Chinese standards are intentionally processable first-class
    inputs. Only strings that begin with a JSON container are treated as an
    attempted structured standard.
    """
    if value is None or _blank_string(value):
        return _result("absent", False, False, False, [], False)
    if isinstance(value, str) and not _json_looking(value):
        return _result("natural_language", False, False, True, [], True)

    validation = _validate(value)
    standard = validation.get("standard")
    semantic_review_available, traceable = _rule_completeness(standard)
    if validation.get("valid"):
        return _result(
            "structured_complete",
            True,
            True,
            traceable,
            [],
            semantic_review_available,
        )
    return _result(
        "structured_incomplete",
        False,
        False,
        traceable,
        validation.get("errors", []),
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
