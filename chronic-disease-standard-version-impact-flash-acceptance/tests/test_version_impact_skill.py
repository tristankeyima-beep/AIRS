from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "chronic-disease-standard-version-impact-flash"
FIXTURE = ROOT / "chronic-disease-standard-version-impact-flash-acceptance/fixtures/valid-version-impact.json"


class VersionImpactSkillTests(unittest.TestCase):
    def read_skill_file(self, relative_path):
        path = SKILL_ROOT / relative_path
        if not path.is_file():
            self.fail(f"missing required Skill file: {path}")
        return path.read_text(encoding="utf-8")

    def test_skill_requires_confirmed_versions_and_order_basis(self):
        skill = self.read_skill_file("SKILL.md")
        self.assertIn("确认比较顺序", skill)
        self.assertIn("不得单独当作政策生效日期", skill)
        self.assertIn("不评价原审核结果", skill)

    def test_contract_uses_version_scoped_rule_ids(self):
        contract = self.read_skill_file("references/version-impact-contract.md")
        self.assertIn("S1:R001", contract)
        self.assertIn("standard_version_impact", contract)
        self.assertIn("排序依据", contract)

    def test_fixture_keeps_versions_and_assessments_separate(self):
        if not FIXTURE.is_file():
            self.fail(f"missing required fixture: {FIXTURE}")
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(data["mode"], "standard_version_impact")
        self.assertEqual(len(data["standardInputs"]), 2)
        self.assertEqual(data["changes"][0]["type"], "条件修改")
        self.assertTrue(data["versionAssessments"])
        self.assertIn("S1:R001", data["versionAssessments"][0]["ruleJudgments"][0]["ruleId"])

    def test_template_has_comparison_sections_and_one_data_slot(self):
        template = self.read_skill_file("assets/version-impact-template.html")
        self.assertEqual(template.count("__FLASH_DATA_JSON__"), 1)
        self.assertIn("版本与排序依据", template)
        self.assertIn("标准差异", template)
        self.assertIn("各版本规则证据判读", template)
        self.assertNotIn("五维检查", template)

    def test_template_translates_internal_assessment_states_to_chinese(self):
        template = self.read_skill_file("assets/version-impact-template.html")
        for expected in ('met:"满足"', 'not_met:"不满足"', 'unknown:"无法判断"', 'meets:"符合"', 'does_not_meet:"不符合"', 'uncertain:"无法确定"'):
            self.assertIn(expected, template)
        self.assertIn('detail("参考结果",statusLabel(assessment.referenceResult))', template)
        self.assertIn('statusLabel(judgment.result)', template)

    def test_template_translates_internal_identifiers_for_display(self):
        template = self.read_skill_file("assets/version-impact-template.html")
        self.assertIn('版本${version}', template)
        self.assertIn('规则${rule}', template)
        self.assertIn('规则${number}', template)
        self.assertIn('.replace(/\\bAND\\b/g, "且")', template)
        self.assertIn('readableText', template)


if __name__ == "__main__":
    unittest.main()
