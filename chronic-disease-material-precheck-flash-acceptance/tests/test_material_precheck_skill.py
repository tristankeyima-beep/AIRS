from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "chronic-disease-material-precheck-flash"


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


if __name__ == "__main__":
    unittest.main()
