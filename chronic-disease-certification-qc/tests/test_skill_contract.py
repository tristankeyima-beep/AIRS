import re
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_skill_metadata_and_ui_contract(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        ui_text = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        frontmatter_match = re.match(
            r"\A---\n(?P<frontmatter>.*?)\n---\n", skill_text, re.DOTALL
        )
        self.assertIsNotNone(frontmatter_match, "SKILL.md frontmatter is malformed")

        frontmatter = frontmatter_match.group("frontmatter")
        fields = [line.split(": ", 1) for line in frontmatter.splitlines()]
        self.assertTrue(
            all(len(field) == 2 and field[0] for field in fields),
            "SKILL.md frontmatter must contain simple key-value fields",
        )
        field_names = [field[0] for field in fields]
        self.assertEqual(set(field_names), {"name", "description"})
        self.assertEqual(len(field_names), len(set(field_names)))
        metadata = dict(fields)
        self.assertEqual(metadata["name"], "chronic-disease-certification-qc")

        skill_body = skill_text[frontmatter_match.end() :]
        self.assertIn("生成门诊慢特病结构化认定标准", skill_body)
        self.assertIn("智能审核质控", skill_body)
        blocked = ("TO" + "DO", "TB" + "D")
        self.assertFalse(any(term in skill_body.upper() for term in blocked))

        expected_ui = (
            "interface:\n"
            '  display_name: "门诊慢特病认定标准与审核质控"\n'
            '  short_description: "生成门诊慢特病结构化认定标准，并复核患者材料与智能审核结果质量"\n'
            '  default_prompt: "使用 $chronic-disease-certification-qc 生成门诊慢特病结构化认定标准，或复核患者材料与智能审核结果。"\n'
        )
        normalized_ui = ui_text[:-1] if ui_text.endswith("\n") else ui_text
        self.assertEqual(normalized_ui, expected_ui[:-1])


if __name__ == "__main__":
    unittest.main()
