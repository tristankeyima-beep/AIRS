import re
import unittest
from pathlib import Path


# Focused acceptance coverage for the strengthened Flash contracts.
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "chronic-disease-certification-qc-flash"


def read(relative_path):
    return (SKILL_ROOT / relative_path).read_text(encoding="utf-8")


def section(markdown, heading):
    match = re.search(
        rf"(?ms)^{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^## |\Z)",
        markdown,
    )
    if match is None:
        raise AssertionError(f"missing section: {heading}")
    return match.group("body")


class Mode1ContractImprovementTests(unittest.TestCase):
    def test_skill_batches_all_blocking_ambiguities_into_one_question(self):
        mode1 = section(read("SKILL.md"), "## 模式 1：生成结构化认定标准")
        self.assertIn("一次性列出当前发现的全部阻断性歧义并统一询问", mode1)
        self.assertNotIn("逐项询问每个阻断性歧义", mode1)

    def test_mode1_rule_and_quote_semantics_are_explicit(self):
        contract = read("references/mode1-contract.md")
        for marker in (
            "全部必须满足的 `AND` 子条件可以保留在同一条规则",
            "任一满足即可",
            "必须拆成多条规则",
            "由 `logic` 的 `OR` 组合",
            "单一来源中的连续原句",
            "不得拼接",
            "不得改写文字或标点",
        ):
            self.assertIn(marker, contract)

    def test_mode1_empty_code_and_version_date_semantics_are_explicit(self):
        contract = read("references/mode1-contract.md")
        for marker in (
            "`diseaseCode` 为空字符串时",
            "页面显示“未提供编码”",
            "不得判定为无效",
            "`VYYYYMMDD`",
            "成果生成日期",
            "不是政策发布日期",
        ):
            self.assertIn(marker, contract)

    def test_mode1_checklist_has_exactly_ten_atomic_items(self):
        mode1 = section(read("references/output-checklist.md"), "## 模式 1")
        items = [
            line for line in mode1.splitlines() if line.startswith("- [ ] ")
        ]
        self.assertEqual(10, len(items), items)
        expected_markers = (
            "JSON 可解析",
            "根字段",
            "逐份",
            "完整来源原文",
            "连续原句",
            "规则 ID",
            "提取项 ID",
            "逻辑树",
            "七个字段",
            "`enum` 或 `text`",
            "用户确认",
            "`flash-data`",
            "逐字段等值",
        )
        for marker in expected_markers:
            self.assertTrue(any(marker in item for item in items), marker)


