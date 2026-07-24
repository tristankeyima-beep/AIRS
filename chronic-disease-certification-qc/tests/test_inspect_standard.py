import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inspect_standard.py"
SPEC = importlib.util.spec_from_file_location("inspect_standard", SCRIPT)
inspector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspector)


class InspectStandardTests(unittest.TestCase):
    def setUp(self):
        fixture = ROOT / "tests" / "fixtures" / "valid-certification.json"
        self.valid = json.loads(fixture.read_text(encoding="utf-8"))

    def assert_completeness(self, result, structural, executable, traceable):
        self.assertEqual(
            result["completeness"],
            {
                "structural": structural,
                "executable": executable,
                "traceable": traceable,
                "source_consistent": None,
            },
        )

    def test_none_is_absent(self):
        result = inspector.inspect_standard(None)
        self.assertEqual(result["kind"], "absent")
        self.assert_completeness(result, False, False, False)
        self.assertEqual(result["issues"], [])
        self.assertFalse(result["semantic_review_available"])

    def test_blank_text_is_absent(self):
        result = inspector.inspect_standard(" \n\t ")
        self.assertEqual(result["kind"], "absent")
        self.assert_completeness(result, False, False, False)
        self.assertEqual(result["issues"], [])

    def test_chinese_natural_language_is_first_class_input(self):
        text = "逻辑：且\n认定标准：需明确诊断；需提供影像学证据"
        result = inspector.inspect_standard(text)
        self.assertEqual(result["kind"], "natural_language")
        self.assert_completeness(result, False, False, True)
        self.assertEqual(result["issues"], [])
        self.assertTrue(result["semantic_review_available"])

    def test_natural_language_with_nonleading_braces_is_not_json(self):
        result = inspector.inspect_standard("标准说明中包含 {示例}，仍以病历内容为准。")
        self.assertEqual(result["kind"], "natural_language")
        self.assertEqual(result["issues"], [])

    def test_canonical_fixture_is_complete_and_executable(self):
        result = inspector.inspect_standard(self.valid)
        self.assertEqual(result["kind"], "structured_complete")
        self.assert_completeness(result, True, True, True)
        self.assertEqual(result["issues"], [])
        self.assertTrue(result["semantic_review_available"])

    def test_empty_keyword_guide_is_incomplete_with_validator_issue(self):
        standard = copy.deepcopy(self.valid)
        standard["ruleRepository"][0]["ruleKeywordGuide"] = []
        result = inspector.inspect_standard(standard)
        self.assertEqual(result["kind"], "structured_incomplete")
        self.assertFalse(result["completeness"]["structural"])
        self.assertEqual(
            result["issues"],
            [
                {
                    "path": "ruleRepository[0].ruleKeywordGuide",
                    "code": "keyword_guide_required",
                    "message": "At least one keyword guide is required.",
                    "severity": "error",
                }
            ],
        )

    def test_wrapped_objects_and_json_strings_are_complete(self):
        for input_value in (
            {"output": {"result": copy.deepcopy(self.valid)}},
            {"data": json.dumps(self.valid, ensure_ascii=False)},
        ):
            with self.subTest(input_value=input_value):
                result = inspector.inspect_standard(input_value)
                self.assertEqual(result["kind"], "structured_complete")
                self.assertTrue(result["completeness"]["executable"])

    def test_valid_and_incomplete_paths_are_handled(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            valid_path = directory / "valid.json"
            valid_path.write_text(json.dumps(self.valid, ensure_ascii=False), encoding="utf-8")
            incomplete = copy.deepcopy(self.valid)
            incomplete["ruleRepository"][0]["ruleKeywordGuide"] = []
            incomplete_path = directory / "incomplete.json"
            incomplete_path.write_text(json.dumps(incomplete, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(inspector.inspect_standard(valid_path)["kind"], "structured_complete")
            result = inspector.inspect_standard(incomplete_path)
        self.assertEqual(result["kind"], "structured_incomplete")
        self.assertEqual(result["issues"][0]["path"], "ruleRepository[0].ruleKeywordGuide")

    def test_malformed_json_looking_text_returns_validator_issue(self):
        result = inspector.inspect_standard("{not json")
        self.assertEqual(result["kind"], "structured_incomplete")
        self.assertEqual(result["issues"][0]["path"], "$")
        self.assertEqual(result["issues"][0]["code"], "invalid_json")

    def test_non_utf8_path_returns_validator_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "invalid.json"
            input_path.write_bytes(b"\xff\xfe")
            result = inspector.inspect_standard(input_path)
        self.assertEqual(result["kind"], "structured_incomplete")
        self.assertEqual(result["issues"][0]["code"], "input_decode_error")

    def test_non_string_scalars_are_structured_incomplete(self):
        for input_value in (0, 1.5, True, [], object()):
            with self.subTest(input_value=repr(input_value)):
                result = inspector.inspect_standard(input_value)
                self.assertEqual(result["kind"], "structured_incomplete")
                self.assertFalse(result["completeness"]["executable"])
                self.assertEqual(result["issues"][0]["code"], "invalid_root")

    def test_missing_source_text_is_not_traceable(self):
        standard = copy.deepcopy(self.valid)
        standard["ruleRepository"][0]["sourceRuleContent"] = ""
        result = inspector.inspect_standard(standard)
        self.assertEqual(result["kind"], "structured_incomplete")
        self.assertFalse(result["completeness"]["traceable"])
        self.assertTrue(result["semantic_review_available"])

    def test_input_is_not_mutated_and_result_is_serializable(self):
        standard = copy.deepcopy(self.valid)
        original = copy.deepcopy(standard)
        result = inspector.inspect_standard(standard)
        self.assertEqual(standard, original)
        json.dumps(result, ensure_ascii=False)

    def test_cyclic_and_deep_structures_return_serializable_results(self):
        wrapped = {}
        wrapped["output"] = wrapped
        wrapped_result = inspector.inspect_standard(wrapped)
        self.assertEqual(wrapped_result["kind"], "structured_incomplete")
        self.assertEqual(wrapped_result["issues"][0]["code"], "wrapper_cycle")

        standard = copy.deepcopy(self.valid)
        node = standard["logicTopology"]
        for _ in range(1200):
            child = {"type": "GROUP", "operator": "AND", "children": []}
            node["children"] = [child]
            node = child
        node["children"] = [{"type": "RULE_REF", "ruleCode": "01001"}]
        deep_result = inspector.inspect_standard(standard)
        self.assertEqual(deep_result["kind"], "structured_incomplete")
        json.dumps(wrapped_result, ensure_ascii=False)
        json.dumps(deep_result, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
