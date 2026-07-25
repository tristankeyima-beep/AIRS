import json
import copy
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_ROOT))

from test_flash_skill import run_mode1_renderer


class FlashMode1ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.template_path = (
            REPO_ROOT
            / "chronic-disease-certification-qc-flash"
            / "assets"
            / "certification-template.html"
        )
        self.fixture_path = (
            REPO_ROOT
            / "chronic-disease-certification-qc-flash-acceptance"
            / "fixtures"
            / "valid-mode1.json"
        )
        self.fixture = json.loads(
            self.fixture_path.read_text(encoding="utf-8")
        )
        self.template = self.template_path.read_text(encoding="utf-8")

    def render(self, fixture=None):
        return run_mode1_renderer(
            self.template_path,
            fixture if fixture is not None else self.fixture,
        )

    def test_renderer_builds_logic_group_rule_and_extraction_tree(self):
        state = self.render()
        self.assertEqual(1, state["logicTreeShape"]["groupCount"])
        self.assertEqual(1, state["logicTreeShape"]["childrenCount"])
        self.assertEqual(2, state["logicTreeShape"]["ruleCount"])
        self.assertEqual(2, state["logicTreeShape"]["extractionCount"])
        self.assertEqual(
            [1, 1],
            state["logicTreeShape"]["rulesContainOwnExtractions"],
        )
        self.assertEqual(["details", "details"], state["ruleNodeTags"])
        self.assertEqual(["details", "details"], state["extractionNodeTags"])
        structure = state["logicTreeShape"]["structure"]
        tree = structure["children"][1]
        self.assertIn("logic-tree", tree["className"])
        group = tree["children"][0]
        self.assertIn("logic-group", group["className"])
        children = next(
            child
            for child in group["children"]
            if "logic-children" in child["className"]
        )
        self.assertTrue(
            all("rule-node" in child["className"] for child in children["children"])
        )

    def test_summaries_show_complete_rules_and_each_rules_own_items(self):
        state = self.render()
        self.assertEqual(
            [
                "R001 · 满足条件 A",
                "R002 · 满足条件 B",
            ],
            state["ruleSummaryTexts"],
        )
        self.assertEqual(
            [
                "K001 · 条件 A · 枚举",
                "K002 · 条件 B · 枚举",
            ],
            state["extractionSummaryTexts"],
        )
        self.assertEqual(
            [
                ["K001 · 条件 A · 枚举"],
                ["K002 · 条件 B · 枚举"],
            ],
            state["ruleExtractionSummaryTexts"],
        )
        for marker in (
            "OR · 或",
            "取证与判断指引",
            "测试材料明确记载条件 A 已满足",
            "测试材料明确记载条件 B 未满足",
            "测试材料未提供足以判断条件 A 的信息",
            "测试认定材料",
        ):
            self.assertIn(marker, state["logicText"])

    def test_logic_top_shows_preliminary_conclusion_with_disclaimer(self):
        state = self.render()
        for marker in (
            "本次标准整理初步结论",
            "采用 R001 OR R002",
            "本次分析结果，不是政策原文",
        ):
            self.assertIn(marker, state["logicText"])

    def test_overview_labels_empty_code_and_version_as_result_date(self):
        state = self.render()
        self.assertIn("未提供编码", state["overviewText"])
        self.assertIn("成果生成日期", state["overviewText"])
        self.assertIn("V20260725", state["overviewText"])
        self.assertNotIn("政策发布日期", state["overviewText"])

    def test_unmatched_quote_is_non_blocking_warning_on_own_rule(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["rules"][1]["sourceQuote"] = "来源中不存在的连续原句"
        state = self.render(fixture)
        self.assertFalse(state["shellHidden"])
        self.assertTrue(state["errorHidden"])
        self.assertEqual([0, 1], state["warningCountsPerRule"])
        self.assertIn(
            "原文引用未能在来源材料中精确定位",
            state["logicText"],
        )

    def test_recursive_render_assigns_navigation_targets_once(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["logic"] = {
            "type": "group",
            "operator": "AND",
            "children": [
                {"type": "rule", "ruleId": "R001"},
                {
                    "type": "group",
                    "operator": "OR",
                    "children": [
                        {"type": "rule", "ruleId": "R002"},
                    ],
                },
            ],
        }
        state = self.render(fixture)
        self.assertEqual(2, state["logicTreeShape"]["groupCount"])
        self.assertEqual(1, state["idCounts"]["rules"])
        self.assertEqual(1, state["idCounts"]["extractions"])
        self.assertEqual("-1", state["rulesTabIndex"])
        self.assertEqual("-1", state["extractionsTabIndex"])
        self.assertIn("AND · 且", state["logicText"])
        self.assertIn("OR · 或", state["logicText"])

    def test_template_has_one_hierarchical_view_and_print_accessibility(self):
        for old_class in (
            "rule-grid",
            "rule-card",
            "extraction-grid",
            "extraction-card",
        ):
            self.assertNotIn(old_class, self.template)
        for new_class in (
            "logic-tree",
            "logic-group",
            "logic-children",
            "rule-node",
            "extraction-node",
        ):
            self.assertIn(new_class, self.template)
        self.assertNotIn("<section id=\"rules\"", self.template)
        self.assertNotIn("<section id=\"extractions\"", self.template)
        self.assertIn(":focus-visible", self.template)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.template)
        self.assertIn(
            "details:not([open]) > :not(summary)",
            self.template,
        )
        self.assertNotIn("innerHTML", self.template)
        self.assertNotRegex(
            self.template,
            r"https?://|<script\b[^>]*\bsrc\s*=|"
            r"<link\b[^>]*\bhref\s*=",
        )


if __name__ == "__main__":
    unittest.main()
