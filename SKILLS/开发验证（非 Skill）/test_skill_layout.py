from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "SKILLS"

EXPECTED_SKILLS = {
    "认定标准生成（Flash）/chronic-disease-certification-standard-flash",
    "审核质控（Flash）/chronic-disease-certification-qc-flash",
    "申请材料预检与补件清单（Flash）/chronic-disease-material-precheck-flash",
    "材料证据编目与归位（Flash）/chronic-disease-material-catalog-flash",
    "认定标准版本比对与影响分析（Flash）/chronic-disease-standard-version-impact-flash",
}

COMPLETE_QC_SKILL = "门诊慢特病认定标准与审核质控助手（完整版）/chronic-disease-certification-qc"

DESCRIPTION_DOCUMENTS = {
    "认定标准生成（Flash）/chronic-disease-certification-standard-flash": (
        "门诊慢特病认定标准生成助手（Flash）",
        "测试用例",
        "脑梗死",
    ),
    "审核质控（Flash）/chronic-disease-certification-qc-flash": (
        "门诊慢特病审核质控助手（Flash）",
        "测试用例",
        "确认完整",
    ),
    "申请材料预检与补件清单（Flash）/chronic-disease-material-precheck-flash": (
        "门诊慢特病申请材料预检与补件清单助手（Flash）",
        "补件清单",
        "不构成正式资格审核结论",
    ),
    "材料证据编目与归位（Flash）/chronic-disease-material-catalog-flash": (
        "门诊慢特病材料证据编目与归位助手（Flash）",
        "客观整理",
        "不评价材料是否充分",
    ),
    "认定标准版本比对与影响分析（Flash）/chronic-disease-standard-version-impact-flash": (
        "门诊慢特病认定标准版本比对与影响分析助手（Flash）",
        "受影响审核规则",
        "不构成最终经办资格结论",
    ),
    COMPLETE_QC_SKILL: (
        "门诊慢特病认定标准与审核质控助手（完整版）",
        "模式一",
        "模式二",
    ),
}


class SkillLayoutTests(unittest.TestCase):
    def test_five_flash_skills_are_grouped_under_skills(self):
        for relative_path in EXPECTED_SKILLS:
            skill_root = SKILLS_ROOT / relative_path
            self.assertTrue((skill_root / "SKILL.md").is_file(), relative_path)
            self.assertTrue((skill_root / "agents/openai.yaml").is_file(), relative_path)

    def test_flash_skill_directories_are_not_left_at_repository_root(self):
        for relative_path in EXPECTED_SKILLS:
            self.assertFalse((ROOT / Path(relative_path).name).exists(), relative_path)

    def test_complete_qc_skill_is_grouped_under_the_complete_edition(self):
        skill_root = SKILLS_ROOT / COMPLETE_QC_SKILL
        self.assertTrue((skill_root / "SKILL.md").is_file(), COMPLETE_QC_SKILL)
        self.assertTrue((skill_root / "agents/openai.yaml").is_file(), COMPLETE_QC_SKILL)
        self.assertFalse((ROOT / "chronic-disease-certification-qc").exists())

    def test_every_deliverable_skill_has_a_chinese_usage_guide(self):
        for relative_path, required_terms in DESCRIPTION_DOCUMENTS.items():
            guide_path = SKILLS_ROOT / relative_path / "使用说明.md"
            self.assertTrue(guide_path.is_file(), relative_path)
            content = guide_path.read_text(encoding="utf-8")
            for required_term in required_terms:
                self.assertIn(required_term, content, f"{relative_path}: {required_term}")


if __name__ == "__main__":
    unittest.main()
