import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_certification.py"
SPEC = importlib.util.spec_from_file_location("validate_certification", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class ValidateCertificationTests(unittest.TestCase):
    def setUp(self):
        fixture = ROOT / "tests" / "fixtures" / "valid-certification.json"
        self.valid = json.loads(fixture.read_text(encoding="utf-8"))

    def issue_codes(self, result):
        return [entry["code"] for entry in result["errors"]]

    def test_valid_standard_passes(self):
        result = validator.validate_certification(self.valid)
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_formal_codes_must_match_disease_suffix_and_repository_sequence(self):
        arbitrary = copy.deepcopy(self.valid)
        arbitrary["ruleRepository"][0]["ruleCode"] = "anything"
        arbitrary["logicTopology"]["children"][0]["ruleCode"] = "anything"
        self.assertIn("invalid_rule_code_format", self.issue_codes(validator.validate_certification(arbitrary)))

        arbitrary_guide = copy.deepcopy(self.valid)
        arbitrary_guide["ruleRepository"][0]["ruleKeywordGuide"][0]["keywordCode"] = "anything"
        self.assertIn(
            "invalid_keyword_code_format",
            self.issue_codes(validator.validate_certification(arbitrary_guide)),
        )

        wrong_prefix = copy.deepcopy(self.valid)
        wrong_prefix["ruleRepository"][0]["ruleCode"] = "99001"
        wrong_prefix["logicTopology"]["children"][0]["ruleCode"] = "99001"
        result = validator.validate_certification(wrong_prefix)
        self.assertIn("invalid_rule_code_sequence", self.issue_codes(result))
        self.assertIn(
            "ruleRepository[0].ruleCode",
            [entry["path"] for entry in result["errors"] if entry["code"] == "invalid_rule_code_sequence"],
        )

        skipped = copy.deepcopy(self.valid)
        skipped["ruleRepository"][0]["ruleCode"] = "01002"
        skipped["logicTopology"]["children"][0]["ruleCode"] = "01002"
        self.assertIn("invalid_rule_code_sequence", self.issue_codes(validator.validate_certification(skipped)))

    def test_rule_and_guide_codes_must_follow_list_order_and_parent_rule(self):
        standard = copy.deepcopy(self.valid)
        second = copy.deepcopy(standard["ruleRepository"][0])
        second["ruleCode"] = "01002"
        second["ruleKeywordGuide"][0]["keywordCode"] = "01002001"
        standard["ruleRepository"].append(second)
        standard["logicTopology"]["children"].append({"type": "RULE_REF", "ruleCode": "01002"})

        out_of_order = copy.deepcopy(standard)
        out_of_order["ruleRepository"].reverse()
        result = validator.validate_certification(out_of_order)
        self.assertEqual(
            [entry["path"] for entry in result["errors"] if entry["code"] == "invalid_rule_code_sequence"],
            ["ruleRepository[0].ruleCode", "ruleRepository[1].ruleCode"],
        )

        wrong_parent = copy.deepcopy(standard)
        wrong_parent["ruleRepository"][1]["ruleKeywordGuide"][0]["keywordCode"] = "01001001"
        result = validator.validate_certification(wrong_parent)
        self.assertIn("invalid_keyword_code_sequence", self.issue_codes(result))
        self.assertIn(
            "ruleRepository[1].ruleKeywordGuide[0].keywordCode",
            [entry["path"] for entry in result["errors"] if entry["code"] == "invalid_keyword_code_sequence"],
        )

        skipped_guide = copy.deepcopy(self.valid)
        skipped_guide["ruleRepository"][0]["ruleKeywordGuide"][0]["keywordCode"] = "01001002"
        self.assertIn(
            "invalid_keyword_code_sequence",
            self.issue_codes(validator.validate_certification(skipped_guide)),
        )

    def test_empty_rule_keyword_guide_has_exact_path(self):
        standard = copy.deepcopy(self.valid)
        standard["ruleRepository"][0]["ruleKeywordGuide"] = []
        result = validator.validate_certification(standard)
        self.assertFalse(result["valid"])
        self.assertIn(
            "ruleRepository[0].ruleKeywordGuide",
            [entry["path"] for entry in result["errors"]],
        )

    def test_empty_enum_options_is_rejected(self):
        standard = copy.deepcopy(self.valid)
        standard["ruleRepository"][0]["ruleKeywordGuide"][0]["enumOptions"] = []
        result = validator.validate_certification(standard)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "enum_options_required")

    def test_unknown_topology_reference_is_rejected(self):
        standard = copy.deepcopy(self.valid)
        standard["logicTopology"]["children"][0]["ruleCode"] = "01999"
        result = validator.validate_certification(standard)
        self.assertIn("unknown_rule_reference", self.issue_codes(result))

    def test_finalization_assigns_codes_and_rewrites_topology(self):
        draft = copy.deepcopy(self.valid)
        draft.pop("meta")
        rule = draft["ruleRepository"][0]
        rule["tempRuleId"] = "R001"
        rule.pop("ruleCode")
        rule["ruleKeywordGuide"][0].pop("keywordCode")
        draft["logicTopology"]["children"][0]["ruleCode"] = "R001"
        output = validator.finalize_certification(draft, self.valid["meta"])
        self.assertEqual(output["ruleRepository"][0]["ruleCode"], "01001")
        self.assertEqual(output["ruleRepository"][0]["ruleKeywordGuide"][0]["keywordCode"], "01001001")
        self.assertEqual(output["logicTopology"]["children"][0]["ruleCode"], "01001")

    def test_duplicate_rule_codes_are_rejected(self):
        standard = copy.deepcopy(self.valid)
        duplicate = copy.deepcopy(standard["ruleRepository"][0])
        duplicate["ruleKeywordGuide"][0]["keywordCode"] = "01001002"
        standard["ruleRepository"].append(duplicate)
        standard["logicTopology"]["children"].append({"type": "RULE_REF", "ruleCode": "01001"})
        self.assertIn("duplicate_rule_code", self.issue_codes(validator.validate_certification(standard)))

    def test_string_guides_require_empty_options(self):
        standard = copy.deepcopy(self.valid)
        guide = standard["ruleRepository"][0]["ruleKeywordGuide"][0]
        guide["dataType"] = "string"
        guide["enumOptions"] = ["not allowed"]
        self.assertIn("string_enum_options_must_be_empty", self.issue_codes(validator.validate_certification(standard)))

    def test_unreferenced_rule_is_rejected(self):
        standard = copy.deepcopy(self.valid)
        extra = copy.deepcopy(standard["ruleRepository"][0])
        extra["ruleCode"] = "01002"
        extra["ruleKeywordGuide"][0]["keywordCode"] = "01002001"
        standard["ruleRepository"].append(extra)
        self.assertIn("unreferenced_rule", self.issue_codes(validator.validate_certification(standard)))

    def test_disease_code_requires_two_digit_suffix(self):
        standard = copy.deepcopy(self.valid)
        standard["meta"]["chronicDiseaseCode"] = "CS1"
        self.assertIn("invalid_disease_code", self.issue_codes(validator.validate_certification(standard)))

    def test_malformed_json_and_wrappers_are_handled(self):
        malformed = validator.validate_certification("{not json")
        self.assertFalse(malformed["valid"])
        self.assertIn("invalid_json", self.issue_codes(malformed))
        wrapped = validator.validate_certification({"output": {"result": self.valid}})
        self.assertTrue(wrapped["valid"])

    def test_wrapped_json_string_is_parsed(self):
        result = validator.validate_certification({"output": json.dumps(self.valid, ensure_ascii=False)})
        self.assertTrue(result["valid"])

    def test_multiple_nested_json_string_wrappers_are_parsed(self):
        wrapped = self.valid
        for wrapper_key in reversed(validator.WRAPPER_KEYS):
            wrapped = {wrapper_key: json.dumps(wrapped, ensure_ascii=False)}
        result = validator.validate_certification(wrapped)
        self.assertTrue(result["valid"])

    def test_non_utf8_path_returns_a_validation_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "invalid.json"
            input_path.write_bytes(b"\xff\xfe")
            result = validator.validate_certification(input_path)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["path"], "$")
        self.assertEqual(result["errors"][0]["code"], "input_decode_error")

    def test_partial_formal_root_is_not_unwrapped(self):
        partial = {"meta": {}, "data": "认定标准：需明确诊断"}
        result = validator.validate_certification(partial)
        self.assertFalse(result["valid"])
        self.assertEqual(result["standard"], partial)
        self.assertEqual(result["errors"][0]["path"], "data")
        self.assertEqual(result["errors"][0]["code"], "unknown_field")

    def test_bom_prefixed_path_is_valid_in_library_and_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "bom.json"
            bom_json = "\ufeff" + json.dumps(self.valid, ensure_ascii=False)
            input_path.write_bytes(bom_json.encode("utf-8"))
            self.assertTrue(validator.validate_certification(bom_json)["valid"])
            self.assertTrue(validator.validate_certification(input_path)["valid"])
            command = subprocess.run(
                [sys.executable, str(SCRIPT), "validate", str(input_path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(command.returncode, 0)
        self.assertTrue(json.loads(command.stdout)["valid"])

    def test_nested_wrapper_bom_json_is_valid(self):
        wrapped = {
            "output": json.dumps(
                {"result": "\ufeff" + json.dumps(self.valid, ensure_ascii=False)},
                ensure_ascii=False,
            )
        }
        self.assertTrue(validator.validate_certification(wrapped)["valid"])

    def test_duplicate_json_keys_fail_closed_at_every_decoded_layer(self):
        canonical = json.dumps(self.valid, ensure_ascii=False)
        version = self.valid["meta"]["version"]
        duplicate_meta = canonical.replace(
            f'"version": "{version}"',
            f'"version": "{version}", "version": "V2"',
            1,
        )
        duplicate_nested_rule = canonical.replace(
            '"ruleCode": "01001"',
            '"ruleCode": "01001", "ruleCode": "01999"',
            1,
        )
        duplicate_outer_wrapper = '{"output": ' + canonical + ', "output": {}}'
        duplicate_inner_wrapper = json.dumps(
            {"output": '{"result": ' + canonical + ', "result": {}}'},
            ensure_ascii=False,
        )
        for payload in (
            duplicate_meta,
            duplicate_nested_rule,
            duplicate_outer_wrapper,
            duplicate_inner_wrapper,
            "\ufeff" + duplicate_meta,
        ):
            with self.subTest(payload=payload[:80]):
                result = validator.validate_certification(payload)
                self.assertFalse(result["valid"])
                self.assertEqual(result["errors"][0]["code"], "duplicate_json_key")
                self.assertEqual(result["errors"][0]["path"], "$")

    def test_duplicate_json_key_cli_failure_is_controlled(self):
        canonical = json.dumps(self.valid, ensure_ascii=False)
        version = self.valid["meta"]["version"]
        duplicate = canonical.replace(
            f'"version": "{version}"',
            f'"version": "{version}", "version": "V2"',
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "duplicate.json"
            input_path.write_text(duplicate, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "validate", str(input_path)],
                text=True, capture_output=True, check=False,
            )
        self.assertEqual(completed.returncode, 1)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["errors"][0]["code"], "duplicate_json_key")

    def test_finalization_does_not_mutate_draft_or_meta(self):
        draft = copy.deepcopy(self.valid)
        draft.pop("meta")
        rule = draft["ruleRepository"][0]
        rule["tempRuleId"] = "R001"
        rule.pop("ruleCode")
        rule["ruleKeywordGuide"][0].pop("keywordCode")
        draft["logicTopology"]["children"][0]["ruleCode"] = "R001"
        meta = copy.deepcopy(self.valid["meta"])
        original_draft, original_meta = copy.deepcopy(draft), copy.deepcopy(meta)
        validator.finalize_certification(draft, meta)
        self.assertEqual(draft, original_draft)
        self.assertEqual(meta, original_meta)

    def test_finalization_rejects_unknown_temporary_topology_reference(self):
        draft = copy.deepcopy(self.valid)
        draft.pop("meta")
        rule = draft["ruleRepository"][0]
        rule["tempRuleId"] = "R001"
        rule.pop("ruleCode")
        rule["ruleKeywordGuide"][0].pop("keywordCode")
        draft["logicTopology"]["children"][0]["ruleCode"] = "R999"
        with self.assertRaisesRegex(ValueError, "Unknown temp rule reference: R999"):
            validator.finalize_certification(draft, self.valid["meta"])

    def test_duplicate_keyword_codes_across_rules_are_rejected(self):
        standard = copy.deepcopy(self.valid)
        second_rule = copy.deepcopy(standard["ruleRepository"][0])
        second_rule["ruleCode"] = "01002"
        standard["ruleRepository"].append(second_rule)
        standard["logicTopology"]["children"].append({"type": "RULE_REF", "ruleCode": "01002"})
        self.assertIn("duplicate_keyword_code", self.issue_codes(validator.validate_certification(standard)))

    def test_duplicate_rule_reference_is_rejected(self):
        standard = copy.deepcopy(self.valid)
        standard["logicTopology"]["children"].append({"type": "RULE_REF", "ruleCode": "01001"})
        self.assertIn("duplicate_rule_reference", self.issue_codes(validator.validate_certification(standard)))

    def test_finalization_rejects_duplicate_temporary_rule_ids(self):
        draft = copy.deepcopy(self.valid)
        draft.pop("meta")
        first_rule = draft["ruleRepository"][0]
        first_rule["tempRuleId"] = "R001"
        first_rule.pop("ruleCode")
        first_rule["ruleKeywordGuide"][0].pop("keywordCode")
        second_rule = copy.deepcopy(first_rule)
        draft["ruleRepository"].append(second_rule)
        with self.assertRaisesRegex(ValueError, "tempRuleId must be unique"):
            validator.finalize_certification(draft, self.valid["meta"])

    def test_unknown_fields_are_rejected_at_every_formal_object_level(self):
        standard = copy.deepcopy(self.valid)
        standard["unexpected"] = True
        standard["meta"]["unexpected"] = True
        rule = standard["ruleRepository"][0]
        rule["unexpected"] = True
        rule["ruleKeywordGuide"][0]["unexpected"] = True
        standard["logicTopology"]["unexpected"] = True
        standard["logicTopology"]["children"][0]["unexpected"] = True
        error_paths = [entry["path"] for entry in validator.validate_certification(standard)["errors"]]
        self.assertEqual(
            error_paths[:6],
            [
                "unexpected",
                "meta.unexpected",
                "ruleRepository[0].unexpected",
                "ruleRepository[0].ruleKeywordGuide[0].unexpected",
                "logicTopology.unexpected",
                "logicTopology.children[0].unexpected",
            ],
        )

    def test_formal_root_with_wrapper_named_extra_field_is_not_unwrapped(self):
        for wrapper_key in validator.WRAPPER_KEYS:
            with self.subTest(wrapper_key=wrapper_key):
                standard = copy.deepcopy(self.valid)
                standard[wrapper_key] = {"result": self.valid}
                result = validator.validate_certification(standard)
                self.assertFalse(result["valid"])
                self.assertEqual(result["errors"][0]["path"], wrapper_key)
                self.assertEqual(result["errors"][0]["code"], "unknown_field")

    def test_cyclic_wrapper_returns_serializable_invalid_result(self):
        wrapped = {}
        wrapped["output"] = wrapped
        result = validator.validate_certification(wrapped)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "wrapper_cycle")
        json.dumps(result, ensure_ascii=False)

    def test_overly_deep_wrapper_returns_serializable_invalid_result(self):
        wrapped = self.valid
        for _ in range(validator.MAX_WRAPPER_DEPTH + 1):
            wrapped = {"data": wrapped}
        result = validator.validate_certification(wrapped)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "wrapper_depth_exceeded")
        json.dumps(result, ensure_ascii=False)

    def test_cyclic_topology_returns_serializable_invalid_result(self):
        standard = copy.deepcopy(self.valid)
        topology = standard["logicTopology"]
        topology["children"].append(topology)
        result = validator.validate_certification(standard)
        self.assertFalse(result["valid"])
        self.assertIn("topology_cycle", self.issue_codes(result))
        json.dumps(result, ensure_ascii=False)

    def test_overly_deep_topology_returns_invalid_result(self):
        standard = copy.deepcopy(self.valid)
        node = standard["logicTopology"]
        for _ in range(validator.MAX_TOPOLOGY_DEPTH + 1):
            child = {"type": "GROUP", "operator": "AND", "children": []}
            node["children"] = [child]
            node = child
        node["children"] = [{"type": "RULE_REF", "ruleCode": "01001"}]
        result = validator.validate_certification(standard)
        self.assertFalse(result["valid"])
        self.assertIn("topology_depth_exceeded", self.issue_codes(result))
        json.dumps(result, ensure_ascii=False)

    def test_finalization_rejects_cyclic_topology_with_controlled_error(self):
        draft = copy.deepcopy(self.valid)
        draft.pop("meta")
        rule = draft["ruleRepository"][0]
        rule["tempRuleId"] = "R001"
        rule.pop("ruleCode")
        rule["ruleKeywordGuide"][0].pop("keywordCode")
        topology = draft["logicTopology"]
        topology["children"][0]["ruleCode"] = "R001"
        topology["children"].append(topology)
        with self.assertRaisesRegex(ValueError, "Topology must not contain a cycle"):
            validator.finalize_certification(draft, self.valid["meta"])

    def test_finalization_rejects_deep_topology_with_controlled_error(self):
        draft = copy.deepcopy(self.valid)
        draft.pop("meta")
        rule = draft["ruleRepository"][0]
        rule["tempRuleId"] = "R001"
        rule.pop("ruleCode")
        rule["ruleKeywordGuide"][0].pop("keywordCode")
        node = draft["logicTopology"]
        for _ in range(validator.MAX_TOPOLOGY_DEPTH + 1):
            child = {"type": "GROUP", "operator": "AND", "children": []}
            node["children"] = [child]
            node = child
        node["children"] = [{"type": "RULE_REF", "ruleCode": "R001"}]
        with self.assertRaisesRegex(ValueError, "Topology exceeds the supported depth"):
            validator.finalize_certification(draft, self.valid["meta"])

    def test_finalization_rejects_topology_beyond_python_recursion_limit(self):
        draft = copy.deepcopy(self.valid)
        draft.pop("meta")
        rule = draft["ruleRepository"][0]
        rule["tempRuleId"] = "R001"
        rule.pop("ruleCode")
        rule["ruleKeywordGuide"][0].pop("keywordCode")
        node = draft["logicTopology"]
        for _ in range(1200):
            child = {"type": "GROUP", "operator": "AND", "children": []}
            node["children"] = [child]
            node = child
        node["children"] = [{"type": "RULE_REF", "ruleCode": "R001"}]
        with self.assertRaisesRegex(ValueError, "Topology exceeds the supported depth"):
            validator.finalize_certification(draft, self.valid["meta"])

    def test_finalization_accepts_999_rules(self):
        draft = copy.deepcopy(self.valid)
        draft.pop("meta")
        draft["ruleRepository"] = []
        references = []
        for index in range(1, 1000):
            rule = copy.deepcopy(self.valid["ruleRepository"][0])
            rule["tempRuleId"] = f"R{index:03d}"
            rule.pop("ruleCode")
            rule["ruleKeywordGuide"][0].pop("keywordCode")
            draft["ruleRepository"].append(rule)
            references.append({"type": "RULE_REF", "ruleCode": f"R{index:03d}"})
        draft["logicTopology"] = {"type": "GROUP", "operator": "AND", "children": references}
        output = validator.finalize_certification(draft, self.valid["meta"])
        self.assertEqual(len(output["ruleRepository"]), 999)
        self.assertEqual(output["ruleRepository"][-1]["ruleCode"], "01999")

    def test_finalization_rejects_1000_rules(self):
        draft = {"ruleRepository": [{}] * 1000, "logicTopology": {"type": "GROUP", "operator": "AND", "children": []}}
        with self.assertRaisesRegex(ValueError, "more than 999 rules"):
            validator.finalize_certification(draft, self.valid["meta"])

    def test_finalization_rejects_1000_guides(self):
        draft = copy.deepcopy(self.valid)
        draft.pop("meta")
        rule = draft["ruleRepository"][0]
        rule["tempRuleId"] = "R001"
        rule.pop("ruleCode")
        rule["ruleKeywordGuide"] = [{}] * 1000
        draft["logicTopology"]["children"][0]["ruleCode"] = "R001"
        with self.assertRaisesRegex(ValueError, "more than 999 guides"):
            validator.finalize_certification(draft, self.valid["meta"])

    def test_cli_validate_and_finalize_exit_codes_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            valid_path = directory_path / "valid.json"
            valid_path.write_text(json.dumps(self.valid, ensure_ascii=False), encoding="utf-8")
            validate = subprocess.run(
                [sys.executable, str(SCRIPT), "validate", str(valid_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(validate.returncode, 0)
            self.assertEqual(validate.stderr, "")
            self.assertTrue(json.loads(validate.stdout)["valid"])

            draft = copy.deepcopy(self.valid)
            draft.pop("meta")
            rule = draft["ruleRepository"][0]
            rule["tempRuleId"] = "R001"
            rule.pop("ruleCode")
            rule["ruleKeywordGuide"][0].pop("keywordCode")
            draft["logicTopology"]["children"][0]["ruleCode"] = "R001"
            draft_path = directory_path / "draft.json"
            meta_path = directory_path / "meta.json"
            output_path = directory_path / "final.json"
            draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
            meta_path.write_text(json.dumps(self.valid["meta"], ensure_ascii=False), encoding="utf-8")
            finalize = subprocess.run(
                [sys.executable, str(SCRIPT), "finalize", str(draft_path), str(meta_path), str(output_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(finalize.returncode, 0)
            self.assertEqual(finalize.stderr, "")
            output_bytes = output_path.read_bytes()
            self.assertTrue(output_bytes.endswith(b"\n"))
            self.assertFalse(output_bytes.endswith(b"\n\n"))
            self.assertIn(b'\n  "meta"', output_bytes)
            self.assertEqual(json.loads(output_bytes.decode("utf-8"))["ruleRepository"][0]["ruleCode"], "01001")

    def test_cli_invalid_input_and_output_error_are_controlled(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            invalid_path = directory_path / "invalid.json"
            invalid_path.write_text("{bad", encoding="utf-8")
            validate = subprocess.run(
                [sys.executable, str(SCRIPT), "validate", str(invalid_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(validate.returncode, 1)
            self.assertEqual(validate.stderr, "")

            draft = copy.deepcopy(self.valid)
            draft.pop("meta")
            rule = draft["ruleRepository"][0]
            rule["tempRuleId"] = "R001"
            rule.pop("ruleCode")
            rule["ruleKeywordGuide"][0].pop("keywordCode")
            draft["logicTopology"]["children"][0]["ruleCode"] = "R001"
            draft_path = directory_path / "draft.json"
            meta_path = directory_path / "meta.json"
            draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
            meta_path.write_text(json.dumps(self.valid["meta"], ensure_ascii=False), encoding="utf-8")
            output_path = directory_path / "missing" / "final.json"
            finalize = subprocess.run(
                [sys.executable, str(SCRIPT), "finalize", str(draft_path), str(meta_path), str(output_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(finalize.returncode, 0)
            self.assertTrue(finalize.stderr.startswith("output_error:"))
            self.assertNotIn("Traceback", finalize.stderr)

    def _write_finalize_inputs(self, directory_path):
        draft = copy.deepcopy(self.valid)
        draft.pop("meta")
        rule = draft["ruleRepository"][0]
        rule["tempRuleId"] = "R001"
        rule.pop("ruleCode")
        rule["ruleKeywordGuide"][0].pop("keywordCode")
        draft["logicTopology"]["children"][0]["ruleCode"] = "R001"
        draft_path = directory_path / "draft.json"
        meta_path = directory_path / "meta.json"
        draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        meta_path.write_text(json.dumps(self.valid["meta"], ensure_ascii=False), encoding="utf-8")
        return draft_path, meta_path

    def test_finalize_cli_rejects_output_aliases_without_changing_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            draft_path, meta_path = self._write_finalize_inputs(directory_path)
            original_draft = draft_path.read_bytes()
            original_meta = meta_path.read_bytes()
            aliases = [
                draft_path,
                "draft.json",
                meta_path,
            ]
            hardlink = directory_path / "draft-hardlink.json"
            try:
                hardlink.hardlink_to(draft_path)
            except OSError as exc:
                self.skipTest(f"hard links unsupported: {exc}")
            aliases.append(hardlink)
            symlink = directory_path / "draft-symlink.json"
            try:
                symlink.symlink_to(draft_path)
            except OSError as exc:
                import errno
                if exc.errno in (errno.EPERM, errno.EACCES, errno.ENOSYS, errno.EOPNOTSUPP):
                    self.skipTest(f"symlinks unsupported: {exc}")
                raise
            aliases.append(symlink)

            for output_argument in aliases:
                with self.subTest(output_path=output_argument):
                    completed = subprocess.run(
                        [
                            sys.executable, str(SCRIPT), "finalize",
                            str(draft_path), str(meta_path), str(output_argument),
                        ],
                        text=True, capture_output=True, check=False,
                        cwd=directory_path,
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertNotIn("Traceback", completed.stderr)
                    self.assertEqual(draft_path.read_bytes(), original_draft)
                    self.assertEqual(meta_path.read_bytes(), original_meta)

    def test_finalize_cli_rejects_existing_output_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            draft_path, meta_path = self._write_finalize_inputs(directory_path)
            destination = directory_path / "destination.json"
            destination.write_bytes(b"keep destination")
            output = directory_path / "output.json"
            try:
                output.symlink_to(destination)
            except OSError as exc:
                import errno
                if exc.errno in (errno.EPERM, errno.EACCES, errno.ENOSYS, errno.EOPNOTSUPP):
                    self.skipTest(f"symlinks unsupported: {exc}")
                raise
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "finalize", str(draft_path), str(meta_path), str(output)],
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertNotIn("Traceback", completed.stderr)
            self.assertTrue(output.is_symlink())
            self.assertEqual(destination.read_bytes(), b"keep destination")

    def test_atomic_writer_preserves_existing_destination_and_cleans_stage_on_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            output = directory_path / "final.json"
            output.write_bytes(b"old bytes")
            output.chmod(0o640)
            for failure in ("stage", "write", "fsync", "replace"):
                with self.subTest(failure=failure):
                    output.write_bytes(b"old bytes")
                    output.chmod(0o640)
                    if failure == "stage":
                        context = patch.object(
                            validator.tempfile,
                            "mkstemp",
                            side_effect=OSError("stage failed"),
                        )
                    elif failure == "replace":
                        context = patch.object(validator.os, "replace", side_effect=OSError("replace failed"))
                    elif failure == "fsync":
                        context = patch.object(validator.os, "fsync", side_effect=OSError("fsync failed"))
                    else:
                        context = patch.object(validator, "_write_all", side_effect=OSError("write failed"))
                    with context:
                        with self.assertRaises(OSError):
                            validator.atomic_write_text(output, "new bytes\n")
                    self.assertEqual(output.read_bytes(), b"old bytes")
                    self.assertEqual(output.stat().st_mode & 0o777, 0o640)
                    self.assertEqual(list(directory_path.glob(".final.json.*.tmp")), [])

    def test_atomic_writer_sets_new_mode_and_preserves_existing_mode(self):
        if sys.platform == "win32":
            self.skipTest("POSIX mode contract")
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            output = directory_path / "final.json"
            validator.atomic_write_text(output, "first\n")
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)
            output.chmod(0o600)
            validator.atomic_write_text(output, "second\n")
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
