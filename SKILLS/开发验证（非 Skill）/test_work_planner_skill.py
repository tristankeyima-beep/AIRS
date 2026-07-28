from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = (
    ROOT
    / "SKILLS"
    / "门诊慢特病工作规划与任务编排"
    / "chronic-disease-work-planner"
)


def read(relative_path):
    return (SKILL_ROOT / relative_path).read_text(encoding="utf-8")


class WorkPlannerSkillTests(unittest.TestCase):
    def test_required_files_exist(self):
        required_files = (
            "SKILL.md",
            "使用说明.md",
            "agents/openai.yaml",
            "references/intent-routing.md",
            "references/continuous-execution.md",
            "references/markdown-plan-template.md",
        )

        for relative_path in required_files:
            self.assertTrue(
                (SKILL_ROOT / relative_path).is_file(),
                relative_path,
            )

    def test_skill_declares_trigger_modes_and_question_limit(self):
        content = read("SKILL.md")
        required_terms = (
            "name: chronic-disease-work-planner",
            "只制定计划",
            "自动连续执行",
            "一至三个",
            "患者申请材料",
            "病种认定标准",
            "审核结果",
            "政策与临床依据",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_skill_narrows_trigger_boundary(self):
        content = read("SKILL.md")
        required_terms = (
            "在门诊慢特病业务中",
            "未说明期望成果",
            "两项以上",
            "单一明确任务",
            "指定具体能力",
            "改写、排版",
            "非门诊慢特病任务",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_explicit_planning_request_overrides_default_non_trigger(self):
        content = read("SKILL.md")
        required_terms = (
            "默认不自动触发",
            "明确要求制定计划",
            "拆解任务",
            "安排步骤",
            "单一明确任务或指定具体能力",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_routing_reference_names_all_six_capabilities(self):
        content = read("references/intent-routing.md")
        required_terms = (
            "chronic-disease-knowledge-retrieval",
            "chronic-disease-certification-standard-flash",
            "chronic-disease-material-catalog-flash",
            "chronic-disease-material-precheck-flash",
            "chronic-disease-standard-version-impact-flash",
            "chronic-disease-certification-qc-flash",
            "没有原审核结果",
            "不得自动采用",
            "不得自动成为医保准入条件",
            "标准修改",
            "拟修订版",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_continuous_execution_keeps_business_confirmation_gates(self):
        content = read("references/continuous-execution.md")
        required_terms = (
            "完整工作计划",
            "认定标准选择",
            "规则解释",
            "材料完整性",
            "版本顺序",
            "暂停",
            "恢复",
            "重新规划",
            "省局内网",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_markdown_plan_has_visual_states_and_real_links_only(self):
        content = read("references/markdown-plan-template.md")
        required_terms = (
            "✅",
            "❌",
            "⏳",
            "⏸️",
            "⬜",
            "本次交付",
            "实际返回",
            "计划之外单独提问",
            "不得伪造链接",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_skill_preserves_business_boundaries(self):
        content = read("SKILL.md")
        required_terms = (
            "不输出最终医保资格结论",
            "不机械调用全部",
            "不替用户确认",
            "详细澄清问题不得写入工作计划",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)


if __name__ == "__main__":
    unittest.main()
