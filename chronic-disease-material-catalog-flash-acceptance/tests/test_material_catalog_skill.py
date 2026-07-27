from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "chronic-disease-material-catalog-flash"
FIXTURE = ROOT / "chronic-disease-material-catalog-flash-acceptance/fixtures/valid-material-catalog.json"


class MaterialCatalogSkillTests(unittest.TestCase):
    def read_skill_file(self, relative_path):
        path = SKILL_ROOT / relative_path
        if not path.is_file():
            self.fail(f"missing required Skill file: {path}")
        return path.read_text(encoding="utf-8")

    def read_fixture(self):
        if not FIXTURE.is_file():
            self.fail(f"missing required fixture: {FIXTURE}")
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

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

    def test_contract_forbids_audit_and_eligibility_outputs(self):
        contract = self.read_skill_file("references/catalog-contract.md")
        self.assertIn("不得包含规则判断、资格结论、审核结论、风险、问题或建议字段", contract)
        self.assertIn("疑似重复只能使用待核对", contract)

    def test_template_has_exactly_one_data_slot(self):
        template = self.read_skill_file("assets/material-catalog-template.html")
        self.assertEqual(template.count("__FLASH_DATA_JSON__"), 1)
        self.assertIn('id="flash-data"', template)
        self.assertIn("JSON.parse", template)

    def test_fixture_is_objective_and_traceable(self):
        data = self.read_fixture()
        self.assertEqual(data["schemaVersion"], "flash-1.0")
        self.assertEqual(data["mode"], "material_catalog")
        self.assertEqual(len(data["sourceDocuments"]), len(data["catalog"]))
        self.assertEqual(data["confirmation"]["confirmed"], True)
        self.assertEqual(data["relationships"][0]["status"], "待核对")
        self.assertIn("不构成资格", data["analysisRecord"]["preliminaryConclusion"])


if __name__ == "__main__":
    unittest.main()
