from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "SKILLS/材料管理/chronic-disease-material-precheck-flash"
FIXTURE = ROOT / "chronic-disease-material-precheck-flash-acceptance/fixtures/valid-material-precheck.json"


class MaterialPrecheckSkillTests(unittest.TestCase):
    def read_skill_file(self, relative_path):
        path = SKILL_ROOT / relative_path
        if not path.is_file():
            self.fail(f"missing required Skill file: {path}")
        return path.read_text(encoding="utf-8")

    def test_skill_requires_standard_and_material_confirmation(self):
        skill = self.read_skill_file("SKILL.md")
        self.assertIn("明确确认采用的标准", skill)
        self.assertIn("明确确认材料完整", skill)
        self.assertIn("不输出通过或不通过结论", skill)

    def test_contract_defines_four_precheck_states(self):
        contract = self.read_skill_file("references/precheck-contract.md")
        for state in ("已定位证据", "信息不足", "未定位证据", "材料形式待确认"):
            self.assertIn(state, contract)
        self.assertIn("不得包含原审核结果、风险或正式资格结论", contract)

    def test_contract_requires_traceable_supplement_items(self):
        contract = self.read_skill_file("references/precheck-contract.md")
        self.assertIn("supplementList", contract)
        self.assertIn("只能收录信息不足、未定位证据或材料形式待确认", contract)
        self.assertIn("不能凭空指定诊断证明、检查单或其他特定文件", contract)

    def test_fixture_covers_every_precheck_state_without_final_decision(self):
        if not FIXTURE.is_file():
            self.fail(f"missing required fixture: {FIXTURE}")
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        states = {item["status"] for item in data["precheckItems"]}
        self.assertEqual(states, {"已定位证据", "信息不足", "未定位证据", "材料形式待确认"})
        self.assertTrue(data["confirmation"]["standardConfirmed"])
        self.assertTrue(data["confirmation"]["materialsConfirmedComplete"])
        self.assertIn("不构成正式资格审核", data["analysisRecord"]["preliminaryConclusion"])

    def test_template_has_precheck_sections_and_one_data_slot(self):
        template = self.read_skill_file("assets/material-precheck-template.html")
        self.assertEqual(template.count("__FLASH_DATA_JSON__"), 1)
        self.assertIn('id="flash-data"', template)
        self.assertIn("条件—证据预检", template)
        self.assertIn("补充信息与补件清单", template)
        self.assertIn("材料形式待人工确认", template)
        self.assertNotIn("五维检查", template)

    def test_template_translates_rule_codes_and_logic_words_for_display(self):
        template = self.read_skill_file("assets/material-precheck-template.html")
        self.assertIn('规则${number}', template)
        self.assertIn('.replace(/\\bAND\\b/g,"且")', template)
        self.assertIn('textContent=readableText(text)', template)


if __name__ == "__main__":
    unittest.main()
