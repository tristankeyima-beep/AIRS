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

    def test_mode_1_requires_source_faithful_draft_and_explicit_approval(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        mode_1 = self.mode_body(skill_text, "模式 1：生成结构化认定标准")

        required_steps = (
            "1. 读取 `references/certification-contract.md` 和 `references/structuring-rules.md`。",
            "2. 清点病种名称、病种编码、来源信息和版本信息。",
            "3. 缺少合规病种编码时询问用户，不编造编码。",
            "4. 只将用户提供的认定信息结构化为临时 R001 规则、原子提取项和嵌套逻辑拓扑。",
            "5. 独立对照来源检查遗漏、添加、阈值、单位、时长、次数、范围、逻辑、冲突和辅助细则误升级。",
            "6. 对每个阻断性歧义逐项向用户提问，不得猜测。",
            "7. 无论是否存在歧义，始终展示拟采用的规则、提取项和逻辑，并取得用户明确同意后再继续。",
            "8. 用户明确同意前，不得生成正式 JSON 或 HTML；用户修订后重复本确认关口。",
        )
        positions = []
        for step in required_steps:
            self.assertIn(step, mode_1)
            positions.append(mode_1.index(step))
        self.assertEqual(positions, sorted(positions), "Mode 1 must be an ordered imperative workflow")
        self.assertNotIn("references/report-contract.md", mode_1)

    def test_mode_1_formalization_is_script_owned_and_html_derives_from_json(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        mode_1 = self.mode_body(skill_text, "模式 1：生成结构化认定标准")

        required_steps = (
            "9. 仅在用户明确同意后，将草案 JSON 与 meta JSON 交给 `scripts/validate_certification.py finalize <草案> <meta> <正式JSON>`；由脚本而非模型分配正式编码。",
            "10. 运行 `scripts/validate_certification.py validate <正式JSON>`；通过后运行 `scripts/render_certification_html.py <正式JSON> <HTML>`，重新读取两份文件并确认业务 HTML 完全由正式 JSON 推导。",
            "11. 交付 `<病种>-certification_list-<版本>.json` 和 `<病种>-认定标准可视化-<版本>.html`。",
        )
        positions = []
        for step in required_steps:
            self.assertIn(step, mode_1)
            positions.append(mode_1.index(step))
        self.assertEqual(positions, sorted(positions))

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
            "始终在生成正式文件前取得用户明确同意后",
        )
        for wording in required_safety_wording:
            self.assertIn(wording, rules)

        ambiguities = ("AND/OR", "阈值", "单位", "时长", "次数", "范围", "排除条件", "共同前提条件", "来源冲突", "病种编码冲突")
        for ambiguity in ambiguities:
            self.assertIn(ambiguity, rules)


if __name__ == "__main__":
    unittest.main()
