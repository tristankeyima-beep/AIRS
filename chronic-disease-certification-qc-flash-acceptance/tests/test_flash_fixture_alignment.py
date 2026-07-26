import copy
import importlib.util
import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    REPO_ROOT
    / "chronic-disease-certification-qc-flash-acceptance"
    / "fixtures"
    / "valid-mode2.json"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "chronic-disease-certification-qc-flash"
    / "references"
    / "mode2-contract.md"
)
VALIDATOR_PATH = Path(__file__).with_name("test_flash_skill.py")
VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "flash_acceptance_validator",
    VALIDATOR_PATH,
)
VALIDATOR_MODULE = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR_MODULE)
assert_valid_mode2 = VALIDATOR_MODULE.assert_valid_mode2


class FlashFixtureAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_canonical_has_two_independent_patient_materials(self):
        patient_sources = [
            source
            for source in self.fixture["sourceDocuments"]
            if source["type"] == "patient_material"
        ]

        self.assertGreaterEqual(len(patient_sources), 2)
        material_ids = []
        for source in patient_sources:
            name_ids = re.findall(r"\d{8,}", source["name"])
            self.assertEqual(1, len(name_ids))
            self.assertIn(name_ids[0], source["content"])
            material_ids.append(name_ids[0])
        self.assertEqual(len(material_ids), len(set(material_ids)))
        for source, own_id in zip(patient_sources, material_ids):
            for other_id in set(material_ids) - {own_id}:
                self.assertNotIn(other_id, source["content"])

    def test_canonical_maps_formal_rule_1001(self):
        standard = next(
            source
            for source in self.fixture["sourceDocuments"]
            if source["type"] == "standard"
        )

        self.assertIn("正式规则码1001", standard["content"])
        self.assertIn("逻辑引用1001", standard["content"])
        self.assertEqual(
            ["1001"],
            [
                judgment["ruleId"]
                for judgment in self.fixture["baseReview"]["ruleJudgments"]
            ],
        )

    def test_mode2_contract_example_matches_canonical_fixture(self):
        contract = CONTRACT_PATH.read_text(encoding="utf-8")
        match = re.search(r"```json\s*(\{.*?\})\s*```", contract, re.DOTALL)
        self.assertIsNotNone(match)
        self.assertEqual(self.fixture, json.loads(match.group(1)))

    def test_rejects_untraceable_audit_material_id(self):
        for material_reference in (
            "材料ID9999999999999999999",
            "材料编号9999999999999999999",
            "引用材料 9999999999999999999",
        ):
            mutation = copy.deepcopy(self.fixture)
            audit_result = next(
                source
                for source in mutation["sourceDocuments"]
                if source["type"] == "audit_result"
            )
            audit_result["content"] = audit_result["content"].replace(
                "材料ID2079388752224174082",
                material_reference,
            )

            with self.subTest(material_reference=material_reference):
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, mutation)

    def test_ignores_non_material_numbers_when_validating_material_ids(self):
        mutation = copy.deepcopy(self.fixture)
        audit_result = next(
            source
            for source in mutation["sourceDocuments"]
            if source["type"] == "audit_result"
        )
        audit_result["content"] += (
            "；审核日期=20260725；规则码=10000001；金额=123456789元"
        )

        assert_valid_mode2(self, mutation)

    def test_allows_untraceable_id_only_with_qualified_extraction_issue(self):
        mutation = copy.deepcopy(self.fixture)
        missing_id = "9999999999999999999"
        audit_result = next(
            source
            for source in mutation["sourceDocuments"]
            if source["type"] == "audit_result"
        )
        audit_result["content"] = audit_result["content"].replace(
            "2079388752224174082",
            missing_id,
        )
        mutation["dimensions"][1]["status"] = "issue"
        mutation["dimensions"][1]["summary"] = "原审核引用的材料ID无法定位"
        mutation["issues"].append(
            {
                "id": "I003",
                "dimension": "证据提取准确性",
                "severity": "medium",
                "auditClaim": f"原审核引用材料ID{missing_id}",
                "actualEvidence": "患者材料名称和原文中均无该ID",
                "sourceReference": f"原审核结果：材料ID{missing_id}",
                "impact": "原审核证据来源无法核验",
                "recommendation": "核对并修正材料ID",
            }
        )

        assert_valid_mode2(self, mutation)

        for name, mutate_issue in {
            "low severity": lambda issue: issue.update(severity="low"),
            "wrong dimension": lambda issue: issue.update(
                dimension="过度推理"
            ),
            "id missing from reference": lambda issue: issue.update(
                sourceReference="原审核结果：材料ID未提供"
            ),
        }.items():
            invalid = copy.deepcopy(mutation)
            mutate_issue(invalid["issues"][-1])
            if name == "wrong dimension":
                invalid["dimensions"][1]["status"] = "passed"
                invalid["dimensions"][2]["status"] = "issue"
            with self.subTest(exception=name):
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, invalid)

    def test_actual_issue_cannot_be_uncertain_unknown(self):
        mutation = copy.deepcopy(self.fixture)
        mutation["auditComparison"]["qcConclusion"] = "uncertain"
        mutation["auditComparison"]["risk"] = "unknown"

        with self.assertRaises(AssertionError):
            assert_valid_mode2(self, mutation)

    def test_detailed_and_brief_preserve_entity_review_condition_issues(self):
        for audit_detail in ("detailed", "brief"):
            for original_conclusion in ("通过", "方向未明确"):
                mutation = copy.deepcopy(self.fixture)
                mutation["inputProfile"]["auditDetail"] = audit_detail
                mutation["auditComparison"].update(
                    originalConclusion=original_conclusion,
                    qcConclusion="problematic",
                    risk="none",
                )
                audit_result = next(
                    source
                    for source in mutation["sourceDocuments"]
                    if source["type"] == "audit_result"
                )
                audit_result["content"] = (
                    f"finalResult={original_conclusion}；"
                    "原审核条件链路存在局部问题，"
                    "引用材料ID2079388752224174082。"
                )
                mutation["dimensions"][0].update(
                    status="passed",
                    summary="材料缺失判断未发现问题",
                    notCheckedReason="",
                )
                mutation["dimensions"][3]["summary"] = (
                    "实体审查发现条件链路存在局部问题"
                )
                mutation["issues"] = [
                    {
                        "id": "I001",
                        "dimension": "审核条件与结论一致性",
                        "severity": "medium",
                        "auditClaim": "原审核条件链路的中间理由成立",
                        "actualEvidence": (
                            "患者材料足以确认局部条件链路错误，"
                            + (
                                "且不改变总体通过方向"
                                if original_conclusion == "通过"
                                else "最终结论方向仍未明确"
                            )
                        ),
                        "sourceReference": (
                            "患者材料-2079388752224174082：测试段落"
                        ),
                        "impact": "局部条件链路不准确",
                        "recommendation": "修正条件链路的中间理由",
                    }
                ]

                with self.subTest(
                    audit_detail=audit_detail,
                    original_conclusion=original_conclusion,
                ):
                    assert_valid_mode2(self, mutation)

    def test_reliable_requires_known_aligned_direction(self):
        mutation = copy.deepcopy(self.fixture)
        mutation["issues"] = []
        for dimension in mutation["dimensions"]:
            dimension["status"] = "passed"
            dimension["summary"] = "本维度复核通过"
            dimension["notCheckedReason"] = ""
        mutation["auditComparison"].update(
            originalConclusion="方向未明确",
            qcConclusion="reliable",
            risk="none",
        )

        with self.assertRaises(AssertionError):
            assert_valid_mode2(self, mutation)

    def test_absent_standard_invariants_apply_to_detailed_and_brief(self):
        for audit_detail in ("detailed", "brief"):
            mutation = copy.deepcopy(self.fixture)
            mutation["inputProfile"].update(
                standardKind="absent",
                auditDetail=audit_detail,
            )
            mutation["sourceDocuments"] = [
                source
                for source in mutation["sourceDocuments"]
                if source["type"] != "standard"
            ]
            mutation["confirmation"]["inventoryShown"] = [
                source["name"] for source in mutation["sourceDocuments"]
            ]
            mutation["baseReview"]["ruleJudgments"] = []
            mutation["baseReview"]["preliminaryResult"] = "uncertain"
            mutation["issues"] = []
            for dimension in mutation["dimensions"]:
                dimension["status"] = "passed"
                dimension["summary"] = "本维度未发现实际问题"
                dimension["notCheckedReason"] = ""
            for index in (3, 4):
                mutation["dimensions"][index]["status"] = "not_checked"
                mutation["dimensions"][index]["summary"] = "缺少认定标准"
                mutation["dimensions"][index][
                    "notCheckedReason"
                ] = "未提供认定标准"
            mutation["auditComparison"].update(
                qcConclusion="uncertain",
                risk="unknown",
            )

            with self.subTest(audit_detail=audit_detail):
                assert_valid_mode2(self, mutation)

                reliable = copy.deepcopy(mutation)
                reliable["auditComparison"].update(
                    qcConclusion="reliable",
                    risk="none",
                )
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, reliable)

    def test_rejection_wording_has_priority_when_deriving_directional_risk(self):
        for original_conclusion in (
            "未通过",
            "未予通过",
            "不能通过",
            "不通过",
            "不予通过",
            "审核决定拒绝",
        ):
            mutation = copy.deepcopy(self.fixture)
            mutation["auditComparison"]["originalConclusion"] = (
                original_conclusion
            )
            assert_valid_mode2(self, mutation)
            mutation["auditComparison"]["risk"] = "false_approval"
            with self.subTest(original_conclusion=original_conclusion):
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, mutation)


if __name__ == "__main__":
    unittest.main()
