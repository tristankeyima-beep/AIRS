import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_skill_metadata_and_ui_contract(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        ui_text = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertRegex(skill_text, r"(?m)^name: chronic-disease-certification-qc$")
        self.assertIn("生成门诊慢特病结构化认定标准", skill_text)
        self.assertIn("智能审核质控", skill_text)
        blocked = ("TO" + "DO", "TB" + "D")
        self.assertFalse(any(term in skill_text.upper() for term in blocked))
        self.assertIn('display_name: "门诊慢特病认定标准与审核质控"', ui_text)
        self.assertIn("$chronic-disease-certification-qc", ui_text)


if __name__ == "__main__":
    unittest.main()
