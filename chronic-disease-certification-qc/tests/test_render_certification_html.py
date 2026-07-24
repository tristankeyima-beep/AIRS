import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_literal_template_markers_in_title_and_business_values_render_as_text(self):
        standard = copy.deepcopy(self.standard)
        standard["meta"]["chronicDiseaseName"] = "病种 {{BODY}} {{TITLE}}"
        standard["meta"]["description"] = "说明 {{TITLE}} {{BODY}}"
        standard["ruleRepository"][0].update({
            "ruleContent": "条件 {{TITLE}}", "ruleSource": "依据 {{BODY}}",
            "experience": "经验 {{TITLE}}", "sourceRuleContent": "原文 {{BODY}}",
            "sourceMdFile": "来源 {{TITLE}}", "sourceSection": "章节 {{BODY}}",
        })
        standard["ruleRepository"][0]["ruleKeywordGuide"][0].update({
            "keywordContent": "指引 {{TITLE}} {{BODY}}", "enumOptions": ["选项 {{BODY}}", "选项 {{TITLE}}"],
        })

        html = self.renderer.render_certification_html(standard)

        for expected in ("病种 {{BODY}} {{TITLE}}", "说明 {{TITLE}} {{BODY}}", "条件 {{TITLE}}", "依据 {{BODY}}",
                         "经验 {{TITLE}}", "原文 {{BODY}}", "来源 {{TITLE}}", "章节 {{BODY}}", "指引 {{TITLE}} {{BODY}}",
                         "选项 {{BODY}}", "选项 {{TITLE}}"):
            self.assertIn(expected, html)
        self.assertEqual(html.count("<main id=\"document-main\">") , 1)

    def test_rejects_malformed_template_before_business_values_are_concatenated(self):
        original_template = self.renderer.TEMPLATE
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "malformed.html"
            malformed.write_text("<html>{{TITLE}}{{TITLE}}{{BODY}}</html>", encoding="utf-8")
            self.renderer.TEMPLATE = malformed
            try:
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    self.renderer.render_certification_html(self.standard)
            finally:
                self.renderer.TEMPLATE = original_template

    def test_lone_surrogates_are_normalized_to_utf8_safe_replacement_characters(self):
        standard = copy.deepcopy(self.standard)
        standard["meta"]["chronicDiseaseName"] = "病种\ud800"
        standard["ruleRepository"][0]["ruleContent"] = "条件\udcff"
        standard["ruleRepository"][0]["ruleKeywordGuide"][0]["enumOptions"] = ["选项\ud800"]

        html = self.renderer.render_certification_html(standard)

        self.assertIn("\ufffd", html)
        self.assertNotIn("\ud800", html)
        self.assertNotIn("\udcff", html)
        self.assertIsInstance(html.encode("utf-8"), bytes)

    def test_rules_are_collapsed_by_default_but_print_css_reveals_details(self):
        html = self.renderer.render_certification_html(self.standard)

        self.assertIn('<article class="rule-card" data-rule-code="01001"><details>', html)
        self.assertNotIn("<details open>", html)
        self.assertIn("@media print", html)
        self.assertIn("details > *:not(summary) { display: block; }", html)

    def test_guide_disclosure_is_contextual_escaped_and_accessibly_named(self):
        standard = copy.deepcopy(self.standard)
        breakout = "</pre><script>alert(1)</script>{{BODY}}"
        standard["ruleRepository"][0]["ruleKeywordGuide"][0].update({
            "keywordContent": breakout, "enumOptions": [breakout],
        })

        html = self.renderer.render_certification_html(standard)

        self.assertIn('<caption>规则 01001 的取证与判断指引</caption>', html)
        for heading in ("关键词编码", "取证/判断指引", "数据类型", "是否必填", "枚举选项", "完整数据结构"):
            self.assertIn(f'<th scope="col">{heading}</th>', html)
        self.assertIn('<details class="guide-data"><summary>展开完整数据</summary><pre>', html)
        self.assertIn('&lt;/pre&gt;&lt;script&gt;alert(1)&lt;/script&gt;{{BODY}}', html)
        self.assertNotIn("</pre><script>alert(1)</script>", html)

    def test_forbidden_controls_are_replaced_but_tab_linefeed_and_carriage_return_are_preserved(self):
        standard = copy.deepcopy(self.standard)
        forbidden = "\x00\x01\x08\x0b\x0c\x0e\x1f\x7f"
        allowed = "保留\t制表\n换行\r回车"
        standard["meta"]["description"] = f"说明{forbidden}{allowed}"
        standard["ruleRepository"][0]["ruleContent"] = f"条件{forbidden}"
        standard["ruleRepository"][0]["ruleKeywordGuide"][0]["enumOptions"] = [f"选项{forbidden}"]

        html = self.renderer.render_certification_html(standard)

        for character in forbidden:
            self.assertNotIn(character, html)
        self.assertIn(allowed, html)
        self.assertIsInstance(html.encode("utf-8"), bytes)

    def test_template_and_document_meet_accessibility_responsive_print_and_dark_mode_contract(self):
        html = self.renderer.render_certification_html(self.standard)
        template = TEMPLATE.read_text(encoding="utf-8")

        for expected in ('<!doctype html>', '<html lang="zh-CN">', '<meta charset="utf-8">',
                         'name="viewport"', '<header', '<main', '<section', '<article', '<details', '<summary',
                         ':focus-visible', '@media (max-width:', '@media print', '@media (prefers-color-scheme: dark)',
                         '@media (prefers-reduced-motion: reduce)', ':root'):
            self.assertIn(expected, html if expected not in (':root',) else template)
        self.assertEqual(html.count("<h1"), 1)
        self.assertIn("<h3>取证与判断指引</h3>", html)
        self.assertNotIn("<h4", html)
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

    def test_cli_normalizes_escaped_lone_surrogates_without_traceback(self):
        standard = copy.deepcopy(self.standard)
        standard["meta"]["description"] = "输入含孤立代理项\ud800"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "surrogate.json"
            output = Path(directory) / "surrogate.html"
            source.write_text(json.dumps(standard, ensure_ascii=True), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), str(output)],
                text=True, capture_output=True, check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)
            self.assertIn("\ufffd", output.read_text(encoding="utf-8"))

    def test_cli_normalizes_forbidden_controls_without_traceback(self):
        standard = copy.deepcopy(self.standard)
        forbidden = "\x00\x01\x08\x0b\x0c\x0e\x1f\x7f"
        standard["meta"]["description"] = f"CLI{forbidden}控制字符"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "controls.json"
            output = Path(directory) / "controls.html"
            source.write_text(json.dumps(standard, ensure_ascii=True), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), str(output)],
                text=True, capture_output=True, check=False,
            )
            rendered = output.read_text(encoding="utf-8") if output.exists() else ""

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)
            self.assertTrue(rendered.encode("utf-8"))
            for character in forbidden:
                self.assertNotIn(character, rendered)

    def test_cli_rejects_input_output_aliases_and_existing_output_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            source = directory_path / "standard.json"
            source.write_bytes(FIXTURE.read_bytes())
            original = source.read_bytes()
            hardlink = directory_path / "hardlink.html"
            try:
                hardlink.hardlink_to(source)
            except OSError as exc:
                self.skipTest(f"hard links unsupported: {exc}")
            symlink = directory_path / "symlink.html"
            try:
                symlink.symlink_to(source)
            except OSError as exc:
                import errno
                if exc.errno in (errno.EPERM, errno.EACCES, errno.ENOSYS, errno.EOPNOTSUPP):
                    self.skipTest(f"symlinks unsupported: {exc}")
                raise
            for output in (source, "standard.json", hardlink, symlink):
                with self.subTest(output=output):
                    completed = subprocess.run(
                        [sys.executable, str(SCRIPT), str(source), str(output)],
                        text=True, capture_output=True, check=False,
                        cwd=directory_path,
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertNotIn("Traceback", completed.stderr)
                    self.assertEqual(source.read_bytes(), original)

    def test_renderer_atomic_output_failure_preserves_destination_and_cleans_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            output = directory_path / "rendered.html"
            output.write_bytes(b"old html")
            output.chmod(0o640)
            with patch.object(self.renderer.validator.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    self.renderer.validator.atomic_write_text(output, "new html\n")
            self.assertEqual(output.read_bytes(), b"old html")
            self.assertEqual(output.stat().st_mode & 0o777, 0o640)
            self.assertEqual(list(directory_path.glob(".rendered.html.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
