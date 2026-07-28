from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "SKILLS"

EXPECTED_SKILLS = {
    "认定标准/chronic-disease-certification-standard-flash",
    "审核质控/chronic-disease-certification-qc-flash",
    "材料管理/chronic-disease-material-catalog-flash",
    "材料管理/chronic-disease-material-precheck-flash",
    "版本管理/chronic-disease-standard-version-impact-flash",
}

COMPLETE_QC_SKILL = "审核质控/门诊慢特病审核质控完整版"


class SkillLayoutTests(unittest.TestCase):
    def test_five_flash_skills_are_grouped_under_skills(self):
        for relative_path in EXPECTED_SKILLS:
            skill_root = SKILLS_ROOT / relative_path
            self.assertTrue((skill_root / "SKILL.md").is_file(), relative_path)
            self.assertTrue((skill_root / "agents/openai.yaml").is_file(), relative_path)

    def test_flash_skill_directories_are_not_left_at_repository_root(self):
        for relative_path in EXPECTED_SKILLS:
            self.assertFalse((ROOT / Path(relative_path).name).exists(), relative_path)

    def test_complete_qc_skill_uses_its_chinese_category_name(self):
        skill_root = SKILLS_ROOT / COMPLETE_QC_SKILL
        self.assertTrue((skill_root / "SKILL.md").is_file(), COMPLETE_QC_SKILL)
        self.assertTrue((skill_root / "agents/openai.yaml").is_file(), COMPLETE_QC_SKILL)
        self.assertFalse((ROOT / "chronic-disease-certification-qc").exists())


if __name__ == "__main__":
    unittest.main()
