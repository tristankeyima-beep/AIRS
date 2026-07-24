import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_certification_html.py"
TEMPLATE = ROOT / "assets" / "certification-template.html"
FIXTURE = ROOT / "tests" / "fixtures" / "valid-certification.json"


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_certification_html", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CertificationHtmlTests(unittest.TestCase):
    def setUp(self):
        self.renderer = load_renderer()
        self.standard = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_canonical_fixture_renders_full_rule_and_offline_document(self):
        html = self.renderer.render_certification_html(FIXTURE)

        for expected in ("测试病种", "01001001", "需明确诊断为测试病种", "AND · 全部条件满足"):
            self.assertIn(expected, html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("text-overflow:ellipsis", html.replace(" ", ""))
        self.assertNotIn("line-clamp", html)

    def test_escapes_special_characters_and_cannot_inject_tags(self):
        standard = copy.deepcopy(self.standard)
        standard["meta"]["chronicDiseaseName"] = '<img src=x onerror="alert(1)"> & 病种'
        standard["ruleRepository"][0]["ruleContent"] = "<script>alert('xss')</script>"
        standard["ruleRepository"][0]["sourceRuleContent"] = "<b>不得解释为标签</b>"
        html = self.renderer.render_certification_html(standard)

        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; 病种", html)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<b>不得", html)

    def test_renders_nested_logic_in_order_and_each_rule_and_guide_once(self):
        standard = copy.deepcopy(self.standard)
        second = copy.deepcopy(standard["ruleRepository"][0])
        second.update({
            "ruleCode": "01002",
            "ruleContent": "第二条完整条件",
            "sourceRuleContent": "第二条来源原文",
        })
        second["ruleKeywordGuide"][0].update({"keywordCode": "01002001", "keywordContent": "第二条指引"})
        third = copy.deepcopy(second)
        third.update({
            "ruleCode": "01003",
            "ruleContent": "第三条完整条件",
            "sourceRuleContent": "第三条来源原文",
        })
        third["ruleKeywordGuide"][0].update({"keywordCode": "01003001", "keywordContent": "第三条指引"})
        standard["ruleRepository"].extend([second, third])
        standard["logicTopology"] = {
            "type": "GROUP", "operator": "AND", "children": [
                {"type": "RULE_REF", "ruleCode": "01001"},
                {"type": "GROUP", "operator": "OR", "children": [
                    {"type": "RULE_REF", "ruleCode": "01002"},
                    {"type": "RULE_REF", "ruleCode": "01003"},
                ]},
            ],
        }
        html = self.renderer.render_certification_html(standard)

        self.assertIn("AND · 全部条件满足", html)
        self.assertIn("OR · 任一条件满足", html)
        self.assertLess(html.index("01001"), html.index("01002"))
        self.assertLess(html.index("01002"), html.index("01003"))
        for value in ("01001", "01002", "01003", "01001001", "01002001", "01003001"):
            self.assertEqual(html.count(f">{value}<"), 1)

    def test_renders_all_meta_source_and_experience_fields_without_truncation(self):
        standard = copy.deepcopy(self.standard)
        standard["meta"].update({
            "version": "V20991231 完整版本", "createdAt": "2099-12-31T23:59:59+08:00",
            "description": "完整标准说明", "sourceFile": "完整来源文件.md",
        })
        standard["ruleRepository"][0].update({
            "ruleSource": "完整政策依据", "experience": "完整业务经验", "sourceMdFile": "完整来源.md", "sourceSection": "第三章第二节",
        })
        html = self.renderer.render_certification_html(standard)

        for expected in ("V20991231 完整版本", "2099-12-31T23:59:59+08:00", "完整标准说明", "完整来源文件.md",
                         "完整政策依据", "完整业务经验", "完整来源.md", "第三章第二节"):
            self.assertIn(expected, html)

    def test_invalid_input_raises_controlled_value_error_with_issue_json(self):
        invalid = copy.deepcopy(self.standard)
        invalid["logicTopology"]["children"] = []

        with self.assertRaisesRegex(ValueError, '"code": "children_required"'):
            self.renderer.render_certification_html(invalid)

    def test_supported_adapters_are_equivalent_deterministic_and_do_not_mutate_input(self):
        original = copy.deepcopy(self.standard)
        payload = json.dumps(self.standard, ensure_ascii=False)
        wrapped = {"output": {"result": payload}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "standard.json"
            path.write_text(payload, encoding="utf-8")
            rendered = [self.renderer.render_certification_html(value) for value in (self.standard, path, payload, wrapped)]

        self.assertEqual(rendered, [rendered[0]] * 4)
        self.assertEqual(self.standard, original)
        self.assertEqual(wrapped, {"output": {"result": payload}})

    def test_template_and_document_meet_accessibility_responsive_print_and_dark_mode_contract(self):
        html = self.renderer.render_certification_html(self.standard)
        template = TEMPLATE.read_text(encoding="utf-8")

        for expected in ('<!doctype html>', '<html lang="zh-CN">', '<meta charset="utf-8">',
                         'name="viewport"', '<header', '<main', '<section', '<article', '<details', '<summary',
                         ':focus-visible', '@media (max-width:', '@media print', '@media (prefers-color-scheme: dark)',
                         '@media (prefers-reduced-motion: reduce)', ':root'):
            self.assertIn(expected, html if expected not in (':root',) else template)
        self.assertEqual(html.count("<h1"), 1)
        self.assertNotIn("{{TITLE}}", html)
        self.assertNotIn("{{BODY}}", html)

    def test_cli_writes_one_trailing_newline_and_fails_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "rendered.html"
            success = subprocess.run(
                [sys.executable, str(SCRIPT), str(FIXTURE), str(output)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertTrue(output.exists())
            rendered = output.read_text(encoding="utf-8")
            self.assertTrue(rendered.endswith("\n"))
            self.assertFalse(rendered.endswith("\n\n"))

            missing_parent = Path(directory) / "missing" / "output.html"
            failed = subprocess.run(
                [sys.executable, str(SCRIPT), str(FIXTURE), str(missing_parent)],
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("output_error:", failed.stderr)
            self.assertNotIn("Traceback", failed.stderr)

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{not json", encoding="utf-8")
            failed_input = subprocess.run(
                [sys.executable, str(SCRIPT), str(invalid), str(output)],
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(failed_input.returncode, 0)
            self.assertIn("render_error:", failed_input.stderr)
            self.assertNotIn("Traceback", failed_input.stderr)


if __name__ == "__main__":
    unittest.main()