class Mode2ContractImprovementTests(unittest.TestCase):
    def test_skill_does_not_read_audit_content_before_base_review(self):
        mode2 = section(
            read("SKILL.md"),
            "## 模式 2：生成智能审核质控报告",
        )
        base_review_position = mode2.index("`baseReview`")
        before_base_review = mode2[:base_review_position]
        after_base_review = mode2[base_review_position:]
        self.assertNotIn(
            "盘点患者材料、认定标准、审核过程与明细、最终结论",
            before_base_review,
        )
        for marker in (
            "第一阶段只盘点患者材料、认定标准和来源材料的名称与类型",
            "原审核材料只登记存在",
            "不得读取其主张、证据、推理或结论",
        ):
            self.assertIn(marker, before_base_review)
        self.assertIn("完成后才读取原审核内容", after_base_review)

    def test_materials_are_one_to_one_and_confirmation_is_never_assumed(self):
        skill = read("SKILL.md")
        contract = read("references/mode2-contract.md")
        for text in (skill, contract):
            self.assertIn("一份输入材料对应 `sourceDocuments` 中的一条记录", text)
            self.assertIn("不得合并材料或以摘要替代", text)
            self.assertIn("`content` 保存该份材料的完整原文", text)
            self.assertIn("用户未明确确认", text)
            self.assertIn("不得默认材料完整", text)
            self.assertIn("不得生成正式 JSON 或 HTML", text)

    def test_base_review_is_completed_without_audit_result(self):
        contract = read("references/mode2-contract.md")
        for marker in (
            "`materialFacts`、`ruleJudgments` 和 `preliminaryResult`",
            "不得读取或引用任何 `audit_result`",
            "`baseReview` 三部分全部形成后",
            "才能读取原审核",
        ):
            self.assertIn(marker, contract)

    def test_structured_and_natural_language_rule_ids_are_distinct(self):
        contract = read("references/mode2-contract.md")
        for marker in (
            "`standardKind=structured`",
            "`ruleJudgments[].ruleId`",
            "直接复用结构化标准中的正式规则码",
            "覆盖标准逻辑树中的全部规则",
            "`standardKind=natural_language`",
            "`TMP-R001`",
        ):
            self.assertIn(marker, contract)

    def test_original_material_ids_must_be_located_or_become_issues(self):
        contract = read("references/mode2-contract.md")
        for marker in (
            "原审核引用的每个材料 ID",
            "患者材料的名称或完整原文",
            "无法定位",
            "“证据提取准确性”",
            "至少为 `medium`",
            "原样写入 `issue.sourceReference`",
        ):
            self.assertIn(marker, contract)

    def test_qc_outcome_priority_has_no_conclusion_only_exception(self):
        contract = read("references/mode2-contract.md")
        for marker in (
            "五个维度全部为 `passed` 且 `issues` 为空",
            "才能使用 `reliable`",
            "存在任何实际问题",
            "必须使用 `problematic`",
            "方向一致的局部问题",
            "`problematic`、`risk=none`",
            "仅有 `not_checked` 且不存在实际问题",
            "`uncertain`、`risk=unknown`",
            "`auditDetail=conclusion_only`",
            "规则维护质量存在实际问题",
        ):
            self.assertIn(marker, contract)
        self.assertNotIn(
            "即使发现规则维护问题，也禁止标为可靠或改成 "
            "`problematic + none`",
            contract,
        )

    def test_problematic_none_preserves_directional_risk_priority(self):
        contract = read("references/mode2-contract.md")
        for marker in (
            "`problematic`、`risk=none` 表示已确认存在局部问题",
            "没有已确认的错误通过或错误拒绝方向",
            "方向一致",
            "方向不明确",
            "一旦已确认方向相反",
            "不得使用 `risk=none`",
            "`false_approval` 或 `false_rejection`",
            "规则维护问题不得覆盖",
        ):
            self.assertIn(marker, contract)

    def test_mode2_checklist_adds_atomic_improvement_checks(self):
        mode2 = section(read("references/output-checklist.md"), "## 模式 2")
        items = [
            line for line in mode2.splitlines() if line.startswith("- [ ] ")
        ]
        expected_markers = (
            "逐份来源",
            "`baseReview` 三部分",
            "读取任何 `audit_result`",
            "正式规则码",
            "逻辑树全部规则",
            "所有材料 ID",
            "患者材料名称或完整原文",
            "`reliable`",
            "`problematic`",
            "优先级",
        )
        for marker in expected_markers:
            self.assertTrue(any(marker in item for item in items), marker)

    def test_mode2_checklist_keeps_confirmed_directional_risk(self):
        mode2 = section(read("references/output-checklist.md"), "## 模式 2")
        self.assertNotIn("无论方向是否一致", mode2)
        for marker in (
            "方向相反时始终保留",
            "`false_approval` 或 `false_rejection`",
            "无已确认方向性风险",
            "`problematic + none`",
        ):
            self.assertIn(marker, mode2)


class PreservedGuardrailTests(unittest.TestCase):
    def test_common_safety_combination_and_degradation_rules_remain(self):
        skill = read("SKILL.md")
        contract = read("references/mode2-contract.md")
        checklist = read("references/output-checklist.md")
        for marker in (
            "## 组合请求",
            "模式 2 的输入完整性确认",
            "疑似 API 密钥",
            "立即停止",
            "目标服务或地址",
            "具体动作",
            "材料范围",
            "`flash-data`",
            "逐字段等值",
        ):
            self.assertIn(marker, skill + checklist)
        for marker in (
            "`standardKind=absent`",
            "`auditDetail=brief`",
            "`auditDetail=conclusion_only`",
            "`not_checked`",
        ):
            self.assertIn(marker, contract)


if __name__ == "__main__":
    unittest.main()
