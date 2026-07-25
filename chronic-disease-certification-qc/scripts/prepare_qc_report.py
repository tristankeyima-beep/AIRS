#!/usr/bin/env python3
"""Prepare deterministic fields in a Mode 2 QC report draft."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys


RENDERER_PATH = Path(__file__).with_name("render_qc_html.py")
RENDERER_SPEC = importlib.util.spec_from_file_location("_qc_report_renderer", RENDERER_PATH)
renderer = importlib.util.module_from_spec(RENDERER_SPEC)
RENDERER_SPEC.loader.exec_module(renderer)
MATERIAL_TEXT_KEYS = ("content", "materialContent", "text", "rawText")


def _normalize_material_content(report):
    raw_input = report.get("rawInput")
    if not isinstance(raw_input, dict):
        return
    materials = raw_input.get("materials")
    if not isinstance(materials, list):
        return
    for index, material in enumerate(materials):
        if not isinstance(material, dict):
            continue
        available = [
            (key, material[key])
            for key in MATERIAL_TEXT_KEYS
            if isinstance(material.get(key), str)
        ]
        distinct = {value for _, value in available}
        if len(distinct) > 1:
            raise ValueError(
                "qc_report_prepare: "
                f"rawInput.materials[{index}]: conflicting material text fields"
            )
        if available:
            material["content"] = available[0][1]
        for key in MATERIAL_TEXT_KEYS:
            if key != "content":
                material.pop(key, None)


def prepare_report(draft):
    """Return a validated canonical report without mutating the business draft."""
    report = renderer._json_safe(draft)
    if not isinstance(report, dict):
        raise ValueError("qc_report_prepare: root must be an object")
    _normalize_material_content(report)

    capabilities = report.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("qc_report_prepare: capabilities must be an array")
    report["unperformedChecks"] = [
        {"name": item.get("name"), "reason": item.get("reason")}
        for item in capabilities
        if isinstance(item, dict) and item.get("status") == "not_run"
    ]

    try:
        input_scope = report["inputScope"]
        inventory = input_scope["inventory"]
        confirmation = input_scope["confirmation"]
        independent = input_scope["independentReview"]
        artifact = independent["artifact"]
        raw_input = report["rawInput"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"qc_report_prepare: missing required structure {exc}") from None

    inventory["rawInputSha256"] = renderer.compute_raw_input_sha256(raw_input)
    confirmation["inventorySha256"] = renderer.compute_inventory_sha256(inventory)
    independent["artifactSha256"] = renderer.compute_independent_review_sha256(artifact)
    return renderer.validate_qc_report(report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="QC report business draft JSON")
    parser.add_argument("output", type=Path, help="prepared canonical QC report JSON")
    args = parser.parse_args(argv)
    try:
        draft = renderer._load_source(args.input)
        prepared = prepare_report(draft)
        payload = (
            json.dumps(
                prepared,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ).rstrip("\n")
            + "\n"
        ).encode("utf-8")
        paths = renderer._reject_output_collisions(args.input, args.output)
        renderer._write_outputs_atomically({paths["HTML output"]: payload})
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"prepare_error: {exc}", file=sys.stderr)
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
