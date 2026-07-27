from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "chronic-disease-material-catalog-flash"


class MaterialCatalogSkillTests(unittest.TestCase):
    def read_skill_file(self, relative_path):
        path = SKILL_ROOT / relative_path
        if not path.is_file():
            self.fail(f"missing required Skill file: {path}")
        return path.read_text(encoding="utf-8")

    def test_skill_defines_objective_cataloging_boundary(self):
        skill = self.read_skill_file("SKILL.md")
        self.assertIn("不读取认定标准", skill)
        self.assertIn("不输出通过或不通过结论", skill)
        self.assertIn("明确确认材料完整", skill)

    def test_contract_defines_catalog_mode_and_required_sections(self):
        contract = self.read_skill_file("references/catalog-contract.md")
        for expected in (
            "material_catalog",
            "sourceDocuments",
            "catalog",
            "timelines",
            "relationships",
            "confirmation",
        ):
            self.assertIn(expected, contract)

    def test_template_has_exactly_one_data_slot(self):
        template = self.read_skill_file("assets/material-catalog-template.html")
        self.assertEqual(template.count("__FLASH_DATA_JSON__"), 1)
        self.assertIn('id="flash-data"', template)
        self.assertIn("JSON.parse", template)


if __name__ == "__main__":
    unittest.main()
