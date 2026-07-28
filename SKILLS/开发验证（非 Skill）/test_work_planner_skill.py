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

    def test_routing_distinguishes_standard_states_and_review_intents(self):
        content = read("references/intent-routing.md")
        required_terms = (
            "完全未提供标准",
            "已提供但未确认",
            "不自动检索",
            "已确认标准",
            "现行有效性",
            "临床或业务合理性",
            "能否配置",
            "现有患者材料能否覆盖规则",
            "拟修改内容",
            "适用范围",
            "业务原因或目标",
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

    def test_execution_mode_selection_precedes_authorization(self):
        required_terms = (
            "先展示完整工作计划",
            "选择执行方式不等于授权执行",
            "计划未变化",
            "不重复确认",
        )

        for relative_path in (
            "SKILL.md",
            "references/continuous-execution.md",
        ):
            content = read(relative_path)
            for required_term in required_terms:
                self.assertIn(
                    required_term,
                    content,
                    f"{relative_path}: {required_term}",
                )

    def test_continuous_execution_defines_state_transitions_and_end_states(self):
        content = read("references/continuous-execution.md")
        required_terms = (
            "⬜ → ⏳",
            "⏳ → ✅",
            "⏳ → ⏸️",
            "用户取消",
            "接受部分交付",
            "不可恢复失败",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_markdown_plan_separates_planned_and_executed_deliverables(self):
        content = read("references/markdown-plan-template.md")
        required_terms = (
            "任务目标",
            "已具备内容",
            "需提前准备",
            "依赖",
            "⬜ 计划执行后生成",
            "[交付物名称](下游或平台实际返回的文件地址)",
            "知识库未返回来源地址",
            "检索无结果",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

        planning_example = content.split(
            "### 计划模式最小示例",
            maxsplit=1,
        )[1].split(
            "### 自动执行模式最小示例",
            maxsplit=1,
        )[0]
        self.assertNotIn("❌", planning_example)
        self.assertNotIn("chronic-disease-", content)

    def test_planning_example_closes_standard_confirmation_dependencies(self):
        content = read("references/markdown-plan-template.md")
        planning_example = content.split(
            "### 计划模式最小示例",
            maxsplit=1,
        )[1].split(
            "### 自动执行模式最小示例",
            maxsplit=1,
        )[0]
        task_progress = planning_example.split(
            "## 一、任务进度",
            maxsplit=1,
        )[1].split(
            "## 二、当前状态",
            maxsplit=1,
        )[0]

        self.assertIn("确认采用的认定标准", task_progress)
        self.assertEqual(task_progress.count("| ⬜ 计划执行 |"), 3)
        self.assertIn(
            "| 3 | 生成结构化标准 | 认定标准生成 | 步骤 2 的确认结果 |",
            task_progress,
        )
        self.assertNotIn("❌", planning_example)

    def test_paused_execution_resumes_the_correct_step(self):
        content = read("references/continuous-execution.md")
        required_terms = (
            "独立确认步骤",
            "执行中的能力",
            "当前步骤 ⏸️ → ⏳",
            "取得正式成果后",
            "从下游能力内部暂停点继续",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_automatic_example_confirms_standard_and_preserves_lookup_errors(self):
        content = read("references/markdown-plan-template.md")
        automatic_example = content.split(
            "### 自动执行模式最小示例",
            maxsplit=1,
        )[1].split(
            "## 最终交付模板",
            maxsplit=1,
        )[0]

        required_example_terms = (
            "> 任务目标：检索并生成糖尿病结构化认定标准",
            "> 已具备内容：病种名称、适用地区、政策时间范围",
            "> 需提前准备：确认本次采用的认定标准",
            "确认采用的认定标准",
            "⏸️ 等待确认",
        )
        for required_term in required_example_terms:
            self.assertIn(required_term, automatic_example, required_term)

        task_progress = automatic_example.split(
            "## 一、任务进度",
            maxsplit=1,
        )[1].split(
            "## 二、当前状态",
            maxsplit=1,
        )[0]
        lookup_row = next(
            line
            for line in task_progress.splitlines()
            if "| 1 | 检索认定标准 |" in line
        )
        self.assertNotIn("患者申请材料", automatic_example)
        for policy_locator in ("病种", "地区", "时间范围"):
            self.assertIn(policy_locator, lookup_row, policy_locator)

        self.assertLess(
            task_progress.index("检索认定标准"),
            task_progress.index("确认采用的认定标准"),
        )
        self.assertLess(
            task_progress.index("确认采用的认定标准"),
            task_progress.index("生成结构化标准"),
        )

        required_error_terms = (
            "未配置",
            "鉴权失败",
            "不可访问",
            "不得归并为“检索无结果”",
        )
        for required_term in required_error_terms:
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
