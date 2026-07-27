from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "chronic-disease-standard-version-impact-flash"


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


if __name__ == "__main__":
    unittest.main()
