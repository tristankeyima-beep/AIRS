import copy
import json
import sys
import unittest
from pathlib import Path


TESTS_ROOT = Path(__file__).resolve().parent
ACCEPTANCE_ROOT = TESTS_ROOT.parent
SKILL_ROOT = ACCEPTANCE_ROOT.parent / "chronic-disease-certification-qc-flash"
sys.path.insert(0, str(TESTS_ROOT))

from test_flash_skill import run_qc_renderer  # noqa: E402


def read(relative_path):
    return (SKILL_ROOT / relative_path).read_text(encoding="utf-8")


class FlashMode2AdpDocumentationTests(unittest.TestCase):
    def test_generation_checklist_has_pre_confirmation_conclusion_self_check(self):
        checklist = read("references/output-checklist.md")
        mode2 = checklist[checklist.index("## 模式 2") :]
        heading = "### 模式 2 结论语义自检（生成前必做）"
        self.assertIn(heading, mode2)
        self.assertLess(
            mode2.index(heading),
            mode2.index("- [ ] 确认清单："),
        )
        self_check = mode2[
            mode2.index(heading) : mode2.index("- [ ] 确认清单：")
        ]
        for marker in (
            "五维全 `passed` 且 `issues` 为空",
            "`reliable`",
            "`risk=none`",
            "任一维度为 `issue` 或 `issues` 非空",
            "必须为 `problematic`",
            "不受方向一致影响",
            "`false_approval`",
            "`false_rejection`",
            "方向一致或方向不明确",
            "`problematic + none`",
            "只有 `not_checked` 且无实际问题",
            "`uncertain + unknown`",
            "任何实际问题的 `problematic` 优先于",
        ):
            self.assertIn(marker, self_check)

    def test_generation_checklist_rejects_stale_disease_context(self):
        mode2 = read("references/output-checklist.md")
        for marker in (
            "`meta.diseaseName`",
            "`meta.reportTitle`",
            "来自本轮输入",
            "未沿用上一轮上下文",
        ):
            self.assertIn(marker, mode2)

    def test_contract_has_five_row_qc_conclusion_quick_reference(self):
        contract = read("references/mode2-contract.md")
        heading = "### qcConclusion 速查表"
        self.assertIn(heading, contract)
        table = contract[
            contract.index(heading) : contract.index(
                "## 五个质控维度",
            )
        ]
        expected_rows = (
            ("全 `passed` 且 `issues` 为空", "`reliable`", "`none`"),
            ("有 `issue`，方向一致或不明确", "`problematic`", "`none`"),
            ("原审核通过、独立复核不通过", "`problematic`", "`false_approval`"),
            ("原审核不通过、独立复核通过", "`problematic`", "`false_rejection`"),
            ("仅有 `not_checked` 且无实际问题", "`uncertain`", "`unknown`"),
        )
        table_rows = [
            line for line in table.splitlines()
            if line.startswith("|") and "---" not in line
        ]
        for expected in expected_rows:
            self.assertTrue(
                any(all(marker in row for marker in expected) for row in table_rows),
                expected,
            )

    def test_contract_constrains_disease_name_and_title_to_current_input(self):
        contract = read("references/mode2-contract.md")
        heading = "## 病种名与标题来源约束"
        self.assertIn(heading, contract)
        meta_position = contract.index("- `meta` 字段恰好为")
        heading_position = contract.index(heading)
        base_review_position = contract.index("## `baseReview`")
        self.assertLess(meta_position, heading_position)
        self.assertLess(heading_position, base_review_position)
        self.assertIn(
            "详见下方“病种名与标题来源约束”",
            contract[meta_position:heading_position],
        )
        section = contract[heading_position:base_review_position]
        for marker in (
            "`meta.diseaseName`",
            "`meta.reportTitle`",
            "严格来自本轮输入所针对的病种",
            "不得沿用上一轮模式 1",
            "其他历史病种",
            "上轮病种+转+本轮病种",
            "单一审核对象",
            "以审核对象病种为准",
            "本轮认定标准或患者材料",
            "找到依据",
        ):
            self.assertIn(marker, section)


