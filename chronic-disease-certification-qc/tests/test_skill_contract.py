import re
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def mode_body(self, skill_text, heading):
        section = re.search(
            rf"(?ms)^## {re.escape(heading)}[ \t]*$\n(?P<body>.*?)(?=^## |\Z)",
            skill_text,
        )
        self.assertIsNotNone(section, f"SKILL.md must contain ## {heading}")
        return section.group("body")

    def mode_steps(self, skill_text):
        mode_1 = self.mode_body(skill_text, "模式 1：生成结构化认定标准")
        steps = [
            (int(number), text)
            for number, text in re.findall(r"(?m)^(\d+)\. (.+)$", mode_1)
        ]
        self.assertGreaterEqual(len(steps), 10, "Mode 1 needs a complete imperative workflow")
        self.assertEqual(
            [number for number, _ in steps],
            list(range(1, len(steps) + 1)),
            "Mode 1 steps must remain consecutively numbered",
        )
        return mode_1, dict(steps)

    def mode_2_steps(self, skill_text):
        mode_2 = self.mode_body(skill_text, "模式 2：生成智能审核质控报告")
        steps = [
            (int(number), text)
            for number, text in re.findall(r"(?m)^(\d+)\. (.+)$", mode_2)
        ]
        self.assertGreaterEqual(len(steps), 11, "Mode 2 needs an ordered QC workflow")
        self.assertEqual(
            [number for number, _ in steps],
            list(range(1, len(steps) + 1)),
            "Mode 2 steps must remain consecutively numbered",
        )
        return mode_2, dict(steps)

    def mode_2_step_number(self, steps, marker):
        matches = [number for number, step in steps.items() if marker in step]
        self.assertEqual(len(matches), 1, f"Mode 2 needs one step containing: {marker}")
        return matches[0]

    def assert_step_contains(self, steps, markers):
        for marker in markers:
            self.assertTrue(
                any(marker in step for step in steps.values()),
                f"Mode 1 must instruct: {marker}",
            )

    def step_number(self, steps, marker):
        matches = [number for number, step in steps.items() if marker in step]
        self.assertEqual(len(matches), 1, f"Mode 1 needs one step containing: {marker}")
        return matches[0]

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
        self.assertIn("模式 1：生成结构化认定标准", skill_body)
        self.assertIn("模式 2：生成智能审核质控报告", skill_body)
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

    def test_mode_1_requires_source_faithful_draft_and_explicit_approval(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        mode_1, steps = self.mode_steps(skill_text)

        self.assertIn("references/certification-contract.md", steps[1])
        self.assertIn("references/structuring-rules.md", steps[1])
        self.assertNotIn("references/report-contract.md", steps[1])
        self.assert_step_contains(steps, ("病种名称", "病种编码", "来源", "版本"))
        self.assert_step_contains(steps, ("缺少合规病种编码", "询问用户", "不编造编码"))
        self.assert_step_contains(steps, ("只将用户提供的认定信息", "R001", "原子提取项", "嵌套逻辑"))
        self.assert_step_contains(steps, ("独立对照来源", "遗漏", "阈值", "单位", "时长", "次数", "范围", "辅助细则"))
        self.assert_step_contains(steps, ("阻断性歧义", "逐项", "不得猜测"))
        self.assert_step_contains(steps, ("重新展示", "规则、提取项和逻辑", "用户明确同意后"))
        self.assertIn("不得生成正式 JSON", mode_1)
        self.assertNotIn("references/report-contract.md", mode_1)

    def test_mode_1_formalization_is_script_owned_and_html_derives_from_json(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        _, steps = self.mode_steps(skill_text)
        inventory_step = self.step_number(steps, "清点病种名称")
        targeted_questions_step = self.step_number(steps, "逐项向用户提问")
        pending_step = self.step_number(steps, "待确认提案")
        approval_step = self.step_number(steps, "重新展示")
        fallback_metadata_step = self.step_number(steps, "草案确认前")
        formal_step = self.step_number(steps, "finalize")
        validation_step = self.step_number(steps, "validate_certification.py validate")
        delivery_step = self.step_number(steps, "certification_list")
        self.assertIn("草案 JSON", steps[formal_step])
        self.assertIn("meta JSON", steps[formal_step])
        self.assertIn("用户明确同意后", steps[formal_step])
        self.assertIn("脚本而非模型", steps[formal_step])
        self.assertIn("render_certification_html.py", steps[validation_step])
        self.assertIn("重新读取", steps[validation_step])
        self.assertIn("完全由正式 JSON 推导", steps[validation_step])
        self.assertIn("meta.description", steps[fallback_metadata_step])
        self.assertIn("生成日期，不是政策发布日期", steps[fallback_metadata_step])
        self.assertIn("交付摘要", steps[delivery_step])
        self.assertIn("生成日期，不是政策发布日期", steps[delivery_step])
        self.assertIn("核验", steps[delivery_step])
        self.assertNotIn("meta.description", steps[delivery_step])
        self.assertLess(targeted_questions_step, pending_step)
        self.assertLess(pending_step, approval_step)
        self.assertLess(inventory_step, fallback_metadata_step)
        self.assertLess(fallback_metadata_step, targeted_questions_step)
        self.assertLess(approval_step, formal_step)
        self.assertLess(fallback_metadata_step, formal_step)
        self.assertLess(formal_step, validation_step)
        self.assertLess(validation_step, delivery_step)
        self.assertIn("认定标准可视化", steps[delivery_step])

    def test_unresolved_ambiguity_ends_at_pending_proposal_even_with_approval(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        mode_1, steps = self.mode_steps(skill_text)
        rules = (SKILL_ROOT / "references" / "structuring-rules.md").read_text(encoding="utf-8")

        for text in (mode_1, rules):
            self.assertIn("用户明确同意不能代替阻断性歧义的解决", text)
            self.assertIn("用户说不知道、无法决定", text)
            self.assertIn("待确认提案", text)
            self.assertIn("阻断性歧义未解决", text)
            self.assertIn("不得生成正式 JSON", text)
            self.assertIn("重新展示", text)
            self.assertIn("用户明确同意后", text)

        pending_step = next(
            number for number, step in steps.items() if "待确认提案" in step
        )
        formal_step = self.step_number(steps, "finalize")
        self.assertLess(pending_step, formal_step)

    def test_skill_routes_generation_qc_and_combined_requests_in_order(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        mode_1, steps = self.mode_steps(skill_text)
        mode_2 = self.mode_body(skill_text, "模式 2：生成智能审核质控报告")

        self.assertIn("生成、结构化、维护或可视化", mode_1)
        self.assertIn("智能审核的质控或复核", mode_2)
        combined = re.search(r"(?ms)^## 组合请求处理[ \t]*$\n(?P<body>.*?)(?=^## |\Z)", skill_text)
        self.assertIsNotNone(combined, "Skill must define combined-request routing")
        combined_body = combined.group("body")
        required_markers = ("先完成模式 1", "阻断性歧义", "用户明确同意后", "finalize", "validate", "使用确认后的标准", "再进入模式 2", "输入清单确认")
        for marker in required_markers:
            self.assertIn(marker, combined_body)
        combined_order = ("先完成模式 1", "用户明确同意后", "finalize", "validate", "再进入模式 2")
        indexes = [combined_body.index(marker) for marker in combined_order]
        self.assertEqual(indexes, sorted(indexes))
        self.assertTrue(any("可视化" in step for step in steps.values()))

    def test_mode_2_is_an_ordered_confirmation_gated_blind_review_workflow(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        mode_2, steps = self.mode_2_steps(skill_text)

        read_refs = self.mode_2_step_number(steps, "references/input-adapters.md")
        inventory = self.mode_2_step_number(steps, "变体 A")
        omission_question = self.mode_2_step_number(steps, "是否遗漏任何内容")
        confirmation = self.mode_2_step_number(steps, "inputScope.confirmedByUser=true")
        classify = self.mode_2_step_number(steps, "inspect_standard.py")
        independent = self.mode_2_step_number(steps, "隔离的子代理")
        comparison = self.mode_2_step_number(steps, "原审核结果比对")
        canonical = self.mode_2_step_number(steps, "写入同一个规范对象")
        renderer = self.mode_2_step_number(steps, "render_qc_html.py")
        parity = self.mode_2_step_number(steps, "一致性核验")
        self.assertEqual(read_refs, 1)
        self.assertEqual(
            [read_refs, inventory, omission_question, confirmation, classify, independent,
             comparison, canonical, renderer, parity],
            sorted([read_refs, inventory, omission_question, confirmation, classify, independent,
                    comparison, canonical, renderer, parity]),
        )
        self.assertIn("变体 B", steps[inventory])
        self.assertIn("正式文本或 HTML", steps[omission_question])
        self.assertIn("用户补充", steps[omission_question])
        self.assertIn("重新清点", steps[omission_question])
        self.assertIn("明确确认没有更多内容", steps[confirmation])
        self.assertIn("不使用原审核结果", steps[independent])
        self.assertIn("evaluate_logic.py", steps[independent])
        self.assertIn("not_run", steps[comparison])
        self.assertIn("五个维度", steps[canonical])
        self.assertIn("--text-output", steps[renderer])
        self.assertIn("直接返回", steps[renderer])
        self.assertIn("高风险", steps[parity])
        self.assertIn("急", mode_2)

    def test_mode_2_standard_scopes_temporary_rules_and_brief_result_limits(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        mode_2, steps = self.mode_2_steps(skill_text)
        adapters = (SKILL_ROOT / "references" / "input-adapters.md").read_text(encoding="utf-8")
        rubric = (SKILL_ROOT / "references" / "qc-rubric.md").read_text(encoding="utf-8")

        for text in (mode_2, adapters):
            for marker in ("structured_complete", "structured_incomplete", "natural_language", "absent"):
                self.assertIn(marker, text)
            self.assertIn("自然语言", text)
            self.assertIn("TMP-R001", text)
            self.assertIn("原文引用", text)
            self.assertIn("原子事实", text)
            self.assertIn("嵌套 AND/OR", text)
            self.assertIn("不得作为正式标准", text)
            self.assertIn("不影响结论", text)
            self.assertIn("影响结论", text)
            self.assertIn("无法确定", text)
            self.assertIn("人工确认", text)
            self.assertIn("不完整结构化", text)
            self.assertIn("结构缺陷", text)
            self.assertIn("未提供认定标准", text)
            self.assertIn("不得断言独立政策", text)
            self.assertIn("仅有简要", text)
            self.assertIn("not_run", text)

        self.assertIn("证据提取", rubric)
        self.assertIn("规则条件", rubric)
        self.assertIn("不推断缺失细节", mode_2)
        self.assertIn("审核结果已经可见", mode_2)
        self.assertIn("不能跳过", mode_2)

    def test_mode_2_requires_all_dimensions_traceable_issues_and_safe_evidence_rules(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        _, steps = self.mode_2_steps(skill_text)
        rubric = (SKILL_ROOT / "references" / "qc-rubric.md").read_text(encoding="utf-8")
        contract = (SKILL_ROOT / "references" / "report-contract.md").read_text(encoding="utf-8")

        for text in ("\n".join(steps.values()), rubric):
            for marker in ("材料缺失", "证据提取", "过度推理", "条件与结论", "规则维护"):
                self.assertIn(marker, text)
        for marker in ("整份材料缺失", "NOT_FOUND", "INSUFFICIENT", "CONTRADICTED", "CONFLICTED", "反向检索"):
            self.assertIn(marker, rubric)
        for marker in ("否定", "疑似", "既往", "排除", "一次", "上位概念"):
            self.assertIn(marker, rubric)
        for marker in ("提取项", "歧义", "矛盾", "非原子", "来源边界", "AND/OR", "路径", "细则升级"):
            self.assertIn(marker, rubric)
        for marker in ("模型主张", "实际材料或标准", "问题原因", "可能影响", "建议", "置信度", "evidenceStatus", "原文", "位置"):
            self.assertIn(marker, contract)
        for marker in ("changed", "potentially_changed", "unchanged", "unknown", "false_approval", "false_rejection", "both", "none"):
            self.assertIn(marker, rubric)

    def test_report_contract_locks_confirmation_and_shared_renderer_delivery(self):
        contract = (SKILL_ROOT / "references" / "report-contract.md").read_text(encoding="utf-8")
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for marker in ("confirmedByUser", "用户明确确认", "正式文本", "HTML", "同一个规范对象", "render_qc_html.py", "直接返回", "重新读取", "一致性核验"):
            self.assertIn(marker, contract + skill_text)
        self.assertIn("审计结论说没有漏传", skill_text)
        self.assertIn("清点之后", skill_text)
        self.assertIn("结论-only", skill_text)

    def test_qc_references_lock_rule_maintenance_taxonomy_risk_label_and_interpretation_paths(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        adapters = (SKILL_ROOT / "references" / "input-adapters.md").read_text(encoding="utf-8")
        rubric = (SKILL_ROOT / "references" / "qc-rubric.md").read_text(encoding="utf-8")
        contract = (SKILL_ROOT / "references" / "report-contract.md").read_text(encoding="utf-8")
        renderer = (SKILL_ROOT / "scripts" / "render_qc_html.py").read_text(encoding="utf-8")

        for marker in (
            "缺少提取项", "规则编码", "枚举", "来源字段", "逻辑引用", "重复编码",
            "非原子", "肯定证据", "反向证据", "无法判断边界", "规则与提取项不一致",
            "重复", "矛盾", "歧义", "来源要求的事实", "来源外条件", "AND/OR", "嵌套",
            "认定路径", "辅助细则升级",
        ):
            self.assertIn(marker, rubric)
        for text in (rubric, contract, renderer):
            self.assertIn("未发现明显风险", text)
            self.assertNotIn("未发现直接风险", text)
        self.assertIn("interpretationPaths", skill)
        for text in (adapters, rubric, contract, renderer):
            self.assertIn("interpretationPaths", text)
            self.assertIn("pathId", text)
            self.assertIn("ruleResults", text)
            self.assertIn("finalResult", text)
        for marker in ("至少 2", "不得全部相同", "qcConclusion", "无法确定", "人工确认"):
            self.assertIn(marker, adapters + rubric + contract)

    def test_mode_2_documents_auditable_inventory_isolation_and_executable_commands(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        adapters = (SKILL_ROOT / "references" / "input-adapters.md").read_text(encoding="utf-8")
        rubric = (SKILL_ROOT / "references" / "qc-rubric.md").read_text(encoding="utf-8")
        contract = (SKILL_ROOT / "references" / "report-contract.md").read_text(encoding="utf-8")
        joined = skill + adapters + rubric + contract

        for marker in ("inputScope.inventory", "revision", "inventorySha256", "userStatement", "referencedButMissing", "independentReview", "artifactSha256", "completedBeforeComparison", "isolated_blind", "independent_non_blind", "确认偏差", "冻结", "SHA-256"):
            self.assertIn(marker, joined)
        for marker in ("structured_complete", "structured_incomplete", "natural_language", "absent", "detailed", "brief", "conclusion_only", "材料缺失判断准确性", "证据提取准确性", "过度推理", "审核条件与结论一致性", "规则维护质量", "错误放行与错误拒绝风险"):
            self.assertIn(marker, joined)
        self.assertIn("python3 scripts/evaluate_logic.py", skill)
        self.assertIn("--output", skill)
        self.assertIn("python3 scripts/render_qc_html.py", skill + contract)

    def test_generation_date_version_fallback_is_recorded_in_two_destinations(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        _, steps = self.mode_steps(skill_text)
        rules = (SKILL_ROOT / "references" / "structuring-rules.md").read_text(encoding="utf-8")

        for text in (skill_text, rules):
            self.assertIn("VYYYYMMDD", text)
            self.assertIn("生成日期，不是政策发布日期", text)
            self.assertIn("meta.description", text)
            self.assertIn("交付摘要", text)
        self.assertIn("草案确认前", rules)
        self.assertIn("验证和渲染后", rules)
        metadata_step = steps[self.step_number(steps, "草案确认前")]
        delivery_step = steps[self.step_number(steps, "certification_list")]
        self.assertIn("meta.description", metadata_step)
        self.assertNotIn("meta.description", delivery_step)
        self.assertIn("交付摘要", delivery_step)
        self.assertIn("核验", delivery_step)
        self.assertLess(self.step_number(steps, "草案确认前"), self.step_number(steps, "finalize"))

    def test_structuring_rules_lock_source_fidelity_atomic_guides_and_versions(self):
        rules_path = SKILL_ROOT / "references" / "structuring-rules.md"
        self.assertTrue(rules_path.is_file(), "Mode 1 must have reusable structuring rules")
        rules = rules_path.read_text(encoding="utf-8")

        headings = (
            "# 结构化认定标准生成规范",
            "## 来源边界",
            "## 规则拆解",
            "## 提取项",
            "## 逻辑",
            "## 编码",
            "## 版本",
            "## 正式文件名",
            "## 阻断性歧义",
            "## 常见错误",
        )
        for heading in headings:
            self.assertIn(heading, rules)

        required_safety_wording = (
            "只使用用户提供的认定信息",
            "病种名称仅用于理解上下文",
            "不得自动补充确诊、检查、治疗、机构等级、并发症、排除条件、阈值等",
            "只有直接决定认定资格的准入条件生成规则",
            "辅助细则只能补强对应规则的证据口径，不得独立升级成规则",
            "一个复合准入条件可以是一条规则",
            "一个提取项只验证一个原子事实",
            "肯定证据",
            "反向证据",
            "无法判断",
            "优先材料位置",
            "满足、不满足和无法判断",
            "string 的 enumOptions 固定为 []",
            "保留 AND/OR 与共同前提条件的嵌套层级，不得扁平化",
            "临时规则使用 R001、R002",
            "正式编码只能由脚本生成",
            "用户版本 > 来源版本 > 生成日期 VYYYYMMDD",
            "不是政策发布日期",
            "<病种>-certification_list-<版本>.json",
            "<病种>-认定标准可视化-<版本>.html",
            "不得用含糊表述掩盖歧义",
            "重新展示拟采用的规则、提取项和逻辑",
            "用户明确同意不能代替阻断性歧义的解决",
            "用户说不知道、无法决定",
            "待确认提案",
            "阻断性歧义未解决",
            "meta.description",
            "交付摘要",
        )
        for wording in required_safety_wording:
            self.assertIn(wording, rules)

        ambiguities = ("AND/OR", "阈值", "单位", "时长", "次数", "范围", "排除条件", "共同前提条件", "来源冲突", "病种编码冲突")
        for ambiguity in ambiguities:
            self.assertIn(ambiguity, rules)


if __name__ == "__main__":
    unittest.main()
