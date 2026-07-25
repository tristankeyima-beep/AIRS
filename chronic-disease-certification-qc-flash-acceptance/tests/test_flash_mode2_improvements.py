import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TESTS_ROOT = Path(__file__).resolve().parent
ACCEPTANCE_ROOT = TESTS_ROOT.parent
SKILL_ROOT = ACCEPTANCE_ROOT.parent / "chronic-disease-certification-qc-flash"
sys.path.insert(0, str(TESTS_ROOT))

from test_flash_skill import run_qc_renderer  # noqa: E402


class FlashMode2ImprovementsTests(unittest.TestCase):
    def setUp(self):
        self.template_path = SKILL_ROOT / "assets" / "qc-report-template.html"
        self.template = self.template_path.read_text(encoding="utf-8")
        self.fixture = json.loads(
            (ACCEPTANCE_ROOT / "fixtures" / "valid-mode2.json").read_text(
                encoding="utf-8"
            )
        )

    def test_sources_is_section_03_in_navigation_and_body(self):
        nav = re.search(
            r'<nav\b[^>]*id="page-navigation"[^>]*>(.*?)</nav>',
            self.template,
            re.DOTALL,
        ).group(1)
        self.assertEqual(
            ["summary", "scope", "sources"],
            re.findall(r'href="#([^"]+)"', nav)[:3],
        )
        sources = re.search(
            r'<section id="sources".*?</section>',
            self.template,
            re.DOTALL,
        ).group(0)
        self.assertIn('<span class="number">03</span>', sources)

    def test_navigation_and_body_have_exact_nine_section_order_and_unique_ids(self):
        expected = [
            "summary",
            "scope",
            "sources",
            "dimensions",
            "issues",
            "rules",
            "recommendations",
            "analysis",
            "confirmation",
        ]
        nav = re.search(
            r'<nav\b[^>]*id="page-navigation"[^>]*>(.*?)</nav>',
            self.template,
            re.DOTALL,
        ).group(1)
        self.assertEqual(expected, re.findall(r'href="#([^"]+)"', nav))
        body_ids = re.findall(r'<section\b[^>]*id="([^"]+)"', self.template)
        self.assertEqual(expected, body_ids)
        self.assertEqual(len(expected), len(set(body_ids)))
        for number, section_id in enumerate(expected, start=1):
            section = re.search(
                rf'<section id="{section_id}".*?</section>',
                self.template,
                re.DOTALL,
            ).group(0)
            self.assertIn(
                f'<span class="number">{number:02d}</span>',
                section,
            )

    def test_summary_renders_five_comparison_items(self):
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertEqual(
            ["本次独立复核", "原审核结论", "方向判断", "质控结论", "风险方向"],
            state["summaryLabels"],
        )
        self.assertIn("相反", state["summaryText"])

    def test_summary_direction_covers_consistent_opposite_and_unknown(self):
        cases = (
            ("不予通过（原文亦写“不通过”）", "does_not_meet", "none", "一致"),
            ("不通过", "meets", "false_rejection", "相反"),
            ("待人工确定", "meets", "none", "无法判断"),
        )
        for original, preliminary, risk, expected in cases:
            with self.subTest(expected=expected):
                fixture = json.loads(json.dumps(self.fixture, ensure_ascii=False))
                fixture["auditComparison"]["originalConclusion"] = original
                fixture["baseReview"]["preliminaryResult"] = preliminary
                fixture["auditComparison"]["risk"] = risk
                state = run_qc_renderer(self.template_path, fixture)
                self.assertFalse(state["shellHidden"], state["errorText"])
                self.assertIn(expected, state["summaryText"])

    def test_scope_explains_two_stage_non_blind_without_repeating_facts(self):
        marker = "仅在逐规则事实区出现-FACT-9001"
        self.fixture["baseReview"]["materialFacts"] = [marker]
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertIn(
            "两阶段复核：先独立判断，再对照原审核",
            state["scopeText"],
        )
        self.assertIn(
            "第一阶段仅依据患者材料和认定标准",
            state["scopeText"],
        )
        self.assertIn("第二阶段再对照原审核", state["scopeText"])
        self.assertIn(
            "原审核结果在同一任务中可见，因此属于非盲复核",
            state["scopeText"],
        )
        self.assertNotIn(marker, state["scopeText"])
        self.assertIn(marker, state["rulesText"])

    def test_audit_result_has_structured_summary_and_verbatim_full_text(self):
        raw = json.dumps(
            {
                "finalResult": {"found": True, "value": "不通过"},
                "ruleResults": [{"ruleCode": "R001", "result": "不通过"}],
                "advice": "补充材料",
            },
            ensure_ascii=False,
        )
        self.fixture["sourceDocuments"][2]["content"] = raw
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertIn("结构化摘要", state["sourcesText"])
        self.assertIn("查看完整原文", state["sourcesText"])
        self.assertIn(raw, state["sourcePreTexts"])
        for marker in ("finalResult", "found", "true", "value", "不通过"):
            self.assertIn(marker, state["sourcesText"])

    def test_plain_audit_result_uses_only_explicit_labeled_boundaries(self):
        raw = (
            "finalResult: 不通过\n"
            "ruleResults: R001 不通过；提取项 1001_01=缺失\n"
            "advice: 请补充\n"
            "rawText: 引用原文逐字内容"
        )
        self.fixture["sourceDocuments"][2]["content"] = raw
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertIn("结构化摘要", state["sourcesText"])
        self.assertIn("最终结论", state["sourcesText"])
        self.assertIn("逐规则审核结果", state["sourcesText"])
        self.assertIn("审核建议", state["sourcesText"])
        self.assertIn("R001", state["sourcesText"])
        self.assertIn("1001_01", state["sourcesText"])
        self.assertIn(raw, state["sourcePreTexts"])

    def test_plain_audit_result_structures_numeric_rule_and_extraction_codes(self):
        raw = (
            "finalResult=不通过；"
            "ruleResults：1001 不通过；"
            "1001_01: value=否；"
            "1001_02: value=否；"
            "advice：复核"
        )
        self.fixture["sourceDocuments"][2]["content"] = raw
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertFalse(state["shellHidden"], state["errorText"])
        self.assertIn("结构化摘要", state["sourcesText"])
        self.assertIn("规则明细", state["sourcesText"])
        self.assertIn("1001 不通过", state["sourcesText"])
        self.assertIn("提取项卡", state["sourcesText"])
        self.assertIn("1001_01", state["sourcesText"])
        self.assertIn("1001_02", state["sourcesText"])
        self.assertNotIn(
            "原审核结果无法自动结构化，以下按原文展示",
            state["sourcesText"],
        )

    def test_ambiguous_plain_audit_result_falls_back_locally(self):
        raw = "finalResult: 只有一个明确标签，其余自由叙述不作医学推断"
        self.fixture["sourceDocuments"][2]["content"] = raw
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertFalse(state["shellHidden"], state["errorText"])
        self.assertIn(
            "原审核结果无法自动结构化，以下按原文展示",
            state["sourcesText"],
        )
        self.assertIn("查看完整原文", state["sourcesText"])
        self.assertIn(raw, state["sourcePreTexts"])

    def test_audit_json_depth_and_node_limits_fall_back_without_breaking_report(self):
        deep = {"leaf": "逐字"}
        for index in range(9):
            deep = {f"level{index}": deep}
        wide = {f"node{index}": index for index in range(501)}
        for raw in (
            json.dumps(deep, ensure_ascii=False),
            json.dumps(wide, ensure_ascii=False),
        ):
            with self.subTest(size=len(raw)):
                fixture = json.loads(json.dumps(self.fixture, ensure_ascii=False))
                fixture["sourceDocuments"][2]["content"] = raw
                state = run_qc_renderer(self.template_path, fixture)
                self.assertFalse(state["shellHidden"], state["errorText"])
                self.assertIn(
                    "原审核结果无法自动结构化，以下按原文展示",
                    state["sourcesText"],
                )
                self.assertIn(raw, state["sourcePreTexts"])

    def test_sources_have_stable_ids_and_issue_material_ids_link_or_warn(self):
        self.fixture["sourceDocuments"][0]["name"] = "材料 12345678"
        self.fixture["sourceDocuments"][0]["content"] = (
            "患者材料编号 12345678，正文证据 A。"
        )
        self.fixture["issues"][0]["sourceReference"] = "引用材料 12345678"
        self.fixture["issues"][1]["sourceReference"] = "引用材料 87654321"
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertEqual(["source-1", "source-2", "source-3"], state["sourceIds"])
        self.assertIn("#source-1", state["issueLinkTargets"])
        self.assertIn(
            "引用材料未在本报告材料清单中",
            state["issuesText"],
        )
        self.assertEqual(len(self.fixture["issues"]), state["renderedIssueCount"])

    def test_rules_fact_provenance_tmp_notice_and_not_checked_reason(self):
        self.fixture["inputProfile"]["standardKind"] = "natural_language"
        self.fixture["baseReview"]["ruleJudgments"][0]["ruleId"] = "TMP-R001"
        self.fixture["dimensions"][1] = {
            "name": self.fixture["dimensions"][1]["name"],
            "status": "not_checked",
            "summary": "输入不足",
            "notCheckedReason": "未提供可核查的提取过程",
        }
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertIn("本次质控提取的患者材料事实", state["rulesText"])
        self.assertIn("由本次质控归纳", state["rulesText"])
        self.assertIn("不代表原审核结论", state["rulesText"])
        self.assertIn("以原始材料为准", state["rulesText"])
        self.assertIn(
            "本次质控临时规则，非正式业务标准",
            state["rulesText"],
        )
        self.assertIn("本项因输入受限未核查", state["dimensionsText"])
        self.assertIn(
            "未提供可核查的提取过程",
            state["dimensionsText"],
        )

    def test_risk_validation_prioritizes_negative_and_fail_closes_mismatches(self):
        valid = run_qc_renderer(self.template_path, self.fixture)
        self.assertFalse(valid["shellHidden"], valid["errorText"])
        self.fixture["auditComparison"]["risk"] = "false_approval"
        invalid = run_qc_renderer(self.template_path, self.fixture)
        self.assertTrue(invalid["shellHidden"])
        self.assertEqual(
            "报告加载失败 风险方向与复核结论不一致",
            " ".join(invalid["errorText"].split()),
        )

    def test_risk_contract_accepts_conclusion_only_and_rule_issue_none(self):
        conclusion_only = json.loads(json.dumps(self.fixture, ensure_ascii=False))
        conclusion_only["inputProfile"]["auditDetail"] = "conclusion_only"
        conclusion_only["issues"] = []
        for dimension in conclusion_only["dimensions"][:3]:
            dimension["status"] = "not_checked"
            dimension["notCheckedReason"] = "原审核仅提供结论"
        for dimension in conclusion_only["dimensions"][3:]:
            dimension["status"] = "passed"
            dimension["notCheckedReason"] = ""
        conclusion_only["auditComparison"]["originalConclusion"] = "通过"
        conclusion_only["baseReview"]["preliminaryResult"] = "meets"
        conclusion_only["auditComparison"]["qcConclusion"] = "uncertain"
        conclusion_only["auditComparison"]["risk"] = "unknown"
        state = run_qc_renderer(self.template_path, conclusion_only)
        self.assertFalse(state["shellHidden"], state["errorText"])

        rule_issue = json.loads(json.dumps(conclusion_only, ensure_ascii=False))
        rule_issue["auditComparison"]["originalConclusion"] = "方向未明确"
        rule_issue["dimensions"][4]["status"] = "issue"
        rule_issue["dimensions"][4]["notCheckedReason"] = ""
        rule_issue["issues"] = [
            {
                "id": "I001",
                "dimension": "规则维护质量",
                "severity": "low",
                "auditClaim": "规则码格式不一致",
                "actualEvidence": "标准出现重复规则码",
                "sourceReference": "认定标准",
                "impact": "影响规则维护",
                "recommendation": "统一编号",
            }
        ]
        rule_issue["auditComparison"]["qcConclusion"] = "problematic"
        rule_issue["auditComparison"]["risk"] = "none"
        state = run_qc_renderer(self.template_path, rule_issue)
        self.assertFalse(state["shellHidden"], state["errorText"])

    def test_risk_contract_rejects_uncertain_with_issue_and_unknown_directional_risk(self):
        candidates = []
        uncertain_issue = json.loads(json.dumps(self.fixture, ensure_ascii=False))
        uncertain_issue["auditComparison"]["qcConclusion"] = "uncertain"
        uncertain_issue["auditComparison"]["risk"] = "unknown"
        candidates.append(uncertain_issue)
        unknown_direction = json.loads(json.dumps(self.fixture, ensure_ascii=False))
        unknown_direction["auditComparison"]["originalConclusion"] = "待定"
        unknown_direction["auditComparison"]["risk"] = "false_rejection"
        candidates.append(unknown_direction)
        for candidate in candidates:
            state = run_qc_renderer(self.template_path, candidate)
            self.assertTrue(state["shellHidden"])
            self.assertIn("风险方向与复核结论不一致", state["errorText"])

    def test_template_javascript_is_safe_and_valid(self):
        self.assertNotIn("innerHTML", self.template)
        self.assertNotRegex(self.template, r"\beval\s*\(")
        scripts = re.findall(
            r"<script(?:\s[^>]*)?>(.*?)</script>",
            self.template,
            re.DOTALL | re.IGNORECASE,
        )
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "renderer.js"
            script.write_text(scripts[1], encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
