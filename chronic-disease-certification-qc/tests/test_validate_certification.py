import copy
import importlib.util
import json
from pathlib import Path
import unittest


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


if __name__ == "__main__":
    unittest.main()