class FlashMode2AdpRendererTests(unittest.TestCase):
    ACTUAL_ISSUE_ERROR = (
        "报告加载失败 reliable 要求五维全 passed 且 issues 为空"
        "（即“可靠”要求五维全部“已通过”且问题清单为空）；"
        "当前存在实际问题，应改为 problematic（存在问题）"
    )
    RISK_ERROR = (
        "报告加载失败 reliable 时 risk 必须为 none"
        "（“可靠”时风险方向必须为“无”）"
    )

    def setUp(self):
        self.template_path = SKILL_ROOT / "assets" / "qc-report-template.html"
        self.fixture = json.loads(
            (
                ACCEPTANCE_ROOT / "fixtures" / "valid-mode2.json"
            ).read_text(encoding="utf-8")
        )

    def make_reliable(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["issues"] = []
        for dimension in candidate["dimensions"]:
            dimension["status"] = "passed"
            dimension["notCheckedReason"] = ""
        candidate["auditComparison"]["originalConclusion"] = "通过"
        candidate["baseReview"]["preliminaryResult"] = "meets"
        candidate["auditComparison"]["qcConclusion"] = "reliable"
        candidate["auditComparison"]["risk"] = "none"
        return candidate

    def sample_issue(self):
        return {
            "id": "I001",
            "dimension": "材料缺失判断准确性",
            "severity": "low",
            "auditClaim": "原审核遗漏局部材料事实",
            "actualEvidence": "患者材料中存在该局部事实",
            "sourceReference": "患者材料-2079388752224174082",
            "impact": "不改变通过方向，但影响报告准确性",
            "recommendation": "补充该局部事实",
        }

    def assert_error(self, candidate, expected):
        state = run_qc_renderer(self.template_path, candidate)
        self.assertTrue(state["shellHidden"])
        self.assertEqual(expected, " ".join(state["errorText"].split()))

    def test_reliable_structure_mismatch_precedes_specific_diagnostic(self):
        candidates = {}

        dimension_only = self.make_reliable()
        dimension_only["dimensions"][0]["status"] = "issue"
        candidates["dimension issue only"] = dimension_only

        issue_record_only = self.make_reliable()
        issue_record_only["issues"] = [self.sample_issue()]
        candidates["issue record only"] = issue_record_only

        for name, candidate in candidates.items():
            with self.subTest(case=name):
                self.assert_error(
                    candidate,
                    "报告加载失败 问题清单与五维问题状态不一致",
                )

    def test_reliable_with_matched_issue_sets_has_specific_bilingual_diagnostic(self):
        both = self.make_reliable()
        both["dimensions"][0]["status"] = "issue"
        both["issues"] = [self.sample_issue()]
        self.assert_error(both, self.ACTUAL_ISSUE_ERROR)

    def test_reliable_with_non_none_risk_has_specific_bilingual_diagnostic(self):
        candidate = self.make_reliable()
        candidate["auditComparison"]["risk"] = "false_approval"
        self.assert_error(candidate, self.RISK_ERROR)

    def test_actual_issue_diagnostic_precedes_reliable_risk_diagnostic(self):
        candidate = self.make_reliable()
        candidate["dimensions"][0]["status"] = "issue"
        candidate["issues"] = [self.sample_issue()]
        candidate["auditComparison"]["risk"] = "false_approval"
        self.assert_error(candidate, self.ACTUAL_ISSUE_ERROR)

    def test_legal_reliable_report_still_renders(self):
        state = run_qc_renderer(self.template_path, self.make_reliable())
        self.assertFalse(state["shellHidden"], state["errorText"])

    def test_legal_direction_consistent_local_problematic_none_still_renders(self):
        candidate = self.make_reliable()
        candidate["dimensions"][0]["status"] = "issue"
        candidate["issues"] = [self.sample_issue()]
        candidate["auditComparison"]["qcConclusion"] = "problematic"
        candidate["auditComparison"]["risk"] = "none"
        state = run_qc_renderer(self.template_path, candidate)
        self.assertFalse(state["shellHidden"], state["errorText"])


if __name__ == "__main__":
    unittest.main()
