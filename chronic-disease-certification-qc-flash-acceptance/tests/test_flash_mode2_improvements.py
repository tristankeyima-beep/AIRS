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

    def audit_result_source(self, fixture=None):
        candidate = self.fixture if fixture is None else fixture
        return next(
            source
            for source in candidate["sourceDocuments"]
            if source["type"] == "audit_result"
        )

    def make_conclusion_only_candidate(
        self,
        original_conclusion="通过",
        preliminary_result="meets",
    ):
        fixture = json.loads(json.dumps(self.fixture, ensure_ascii=False))
        fixture["inputProfile"]["auditDetail"] = "conclusion_only"
        fixture["issues"] = []
        for dimension in fixture["dimensions"][:3]:
            dimension["status"] = "not_checked"
            dimension["notCheckedReason"] = "原审核仅提供结论"
        for dimension in fixture["dimensions"][3:]:
            dimension["status"] = "passed"
            dimension["notCheckedReason"] = ""
        fixture["auditComparison"]["originalConclusion"] = original_conclusion
        fixture["baseReview"]["preliminaryResult"] = preliminary_result
        fixture["auditComparison"]["qcConclusion"] = "uncertain"
        fixture["auditComparison"]["risk"] = "unknown"
        return fixture

    def make_absent_conclusion_only_candidate(self):
        fixture = self.make_conclusion_only_candidate(
            original_conclusion="方向未明确",
            preliminary_result="uncertain",
        )
        fixture["inputProfile"]["standardKind"] = "absent"
        fixture["baseReview"]["ruleJudgments"] = []
        for dimension in fixture["dimensions"][3:]:
            dimension["status"] = "not_checked"
            dimension["notCheckedReason"] = "缺少认定标准，无法核查"
        return fixture

    def make_absent_visible_audit_candidate(
        self,
        audit_detail,
        with_actual_issues=False,
    ):
        fixture = json.loads(json.dumps(self.fixture, ensure_ascii=False))
        fixture["inputProfile"]["standardKind"] = "absent"
        fixture["inputProfile"]["auditDetail"] = audit_detail
        fixture["baseReview"]["preliminaryResult"] = "uncertain"
        fixture["baseReview"]["ruleJudgments"] = []
        fixture["dimensions"][4]["status"] = "not_checked"
        fixture["dimensions"][4][
            "notCheckedReason"
        ] = "缺少认定标准，无法核查"
        if with_actual_issues:
            fixture["auditComparison"]["qcConclusion"] = "problematic"
            fixture["auditComparison"]["risk"] = "none"
        else:
            fixture["issues"] = []
            for dimension in fixture["dimensions"][:4]:
                dimension["status"] = "passed"
                dimension["notCheckedReason"] = ""
            fixture["auditComparison"]["qcConclusion"] = "uncertain"
            fixture["auditComparison"]["risk"] = "unknown"
        return fixture

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
        self.audit_result_source()["content"] = raw
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
        self.audit_result_source()["content"] = raw
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
            "1001_01: 原审核认定证据 A 缺失，"
            "引用材料ID2079388752224174082；"
            "1001_02：value=否；"
            "advice：复核"
        )
        self.audit_result_source()["content"] = raw
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertFalse(state["shellHidden"], state["errorText"])
        self.assertIn("结构化摘要", state["sourcesText"])
        self.assertEqual(1, state["auditRuleNodeCount"])
        self.assertEqual(
            ["规则 1001｜不通过"],
            state["auditRuleSummaryTexts"],
        )
        self.assertEqual([2], state["auditRuleExtractionCounts"])
        self.assertEqual(
            ["提取项 1001_01", "提取项 1001_02"],
            state["auditExtractionSummaryTexts"],
        )
        self.assertEqual(
            [
                "原审核认定证据 A 缺失，"
                "引用材料ID2079388752224174082",
                "value=否",
            ],
            state["auditExtractionBodyTexts"],
        )
        self.assertNotIn(
            "2079388752224174082",
            " ".join(state["auditRuleSummaryTexts"]),
        )
        self.assertNotIn(
            "2079388752224174082",
            " ".join(state["auditExtractionSummaryTexts"]),
        )
        self.assertIn(raw, state["sourcePreTexts"])
        self.assertNotIn(
            "原审核结果无法自动结构化，以下按原文展示",
            state["sourcesText"],
        )

    def test_plain_audit_result_groups_extractions_under_each_rule(self):
        raw = (
            "最终结论：不通过；"
            "逐规则审核结果: TMP-R001 不通过；"
            "TMP-R001_01：临时规则证据不足；"
            "1002 通过；"
            "1002_01: 已找到相应证据；"
            "审核建议=人工复核"
        )
        self.audit_result_source()["content"] = raw
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertFalse(state["shellHidden"], state["errorText"])
        self.assertEqual(2, state["auditRuleNodeCount"])
        self.assertEqual(
            ["规则 TMP-R001｜不通过", "规则 1002｜通过"],
            state["auditRuleSummaryTexts"],
        )
        self.assertEqual([1, 1], state["auditRuleExtractionCounts"])
        self.assertEqual(
            ["提取项 TMP-R001_01", "提取项 1002_01"],
            state["auditExtractionSummaryTexts"],
        )
        self.assertEqual(
            ["临时规则证据不足", "已找到相应证据"],
            state["auditExtractionBodyTexts"],
        )
        self.assertIn(raw, state["sourcePreTexts"])

    def test_real_plain_audit_rule_blocks_keep_nested_extraction_values(self):
        raw = (
            "finalResult=不通过。"
            "ruleResults：1001 不通过（"
            "1001_01 found=true value=已确诊，"
            "引用材料2079388752224174082；"
            "1001_02 found=true value=否，"
            "引用材料2079388752224174085，"
            "rawText“出院情况: 目前患者神志清楚；"
            "言语清晰流利”，标注为“住院病历-5”"
            "）；"
            "1002 不通过（"
            "1002_01 value=否，"
            "引用2079388752224174084/2079388752224174083/"
            "2079388752215785472；"
            "1002_02 value=否，"
            "引用2079388752224174083/2079388752224174084"
            "）。"
            "advice：出院时神志清楚、言语清晰无遗留神经症状，"
            "不符合“仍需继续治疗”；"
            "影像未提示急性梗死灶或血管中重度狭窄。"
        )
        self.audit_result_source()["content"] = raw
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertFalse(state["shellHidden"], state["errorText"])
        self.assertEqual(2, state["auditRuleNodeCount"])
        self.assertEqual(
            ["规则 1001｜不通过", "规则 1002｜不通过"],
            state["auditRuleSummaryTexts"],
        )
        self.assertEqual([2, 2], state["auditRuleExtractionCounts"])
        self.assertEqual(
            [
                "提取项 1001_01",
                "提取项 1001_02",
                "提取项 1002_01",
                "提取项 1002_02",
            ],
            state["auditExtractionSummaryTexts"],
        )
        self.assertEqual(
            [
                "found=true value=已确诊，"
                "引用材料2079388752224174082",
                "found=true value=否，"
                "引用材料2079388752224174085，"
                "rawText“出院情况: 目前患者神志清楚；"
                "言语清晰流利”，标注为“住院病历-5”",
                "value=否，"
                "引用2079388752224174084/2079388752224174083/"
                "2079388752215785472",
                "value=否，"
                "引用2079388752224174083/2079388752224174084",
            ],
            state["auditExtractionBodyTexts"],
        )
        summaries = " ".join(
            state["auditRuleSummaryTexts"]
            + state["auditExtractionSummaryTexts"]
        )
        self.assertNotIn("2079388752224174082", summaries)
        self.assertIn(
            "影像未提示急性梗死灶或血管中重度狭窄。",
            state["sourcesText"],
        )
        self.assertIn(raw, state["sourcePreTexts"])
        self.assertNotIn(
            "原审核结果无法自动结构化，以下按原文展示",
            state["sourcesText"],
        )

    def test_plain_audit_tokenizer_declares_rule_and_extraction_budgets(self):
        self.assertRegex(
            self.template,
            r"const MAX_PLAIN_AUDIT_RULES = \d+;",
        )
        self.assertRegex(
            self.template,
            r"const MAX_PLAIN_AUDIT_EXTRACTIONS = \d+;",
        )
        self.assertIn("MAX_STRUCTURED_SOURCE_CHARS", self.template)

    def test_plain_audit_tokenizer_falls_back_when_unbalanced_or_over_budget(self):
        rule_limit = int(re.search(
            r"const MAX_PLAIN_AUDIT_RULES = (\d+);",
            self.template,
        ).group(1))
        extraction_limit = int(re.search(
            r"const MAX_PLAIN_AUDIT_EXTRACTIONS = (\d+);",
            self.template,
        ).group(1))
        too_many_rules = "；".join(
            f"{1000 + index} 通过"
            for index in range(rule_limit + 1)
        )
        too_many_extractions = "；".join(
            f"1001_{index} value=否"
            for index in range(1, extraction_limit + 2)
        )
        candidates = (
            (
                "finalResult=不通过。"
                "ruleResults：1001 不通过（"
                "1001_01 value=否；"
                "advice：括号不完整"
            ),
            (
                "finalResult=通过；"
                f"ruleResults：{too_many_rules}；"
                "advice：超出规则预算"
            ),
            (
                "finalResult=不通过；"
                f"ruleResults：1001 不通过（{too_many_extractions}）；"
                "advice：超出提取项预算"
            ),
        )
        for raw in candidates:
            with self.subTest(length=len(raw)):
                fixture = json.loads(
                    json.dumps(self.fixture, ensure_ascii=False)
                )
                self.audit_result_source(fixture)["content"] = raw
                state = run_qc_renderer(self.template_path, fixture)
                self.assertFalse(state["shellHidden"], state["errorText"])
                self.assertEqual(0, state["auditRuleNodeCount"])
                self.assertIn("按原文", state["sourcesText"])
                self.assertIn(raw, state["sourcePreTexts"])

    def test_plain_audit_result_does_not_treat_long_material_id_as_rule(self):
        raw = (
            "finalResult=不通过；"
            "ruleResults：2079388752224174082 不通过；"
            "advice：人工复核"
        )
        self.audit_result_source()["content"] = raw
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertFalse(state["shellHidden"], state["errorText"])
        self.assertEqual(0, state["auditRuleNodeCount"])
        self.assertEqual(0, len(state["auditExtractionSummaryTexts"]))
        self.assertIn(raw, state["sourcePreTexts"])

    def test_ambiguous_plain_audit_result_falls_back_locally(self):
        raw = "finalResult: 只有一个明确标签，其余自由叙述不作医学推断"
        self.audit_result_source()["content"] = raw
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
                self.audit_result_source(fixture)["content"] = raw
                state = run_qc_renderer(self.template_path, fixture)
                self.assertFalse(state["shellHidden"], state["errorText"])
                self.assertIn(
                    "原审核结果无法自动结构化，以下按原文展示",
                    state["sourcesText"],
                )
                self.assertIn(raw, state["sourcePreTexts"])

    def test_audit_json_eight_level_boundary_structures_successfully(self):
        boundary = "边界值"
        for index in range(8):
            boundary = {f"level{index}": boundary}
        raw = json.dumps(boundary, ensure_ascii=False)
        self.audit_result_source()["content"] = raw
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertFalse(state["shellHidden"], state["errorText"])
        self.assertIn("结构化摘要", state["sourcesText"])
        self.assertIn("边界值", state["sourcesText"])
        self.assertNotIn(
            "原审核结果无法自动结构化，以下按原文展示",
            state["sourcesText"],
        )
        self.assertIn(raw, state["sourcePreTexts"])

    def test_audit_json_over_character_limit_skips_structuring_and_keeps_raw(self):
        raw = json.dumps("甲" * 200001, ensure_ascii=False)
        self.audit_result_source()["content"] = raw
        state = run_qc_renderer(self.template_path, self.fixture)
        self.assertFalse(state["shellHidden"], state["errorText"])
        self.assertIn("内容较多，请查看完整原文", state["sourcesText"])
        self.assertNotIn("结构化摘要", state["sourcesText"])
        self.assertIn(raw, state["sourcePreTexts"])

    def test_structured_json_walk_is_incremental_and_budgeted(self):
        renderer = self.template[
            self.template.index("const ensureStructuredBudget ="):
            self.template.index("const explicitAuditSegments =")
        ]
        self.assertIn("MAX_STRUCTURED_SOURCE_CHARS", self.template)
        self.assertIn("MAX_STRUCTURED_DEPTH", renderer)
        self.assertIn("MAX_STRUCTURED_NODES", renderer)
        self.assertIn("for (let index = 0;", renderer)
        self.assertIn("for (const key in value)", renderer)
        self.assertIn("hasOwnProperty.call(value, key)", renderer)
        self.assertNotIn("Object.entries", renderer)
        self.assertNotRegex(renderer, r"\bvalue\.map\s*\(")

    def test_sources_have_stable_ids_and_issue_material_ids_link_or_warn(self):
        self.fixture["sourceDocuments"][0]["name"] = "材料 12345678"
        self.fixture["sourceDocuments"][0]["content"] = (
            "患者材料编号 12345678，正文证据 A。"
        )
        self.fixture["issues"][0]["sourceReference"] = "引用材料 12345678"
        self.fixture["issues"][1]["sourceReference"] = "引用材料 87654321"
        state = run_qc_renderer(self.template_path, self.fixture)
        expected_source_ids = [
            f"source-{index}"
            for index in range(1, len(self.fixture["sourceDocuments"]) + 1)
        ]
        self.assertEqual(expected_source_ids, state["sourceIds"])
        self.assertEqual(len(state["sourceIds"]), len(set(state["sourceIds"])))
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
        conclusion_only = self.make_conclusion_only_candidate()
        state = run_qc_renderer(self.template_path, conclusion_only)
        self.assertFalse(state["shellHidden"], state["errorText"])

        rule_issue = json.loads(json.dumps(conclusion_only, ensure_ascii=False))
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

        unknown_direction_issue = json.loads(
            json.dumps(rule_issue, ensure_ascii=False)
        )
        unknown_direction_issue["auditComparison"][
            "originalConclusion"
        ] = "方向未明确"
        unknown_direction_issue["dimensions"][3]["status"] = "not_checked"
        unknown_direction_issue["dimensions"][3][
            "notCheckedReason"
        ] = "原审核结论方向不明确"
        state = run_qc_renderer(self.template_path, unknown_direction_issue)
        self.assertFalse(state["shellHidden"], state["errorText"])

    def test_known_opposite_conclusion_only_cannot_degrade_to_uncertain(self):
        fixture = self.make_conclusion_only_candidate(
            original_conclusion="不通过",
            preliminary_result="meets",
        )
        state = run_qc_renderer(self.template_path, fixture)
        self.assertTrue(state["shellHidden"])
        self.assertIn("风险方向与复核结论不一致", state["errorText"])

    def test_risk_state_machine_requires_complete_status_evidence(self):
        reliable = json.loads(json.dumps(self.fixture, ensure_ascii=False))
        reliable["issues"] = []
        for dimension in reliable["dimensions"]:
            dimension["status"] = "passed"
            dimension["notCheckedReason"] = ""
        reliable["auditComparison"]["originalConclusion"] = "通过"
        reliable["baseReview"]["preliminaryResult"] = "meets"
        reliable["auditComparison"]["qcConclusion"] = "reliable"
        reliable["auditComparison"]["risk"] = "none"
        state = run_qc_renderer(self.template_path, reliable)
        self.assertFalse(state["shellHidden"], state["errorText"])

        invalid_candidates = {}
        reliable_with_unchecked = json.loads(
            json.dumps(reliable, ensure_ascii=False)
        )
        reliable_with_unchecked["dimensions"][0]["status"] = "not_checked"
        reliable_with_unchecked["dimensions"][0]["notCheckedReason"] = "受限"
        invalid_candidates["reliable requires all passed"] = (
            reliable_with_unchecked,
            "风险方向与复核结论不一致",
        )

        dimension_issue_only = json.loads(
            json.dumps(self.fixture, ensure_ascii=False)
        )
        dimension_issue_only["issues"] = []
        invalid_candidates["problematic requires issue records"] = (
            dimension_issue_only,
            "问题清单与五维问题状态不一致",
        )

        issue_records_only = json.loads(
            json.dumps(self.fixture, ensure_ascii=False)
        )
        for dimension in issue_records_only["dimensions"]:
            dimension["status"] = "passed"
            dimension["notCheckedReason"] = ""
        invalid_candidates["problematic requires dimension issue"] = (
            issue_records_only,
            "问题清单与五维问题状态不一致",
        )

        opposite_without_condition_issue = json.loads(
            json.dumps(self.fixture, ensure_ascii=False)
        )
        opposite_without_condition_issue["dimensions"][3]["status"] = "passed"
        opposite_without_condition_issue["dimensions"][3][
            "notCheckedReason"
        ] = ""
        opposite_without_condition_issue["issues"] = (
            opposite_without_condition_issue["issues"][:1]
        )
        invalid_candidates["opposite requires fourth dimension issue"] = (
            opposite_without_condition_issue,
            "风险方向与复核结论不一致",
        )

        for name, (candidate, expected_error) in invalid_candidates.items():
            with self.subTest(case=name):
                state = run_qc_renderer(self.template_path, candidate)
                self.assertTrue(state["shellHidden"])
                self.assertIn(expected_error, state["errorText"])

    def test_reliable_rejects_both_known_opposite_directions(self):
        opposite_directions = (
            ("不通过", "meets"),
            ("通过", "does_not_meet"),
        )
        for original, preliminary in opposite_directions:
            with self.subTest(
                original=original,
                preliminary=preliminary,
            ):
                fixture = json.loads(
                    json.dumps(self.fixture, ensure_ascii=False)
                )
                fixture["issues"] = []
                for dimension in fixture["dimensions"]:
                    dimension["status"] = "passed"
                    dimension["notCheckedReason"] = ""
                fixture["auditComparison"]["originalConclusion"] = original
                fixture["baseReview"]["preliminaryResult"] = preliminary
                fixture["auditComparison"]["qcConclusion"] = "reliable"
                fixture["auditComparison"]["risk"] = "none"
                state = run_qc_renderer(self.template_path, fixture)
                self.assertTrue(state["shellHidden"])
                self.assertIn(
                    "风险方向与复核结论不一致",
                    state["errorText"],
                )

    def test_audit_detail_rejects_invalid_conclusion_only_shapes(self):
        invalid_candidates = {}

        reliable = self.make_conclusion_only_candidate()
        for dimension in reliable["dimensions"]:
            dimension["status"] = "passed"
            dimension["notCheckedReason"] = ""
        reliable["auditComparison"]["qcConclusion"] = "reliable"
        reliable["auditComparison"]["risk"] = "none"
        invalid_candidates["conclusion only cannot be reliable"] = reliable

        checked_process = self.make_conclusion_only_candidate()
        checked_process["dimensions"][0]["status"] = "passed"
        checked_process["dimensions"][0]["notCheckedReason"] = ""
        invalid_candidates["first three must be not checked"] = checked_process

        unknown_direction = self.make_conclusion_only_candidate(
            original_conclusion="方向未明确",
        )
        invalid_candidates["unknown direction fourth must be not checked"] = (
            unknown_direction
        )

        visible_standard_unchecked = self.make_conclusion_only_candidate()
        visible_standard_unchecked["dimensions"][4][
            "status"
        ] = "not_checked"
        visible_standard_unchecked["dimensions"][4][
            "notCheckedReason"
        ] = "错误跳过可见标准"
        invalid_candidates["visible standard fifth must be checked"] = (
            visible_standard_unchecked
        )

        absent_standard_checked = self.make_conclusion_only_candidate(
            original_conclusion="方向未明确",
            preliminary_result="uncertain",
        )
        absent_standard_checked["inputProfile"]["standardKind"] = "absent"
        absent_standard_checked["dimensions"][3]["status"] = "not_checked"
        absent_standard_checked["dimensions"][3][
            "notCheckedReason"
        ] = "方向未知"
        invalid_candidates["absent standard fifth must be not checked"] = (
            absent_standard_checked
        )

        for name, candidate in invalid_candidates.items():
            with self.subTest(case=name):
                state = run_qc_renderer(self.template_path, candidate)
                self.assertTrue(state["shellHidden"])
                self.assertIn(
                    "风险方向与复核结论不一致",
                    state["errorText"],
                )

    def test_absent_conclusion_only_is_strictly_uncertain_and_unchecked(self):
        valid = self.make_absent_conclusion_only_candidate()
        state = run_qc_renderer(self.template_path, valid)
        self.assertFalse(state["shellHidden"], state["errorText"])

        invalid_candidates = {}
        for original, preliminary in (
            ("通过", "meets"),
            ("不通过", "does_not_meet"),
        ):
            same_direction = self.make_absent_conclusion_only_candidate()
            same_direction["auditComparison"][
                "originalConclusion"
            ] = original
            same_direction["baseReview"][
                "preliminaryResult"
            ] = preliminary
            same_direction["dimensions"][3]["status"] = "passed"
            same_direction["dimensions"][3]["notCheckedReason"] = ""
            invalid_candidates[
                f"same direction {preliminary} cannot be accepted"
            ] = same_direction

        with_rule_judgments = self.make_absent_conclusion_only_candidate()
        with_rule_judgments["baseReview"]["ruleJudgments"] = json.loads(
            json.dumps(
                self.fixture["baseReview"]["ruleJudgments"],
                ensure_ascii=False,
            )
        )
        invalid_candidates[
            "absent standard cannot have rule judgments"
        ] = with_rule_judgments

        fourth_passed = self.make_absent_conclusion_only_candidate()
        fourth_passed["dimensions"][3]["status"] = "passed"
        fourth_passed["dimensions"][3]["notCheckedReason"] = ""
        invalid_candidates["fourth dimension cannot pass"] = fourth_passed

        fourth_issue = self.make_absent_conclusion_only_candidate()
        fourth_issue["dimensions"][3]["status"] = "issue"
        fourth_issue["dimensions"][3]["notCheckedReason"] = ""
        fourth_issue["issues"] = [
            json.loads(json.dumps(self.fixture["issues"][1], ensure_ascii=False))
        ]
        fourth_issue["auditComparison"]["qcConclusion"] = "problematic"
        fourth_issue["auditComparison"]["risk"] = "none"
        invalid_candidates["fourth dimension cannot be issue"] = fourth_issue

        fifth_passed = self.make_absent_conclusion_only_candidate()
        fifth_passed["dimensions"][4]["status"] = "passed"
        fifth_passed["dimensions"][4]["notCheckedReason"] = ""
        invalid_candidates["fifth dimension cannot pass"] = fifth_passed

        fifth_issue = self.make_absent_conclusion_only_candidate()
        fifth_issue["dimensions"][4]["status"] = "issue"
        fifth_issue["dimensions"][4]["notCheckedReason"] = ""
        issue = json.loads(
            json.dumps(self.fixture["issues"][1], ensure_ascii=False)
        )
        issue["dimension"] = "规则维护质量"
        fifth_issue["issues"] = [issue]
        fifth_issue["auditComparison"]["qcConclusion"] = "problematic"
        fifth_issue["auditComparison"]["risk"] = "none"
        invalid_candidates["fifth dimension cannot be issue"] = fifth_issue

        problematic = self.make_absent_conclusion_only_candidate()
        problematic["auditComparison"]["qcConclusion"] = "problematic"
        problematic["auditComparison"]["risk"] = "none"
        invalid_candidates["qc cannot be problematic"] = problematic

        reliable = self.make_absent_conclusion_only_candidate()
        reliable["auditComparison"]["qcConclusion"] = "reliable"
        reliable["auditComparison"]["risk"] = "none"
        invalid_candidates["qc cannot be reliable"] = reliable

        for name, candidate in invalid_candidates.items():
            with self.subTest(case=name):
                state = run_qc_renderer(self.template_path, candidate)
                self.assertTrue(state["shellHidden"])
                self.assertIn(
                    "风险方向与复核结论不一致",
                    state["errorText"],
                )

    def test_absent_standard_contract_applies_to_detailed_and_brief(self):
        valid_candidates = (
            self.make_absent_visible_audit_candidate("detailed"),
            self.make_absent_visible_audit_candidate(
                "brief",
                with_actual_issues=True,
            ),
        )
        for candidate in valid_candidates:
            with self.subTest(
                valid_audit_detail=candidate["inputProfile"]["auditDetail"]
            ):
                state = run_qc_renderer(self.template_path, candidate)
                self.assertFalse(state["shellHidden"], state["errorText"])

        invalid_candidates = {}
        for audit_detail in ("detailed", "brief"):
            for original, preliminary in (
                ("通过", "meets"),
                ("不通过", "does_not_meet"),
            ):
                known_result = self.make_absent_visible_audit_candidate(
                    audit_detail
                )
                known_result["auditComparison"][
                    "originalConclusion"
                ] = original
                known_result["baseReview"][
                    "preliminaryResult"
                ] = preliminary
                invalid_candidates[
                    f"{audit_detail} cannot use {preliminary}"
                ] = known_result

            fifth_passed = self.make_absent_visible_audit_candidate(
                audit_detail
            )
            fifth_passed["dimensions"][0]["status"] = "not_checked"
            fifth_passed["dimensions"][0][
                "notCheckedReason"
            ] = "审核结果未覆盖材料完整性"
            fifth_passed["dimensions"][4]["status"] = "passed"
            fifth_passed["dimensions"][4]["notCheckedReason"] = ""
            invalid_candidates[
                f"{audit_detail} fifth dimension cannot pass"
            ] = fifth_passed

            reliable = self.make_absent_visible_audit_candidate(audit_detail)
            reliable["baseReview"]["preliminaryResult"] = "meets"
            reliable["auditComparison"]["originalConclusion"] = "通过"
            reliable["dimensions"][4]["status"] = "passed"
            reliable["dimensions"][4]["notCheckedReason"] = ""
            reliable["auditComparison"]["qcConclusion"] = "reliable"
            reliable["auditComparison"]["risk"] = "none"
            invalid_candidates[
                f"{audit_detail} cannot be reliable"
            ] = reliable

        for name, candidate in invalid_candidates.items():
            with self.subTest(case=name):
                state = run_qc_renderer(self.template_path, candidate)
                self.assertTrue(state["shellHidden"])
                self.assertIn(
                    "风险方向与复核结论不一致",
                    state["errorText"],
                )

    def test_general_reliable_requires_known_consistent_direction(self):
        fixture = json.loads(json.dumps(self.fixture, ensure_ascii=False))
        fixture["issues"] = []
        for dimension in fixture["dimensions"]:
            dimension["status"] = "passed"
            dimension["notCheckedReason"] = ""
        fixture["auditComparison"]["originalConclusion"] = "方向未明确"
        fixture["auditComparison"]["qcConclusion"] = "reliable"
        fixture["auditComparison"]["risk"] = "none"
        state = run_qc_renderer(self.template_path, fixture)
        self.assertTrue(state["shellHidden"])
        self.assertIn("风险方向与复核结论不一致", state["errorText"])

    def test_issue_dimension_sets_fail_closed_and_allow_duplicates(self):
        invalid_candidates = {}

        missing = json.loads(json.dumps(self.fixture, ensure_ascii=False))
        missing["issues"] = missing["issues"][:1]
        invalid_candidates["missing issue dimension"] = missing

        extra = json.loads(json.dumps(self.fixture, ensure_ascii=False))
        extra_issue = json.loads(
            json.dumps(extra["issues"][0], ensure_ascii=False)
        )
        extra_issue["id"] = "I003"
        extra_issue["dimension"] = "证据提取准确性"
        extra["issues"].append(extra_issue)
        invalid_candidates["extra issue dimension"] = extra

        mismatch = json.loads(json.dumps(self.fixture, ensure_ascii=False))
        mismatch["issues"][1]["dimension"] = "证据提取准确性"
        invalid_candidates["mismatched issue dimension"] = mismatch

        for name, candidate in invalid_candidates.items():
            with self.subTest(case=name):
                state = run_qc_renderer(self.template_path, candidate)
                self.assertTrue(state["shellHidden"])
                self.assertIn(
                    "问题清单与五维问题状态不一致",
                    state["errorText"],
                )

        duplicate = json.loads(json.dumps(self.fixture, ensure_ascii=False))
        duplicate_issue = json.loads(
            json.dumps(duplicate["issues"][0], ensure_ascii=False)
        )
        duplicate_issue["id"] = "I003"
        duplicate["issues"].append(duplicate_issue)
        state = run_qc_renderer(self.template_path, duplicate)
        self.assertFalse(state["shellHidden"], state["errorText"])

    def test_all_negative_original_conclusions_require_false_rejection(self):
        negative_conclusions = (
            "未通过",
            "未予通过",
            "不能通过",
            "不通过",
            "不予通过",
            "拒绝",
        )
        for original in negative_conclusions:
            with self.subTest(original=original, risk="false_rejection"):
                fixture = json.loads(
                    json.dumps(self.fixture, ensure_ascii=False)
                )
                fixture["auditComparison"]["originalConclusion"] = original
                state = run_qc_renderer(self.template_path, fixture)
                self.assertFalse(state["shellHidden"], state["errorText"])
            with self.subTest(original=original, risk="false_approval"):
                fixture["auditComparison"]["risk"] = "false_approval"
                state = run_qc_renderer(self.template_path, fixture)
                self.assertTrue(state["shellHidden"])
                self.assertIn(
                    "风险方向与复核结论不一致",
                    state["errorText"],
                )

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
