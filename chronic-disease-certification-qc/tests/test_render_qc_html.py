import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_qc_html.py"
FIXTURE = ROOT / "tests" / "fixtures" / "valid-qc-report.json"


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_qc_html", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QcRendererTests(unittest.TestCase):
    def setUp(self):
        self.renderer = load_renderer()
        self.report = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_renders_all_core_facts_offline(self):
        rendered = self.renderer.render_qc_html(FIXTURE)
        for value in ("不可靠", "错误拒绝风险", "患者规律接受长期治疗三年", "未执行的检查", "原始输入"):
            self.assertIn(value, rendered)
        self.assertNotIn("http://", rendered)
        self.assertNotIn("https://", rendered)

    def test_unconfirmed_input_blocks_every_formal_output(self):
        report = copy.deepcopy(self.report)
        report["inputScope"]["confirmedByUser"] = False
        for render in (self.renderer.render_qc_text, self.renderer.render_qc_html):
            with self.assertRaisesRegex(ValueError, "confirmedByUser"):
                render(report)

    def test_validation_rejects_missing_wrong_enum_subfields_cycles_and_depth(self):
        missing = copy.deepcopy(self.report); missing.pop("case")
        wrong = copy.deepcopy(self.report); wrong["issues"] = {}
        enum = copy.deepcopy(self.report); enum["issues"][0]["severity"] = "urgent"
        subfield = copy.deepcopy(self.report); subfield["issues"][0]["materialEvidence"][0].pop("rawText")
        for candidate in (missing, wrong, enum, subfield):
            with self.assertRaises(ValueError):
                self.renderer.validate_qc_report(candidate)
        cycle = copy.deepcopy(self.report); cycle["rawInput"]["self"] = cycle["rawInput"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.renderer.validate_qc_report(cycle)
        deep = copy.deepcopy(self.report); node = deep["rawInput"]
        for _ in range(70):
            node["nested"] = {}; node = node["nested"]
        with self.assertRaisesRegex(ValueError, "deep"):
            self.renderer.validate_qc_report(deep)

    def test_evidence_states_are_required_for_issues_and_rule_reviews(self):
        for status in ("SUPPORTED", "CONTRADICTED", "NOT_FOUND", "INSUFFICIENT", "CONFLICTED", "NOT_APPLICABLE"):
            report = copy.deepcopy(self.report)
            report["issues"][0]["evidenceStatus"] = status
            self.renderer.validate_qc_report(report)
        missing = copy.deepcopy(self.report); missing["issues"][0].pop("evidenceStatus")
        invalid = copy.deepcopy(self.report); invalid["issues"][0]["evidenceStatus"] = "MAYBE"
        for report in (missing, invalid):
            with self.assertRaises(ValueError):
                self.renderer.validate_qc_report(report)
        for status in ("SUPPORTED", "CONTRADICTED", "NOT_FOUND", "INSUFFICIENT", "CONFLICTED", "NOT_APPLICABLE"):
            review = {"ruleCode": "R001", "result": "无法判断", "modelClaim": "无主张", "evidenceStatus": status, "materialEvidence": [], "qcFinding": "无材料", "recommendation": "补充材料"}
            report = copy.deepcopy(self.report); report["ruleReviews"] = [review]
            self.renderer.validate_qc_report(report)
        review = {"ruleCode": "R001", "result": "无法判断", "modelClaim": "无主张", "evidenceStatus": "NOT_FOUND", "materialEvidence": [], "qcFinding": "无材料", "recommendation": "补充材料"}
        report = copy.deepcopy(self.report); report["ruleReviews"] = [review]
        self.assertIn("NOT_FOUND", self.renderer.render_qc_text(report))
        self.assertIn("NOT_FOUND", self.renderer.render_qc_html(report))
        report["ruleReviews"][0]["evidenceStatus"] = "MAYBE"
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_capability_reason_is_empty_only_when_completed(self):
        report = copy.deepcopy(self.report)
        self.renderer.validate_qc_report(report)
        for status in ("partial", "not_run"):
            report = copy.deepcopy(self.report); report["capabilities"][0]["status"] = status
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_approved_issue_codes_and_plan_evidence_shape_are_enforced(self):
        for impact in ("changed", "potentially_changed", "unchanged", "unknown"):
            report = copy.deepcopy(self.report); report["issues"][0]["impactOnFinalResult"] = impact
            self.renderer.validate_qc_report(report)
        for risk in ("false_approval", "false_rejection", "both", "none"):
            report = copy.deepcopy(self.report); report["issues"][0]["riskDirection"] = risk
            self.renderer.validate_qc_report(report)
        for field, invalid in (("impactOnFinalResult", "not_changed"), ("riskDirection", "local_error")):
            report = copy.deepcopy(self.report); report["issues"][0][field] = invalid
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        for field, value in (("page", 0), ("page", "1"), ("location", {"start": -1, "end": 1}), ("location", {"start": 2, "end": 1})):
            report = copy.deepcopy(self.report); report["issues"][0]["materialEvidence"][0][field] = value
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_non_json_containers_duplicate_keys_and_deep_json_are_controlled(self):
        report = copy.deepcopy(self.report); report["rawInput"] = ("not", "json")
        with self.assertRaisesRegex(ValueError, "unsupported non-JSON"):
            self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["issues"] = (report["issues"][0],)
        with self.assertRaisesRegex(ValueError, "unsupported non-JSON"):
            self.renderer.validate_qc_report(report)
        duplicates = ('{"case":{},"case":{}}', '{"rawInput":{"value":1,"value":2}}', '{"inputScope":{"confirmedByUser":true,"confirmedByUser":false}}')
        for duplicate in duplicates:
            with self.assertRaisesRegex(ValueError, "duplicate"):
                self.renderer.validate_qc_report(duplicate)
        deep_json = '{"rawInput":' * 10000 + 'null' + '}' * 10000
        with self.assertRaisesRegex(ValueError, "deep|recursion"):
            self.renderer.validate_qc_report(deep_json)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "deep.json"; source.write_text(deep_json, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "deep|recursion"):
                self.renderer.validate_qc_report(source)
            completed = subprocess.run([sys.executable, str(SCRIPT), str(source), str(Path(directory) / "out.html")], text=True, capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertNotIn("Traceback", completed.stderr)
            for index, duplicate in enumerate(duplicates):
                source = Path(directory) / f"duplicate-{index}.json"; source.write_text(duplicate, encoding="utf-8")
                completed = subprocess.run([sys.executable, str(SCRIPT), str(source), str(Path(directory) / f"duplicate-{index}.html")], text=True, capture_output=True)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("duplicate", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)

    def test_text_and_html_are_parity_views_of_the_same_canonical_object(self):
        text = self.renderer.render_qc_text(self.report)
        rendered = self.renderer.render_qc_html(self.report)
        for value in ("不可靠", "错误拒绝风险", "误报缺失", "患者规律接受长期治疗三年", "未提供结构化标准", "重新执行智能审核", "原始输入"):
            self.assertIn(value, text)
            self.assertIn(value, rendered)
        self.assertEqual(text.count("误报缺失"), rendered.count("误报缺失"))

    def test_text_has_ordered_sections_and_empty_states(self):
        report = copy.deepcopy(self.report)
        report["issues"] = []; report["ruleReviews"] = []; report["unperformedChecks"] = []
        text = self.renderer.render_qc_text(report)
        headings = ["质控结论", "输入与检查范围", "影响最终结论的问题", "材料缺失复核", "证据准确性", "过度推理", "条件一致性", "规则维护质量", "逐规则复核", "建议", "未执行检查", "原始输入"]
        positions = [text.index("# " + heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertGreaterEqual(text.count("无相关问题"), 5)
        self.assertIn("无逐规则复核", text)
        self.assertIn("无未执行检查", text)

    def test_raw_input_and_empty_material_scope_have_parity_empty_state(self):
        report = copy.deepcopy(self.report); report["inputScope"]["materials"] = []
        text = self.renderer.render_qc_text(report); rendered = self.renderer.render_qc_html(report)
        for value in ("原始输入", "出院记录：患者规律接受长期治疗三年", "无"):
            self.assertIn(value, text)
            self.assertIn(value, rendered)

    def test_escapes_xss_attributes_raw_json_markers_controls_and_surrogates(self):
        report = copy.deepcopy(self.report)
        attack = '<img src=x onerror="alert(1)">{{BODY}}\x00\ud800'
        report["case"]["patientName"] = attack
        report["issues"][0]["modelClaim"] = attack
        report["rawInput"]["attack"] = attack
        rendered = self.renderer.render_qc_html(report)
        self.assertIn("&lt;img src=x", rendered)
        self.assertNotIn("<img src=x", rendered)
        self.assertNotIn("\x00", rendered)
        self.assertNotIn("\ud800", rendered)
        self.assertEqual(rendered.count("<main id=\"qc-report-main\">") , 1)
        self.assertIsInstance(rendered.encode("utf-8"), bytes)

    def test_deterministic_no_mutation_and_adapters(self):
        original = copy.deepcopy(self.report)
        payload = json.dumps(self.report, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"; path.write_text(payload, encoding="utf-8")
            rendered = [self.renderer.render_qc_html(value) for value in (self.report, payload, path)]
        self.assertEqual(rendered, [rendered[0]] * 3)
        self.assertEqual(self.report, original)

    def test_template_has_accessibility_responsive_print_dark_offline_and_no_truncation(self):
        rendered = self.renderer.render_qc_html(self.report)
        for value in ("<!doctype html>", '<html lang="zh-CN">', 'name="viewport"', "<header", "<main", ":focus-visible", "@media (max-width:", "@media print", "@media (prefers-color-scheme: dark)", "@media (prefers-reduced-motion: reduce)"):
            self.assertIn(value, rendered)
        self.assertEqual(rendered.count("<h1"), 1)
        self.assertNotIn("text-overflow:ellipsis", rendered.replace(" ", ""))
        self.assertNotIn("line-clamp", rendered)

    def test_cli_handles_bom_newline_and_controlled_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"; output = Path(directory) / "report.html"
            source.write_text("\ufeff" + json.dumps(self.report, ensure_ascii=False), encoding="utf-8")
            success = subprocess.run([sys.executable, str(SCRIPT), str(source), str(output)], text=True, capture_output=True)
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertTrue(output.read_text(encoding="utf-8").endswith("\n"))
            self.assertFalse(output.read_text(encoding="utf-8").endswith("\n\n"))
            failed = subprocess.run([sys.executable, str(SCRIPT), str(source), str(Path(directory) / "no" / "out.html")], text=True, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("output_error:", failed.stderr)
            self.assertNotIn("Traceback", failed.stderr)


if __name__ == "__main__":
    unittest.main()
