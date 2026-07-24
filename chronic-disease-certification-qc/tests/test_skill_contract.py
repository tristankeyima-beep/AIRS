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

    def assert_step_contains(self, steps, markers):
        for marker in markers:
            self.assertTrue(
                any(marker in step for step in steps.values()),
                f"Mode 1 must instruct: {marker}",
            )

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
        self.assertIn("模式 2：进行智能审核质控", skill_body)
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
        formal_step = next(
            number for number, step in steps.items() if "finalize" in step
        )
        validation_step = next(
            number
            for number, step in steps.items()
            if "validate_certification.py validate" in step
        )
        delivery_step = next(
            number for number, step in steps.items() if "certification_list" in step
        )
        self.assertIn("草案 JSON", steps[formal_step])
        self.assertIn("meta JSON", steps[formal_step])
        self.assertIn("用户明确同意后", steps[formal_step])
        self.assertIn("脚本而非模型", steps[formal_step])
        self.assertIn("render_certification_html.py", steps[validation_step])
        self.assertIn("重新读取", steps[validation_step])
        self.assertIn("完全由正式 JSON 推导", steps[validation_step])
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
        formal_step = next(
            number for number, step in steps.items() if "finalize" in step
        )
        self.assertLess(pending_step, formal_step)

    def test_skill_routes_generation_qc_and_combined_requests_in_order(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        mode_1, steps = self.mode_steps(skill_text)
        mode_2 = self.mode_body(skill_text, "模式 2：进行智能审核质控")

        self.assertIn("生成、结构化、维护或可视化", mode_1)
        self.assertIn("智能审核的质控或复核", mode_2)
        combined = re.search(r"(?ms)^## 组合请求处理[ \t]*$\n(?P<body>.*?)(?=^## |\Z)", skill_text)
        self.assertIsNotNone(combined, "Skill must define combined-request routing")
        combined_body = combined.group("body")
        required_markers = ("先完成模式 1", "阻断性歧义", "用户明确同意后", "finalize", "validate", "使用确认后的标准", "再进入模式 2", "输入清单确认")
        for marker in required_markers:
            self.assertIn(marker, combined_body)
        self.assertLess(combined_body.index("先完成模式 1"), combined_body.index("再进入模式 2"))
        self.assertTrue(any("可视化" in step for step in steps.values()))

    def test_generation_date_version_fallback_is_recorded_in_two_destinations(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        _, steps = self.mode_steps(skill_text)
        rules = (SKILL_ROOT / "references" / "structuring-rules.md").read_text(encoding="utf-8")

        for text in (skill_text, rules):
            self.assertIn("VYYYYMMDD", text)
            self.assertIn("生成日期，不是政策发布日期", text)
            self.assertIn("meta.description", text)
            self.assertIn("交付摘要", text)
        delivery_step = next(
            step for step in steps.values() if "certification_list" in step
        )
        self.assertIn("meta.description", delivery_step)
        self.assertIn("交付摘要", delivery_step)

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
