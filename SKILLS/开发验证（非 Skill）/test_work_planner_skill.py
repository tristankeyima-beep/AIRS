from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-07-29-chronic-disease-work-planner.md"
)
SKILL_ROOT = (
    ROOT
    / "SKILLS"
    / "门诊慢特病工作规划与任务编排"
    / "chronic-disease-work-planner"
)


def read(relative_path):
    return (SKILL_ROOT / relative_path).read_text(encoding="utf-8")


def extract_markdown_h2_section(content, title):
    heading = f"## {title}"
    if content.startswith(heading):
        section_start = 0
    else:
        section_start = content.index(f"\n{heading}") + 1

    next_section = content.find(
        "\n## ",
        section_start + len(heading),
    )
    if next_section == -1:
        return content[section_start:]
    return content[section_start:next_section]


class WorkPlannerSkillTests(unittest.TestCase):
    def test_markdown_h2_section_stops_before_the_next_h2(self):
        content = (
            "# 文档\n"
            "\n"
            "## 测试用例\n"
            "\n"
            "章节内文字\n"
            "\n"
            "## 后续章节\n"
            "\n"
            "章节外文字\n"
        )

        section = extract_markdown_h2_section(content, "测试用例")

        self.assertIn("章节内文字", section)
        self.assertNotIn("后续章节", section)
        self.assertNotIn("章节外文字", section)

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

    def test_usage_guide_preserves_execution_failure_paths(self):
        content = read("使用说明.md")
        required_terms = (
            "可恢复失败",
            "不可恢复失败",
            "重大重新规划",
            "重新确认",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_usage_guide_defines_visual_status_contract(self):
        content = read("使用说明.md")
        status_section = content.split(
            "## 计划展示说明",
            maxsplit=1,
        )[1].split(
            "\n## ",
            maxsplit=1,
        )[0]
        status_lines = {
            icon: next(
                line
                for line in status_section.splitlines()
                if line.startswith(f"- {icon} ")
            )
            for icon in ("✅", "❌", "⏳", "⏸️", "⬜")
        }

        self.assertIn("已完成", status_lines["✅"])
        self.assertIn("取得实际成果", status_lines["✅"])
        self.assertIn("未完成或执行失败", status_lines["❌"])
        self.assertIn("进行中", status_lines["⏳"])
        self.assertIn("正在办理", status_lines["⏳"])
        self.assertIn("等待确认、补充或恢复", status_lines["⏸️"])
        self.assertIn("尚未开始", status_lines["⬜"])
        self.assertIn("只制定计划", status_lines["⬜"])
        self.assertIn("计划执行", status_lines["⬜"])
        for required_term in (
            "自动执行结束时（包括正常完成或提前终止）",
            "不得遗留",
            "⏳",
            "⏸️",
            "⬜",
            "计划模式",
            "未来步骤和成果",
            "保持 ⬜",
            "不得标为 ❌",
            "用户取消",
            "接受部分交付",
        ):
            self.assertIn(required_term, status_section, required_term)

    def test_usage_guide_acceptance_cases_are_reproducible(self):
        content = read("使用说明.md")
        acceptance_section = extract_markdown_h2_section(content, "测试用例")
        acceptance_policy = acceptance_section.split(
            "### 用例一：",
            maxsplit=1,
        )[0]
        self.assertIn(
            "必须先按各用例的 `验收前置条件` 准备或上传材料，再复制 `用户输入`",
            acceptance_policy,
        )
        self.assertIn("均为虚构测试材料", acceptance_policy)
        self.assertIn("不得包含患者隐私", acceptance_policy)
        self.assertNotIn("可选真实患者材料", acceptance_section)

        case_numbers = ("一", "二", "三", "四", "五", "六")
        cases = {}
        for index, case_number in enumerate(case_numbers):
            case_content = acceptance_section.split(
                f"### 用例{case_number}：",
                maxsplit=1,
            )[1]
            if index + 1 < len(case_numbers):
                case_content = case_content.split(
                    f"### 用例{case_numbers[index + 1]}：",
                    maxsplit=1,
                )[0]
            cases[case_number] = case_content
            for field in (
                "验收前置条件",
                "用户输入",
                "期望引导",
                "计划路线",
                "预期成果",
                "不得出现",
            ):
                self.assertIn(f"**{field}**", case_content, f"用例{case_number}: {field}")

        preconditions = {
            case_number: cases[case_number].split(
                "**验收前置条件**",
                maxsplit=1,
            )[1].split(
                "**用户输入**",
                maxsplit=1,
            )[0]
            for case_number in case_numbers
        }

        for case_number in case_numbers:
            self.assertTrue(preconditions[case_number].strip(), f"用例{case_number}: 前置条件为空")

        for case_number in ("一", "二", "三", "六"):
            self.assertIn(
                "患者材料",
                preconditions[case_number],
                f"用例{case_number}: 前置条件未说明患者材料夹具",
            )
            self.assertIn(
                "虚构",
                preconditions[case_number],
                f"用例{case_number}: 患者材料夹具前置条件未明确为虚构材料",
            )

    def test_implementation_plan_validates_all_suites_and_scans(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        expected_suite_contracts = (
            ("SKILLS/开发验证（非 Skill）", "27 项"),
            (
                "SKILLS/慢病知识库检索/"
                "chronic-disease-knowledge-retrieval/tests",
                "28 项",
            ),
            (
                "SKILLS/门诊慢特病认定标准与审核质控助手（完整版）/"
                "chronic-disease-certification-qc/tests",
                "216 项",
            ),
        )

        for suite_path, expected_count in expected_suite_contracts:
            self.assertIn(suite_path, content, suite_path)
            self.assertIn(expected_count, content, expected_count)

        self.assertIn("当前期望合计：271 项", content)
        self.assertIn(
            "TBD|TODO|待实现|lorem ipsum|placeholder",
            content,
        )
        self.assertNotIn(
            "TBD|TODO|待补充|placeholder|lorem ipsum",
            content,
        )
        self.assertIn("rg -n '[A-Za-z]'", content)
        for allowed_english in (
            "Skill ID",
            "Markdown",
            "ADP",
            "配置字段",
            "测试代号",
            "医学单位",
        ):
            self.assertIn(allowed_english, content, allowed_english)

    def test_usage_guide_case_four_static_contract_supports_manual_acceptance(self):
        content = read("使用说明.md")
        case_four = content.split(
            "### 用例四：",
            maxsplit=1,
        )[1].split(
            "### 用例五：",
            maxsplit=1,
        )[0]
        precondition = case_four.split(
            "**验收前置条件**",
            maxsplit=1,
        )[1].split(
            "**用户输入**",
            maxsplit=1,
        )[0]
        expected_guidance = case_four.split(
            "**期望引导**",
            maxsplit=1,
        )[1].split(
            "**计划路线**",
            maxsplit=1,
        )[0]
        planned_route = case_four.split(
            "**计划路线**",
            maxsplit=1,
        )[1].split(
            "**预期成果**",
            maxsplit=1,
        )[0]

        for supplied_context in ("适用范围", "原因"):
            self.assertIn(supplied_context, precondition)
        for expected_behavior in (
            "复述已识别",
            "不重复询问",
            "具体阈值",
            "观察期限",
            "阻断性歧义",
        ):
            self.assertIn(expected_behavior, expected_guidance)
        for route_behavior in (
            "按已知信息推进",
            "未明确的阈值和观察期限",
            "计划外确认",
        ):
            self.assertIn(route_behavior, planned_route)

        for ordered_stage in (
            "确认",
            "阈值",
            "观察期限",
            "检索",
            "拟修订版",
            "版本影响",
        ):
            self.assertIn(ordered_stage, planned_route)

        confirmation_position = planned_route.index("确认")
        threshold_position = planned_route.index("阈值")
        duration_position = planned_route.index("观察期限")
        retrieval_position = planned_route.index("检索")
        draft_position = planned_route.index("拟修订版")
        impact_position = planned_route.index("版本影响")

        for prerequisite_position in (
            confirmation_position,
            threshold_position,
            duration_position,
        ):
            self.assertLess(prerequisite_position, retrieval_position)
        self.assertLess(retrieval_position, draft_position)
        self.assertLess(draft_position, impact_position)

        # 助手在实际对话中是否确实避免重复提问，仍须由 ADP 人工验收。

    def test_usage_guide_limits_qc_when_original_review_is_incomplete(self):
        content = read("使用说明.md")
        for required_term in (
            "原审核只有结论或摘要时",
            "仅复核可见内容",
            "未核查",
        ):
            self.assertIn(required_term, content, required_term)


if __name__ == "__main__":
    unittest.main()
