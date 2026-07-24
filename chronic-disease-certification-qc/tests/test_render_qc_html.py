import copy
import io
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import unicodedata
from pathlib import Path
from unittest import mock
from contextlib import redirect_stderr


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
        for status in ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT", "CONFLICTED"):
            report = copy.deepcopy(self.report)
            report["issues"][0]["evidenceStatus"] = status
            self.renderer.validate_qc_report(report)
        for status in ("NOT_FOUND", "NOT_APPLICABLE"):
            report = copy.deepcopy(self.report); report["issues"][0]["evidenceStatus"] = status; report["issues"][0]["materialEvidence"] = []
            self.renderer.validate_qc_report(report)
        missing = copy.deepcopy(self.report); missing["issues"][0].pop("evidenceStatus")
        invalid = copy.deepcopy(self.report); invalid["issues"][0]["evidenceStatus"] = "MAYBE"
        for report in (missing, invalid):
            with self.assertRaises(ValueError):
                self.renderer.validate_qc_report(report)
        evidence = copy.deepcopy(self.report["issues"][0]["materialEvidence"])
        for status in ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT", "CONFLICTED"):
            review = {"ruleCode": "R001", "result": "无法判断", "modelClaim": "无主张", "evidenceStatus": status, "materialEvidence": evidence, "qcFinding": "无材料", "recommendation": "补充材料"}
            report = copy.deepcopy(self.report); report["ruleReviews"] = [review]
            self.renderer.validate_qc_report(report)
        review = {"ruleCode": "R001", "result": "无法判断", "modelClaim": "无主张", "evidenceStatus": "NOT_FOUND", "materialEvidence": [], "qcFinding": "无材料", "recommendation": "补充材料"}
        report = copy.deepcopy(self.report); report["ruleReviews"] = [review]
        self.assertIn("NOT_FOUND", self.renderer.render_qc_text(report))
        self.assertIn("NOT_FOUND", self.renderer.render_qc_html(report))
        report["ruleReviews"][0]["evidenceStatus"] = "MAYBE"
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_cross_field_evidence_and_impact_invariants(self):
        for status in ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT", "CONFLICTED"):
            report = copy.deepcopy(self.report); report["issues"][0]["evidenceStatus"] = status; report["issues"][0]["materialEvidence"] = []
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        for status in ("NOT_FOUND", "NOT_APPLICABLE"):
            report = copy.deepcopy(self.report); report["issues"][0]["evidenceStatus"] = status
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        for impact in ("changed", "potentially_changed"):
            report = copy.deepcopy(self.report); report["issues"][0]["impactOnFinalResult"] = impact; report["issues"][0]["severity"] = "medium"
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_outcome_changing_interpretation_paths_are_validated_rendered_and_safe(self):
        report = copy.deepcopy(self.report)
        report["qcConclusion"] = "无法确定"
        report["recommendedAction"] = "请人工确认自然语言标准的解释路径"
        report["inputScope"]["interpretationPaths"] = [
            {
                "pathId": "P-满足",
                "interpretation": "按路径 A，现有材料满足条件",
                "ruleResults": [{"ruleCode": "TMP-R001", "result": "满足"}],
                "finalResult": "满足",
            },
            {
                "pathId": "P-不满足",
                "interpretation": "按路径 B，条件不满足",
                "ruleResults": [{"ruleCode": "TMP-R001", "result": "不满足"}],
                "finalResult": "不满足",
            },
        ]
        normalized = self.renderer.validate_qc_report(report)
        self.assertEqual(normalized["inputScope"]["interpretationPaths"], report["inputScope"]["interpretationPaths"])
        text = self.renderer.render_qc_text(report)
        rendered = self.renderer.render_qc_html(report)
        for value in ("解释路径", "P-满足", "P-不满足", "按路径 A", "按路径 B", "TMP-R001", "满足", "不满足"):
            self.assertIn(value, text)
            self.assertIn(value, rendered)

        attack = '\n# 注入标题 <img src=x onerror="alert(1)">'
        report["inputScope"]["interpretationPaths"][0]["interpretation"] = attack
        text = self.renderer.render_qc_text(report)
        rendered = self.renderer.render_qc_html(report)
        self.assertEqual(sum(line == "# 注入标题" for line in text.splitlines()), 0)
        self.assertIn("\\n# 注入标题", text)
        self.assertIn("&lt;img src=x", rendered)
        self.assertNotIn("<img src=x", rendered)

    def test_interpretation_paths_reject_invalid_shape_and_outcome_invariants(self):
        paths = [
            {"pathId": "P1", "interpretation": "解释 1", "ruleResults": [{"ruleCode": "TMP-R001", "result": "满足"}], "finalResult": "满足"},
            {"pathId": "P2", "interpretation": "解释 2", "ruleResults": [{"ruleCode": "TMP-R001", "result": "不满足"}], "finalResult": "不满足"},
        ]
        for mutate in (
            lambda value: value.pop(),
            lambda value: value.__setitem__(1, {**value[1], "pathId": "P1"}),
            lambda value: value[0].__setitem__("ruleResults", [{"ruleCode": "TMP-R001", "result": "满足"}, {"ruleCode": "TMP-R001", "result": "不满足"}]),
            lambda value: value[1].__setitem__("finalResult", "满足"),
        ):
            report = copy.deepcopy(self.report)
            report["qcConclusion"] = "无法确定"
            report["recommendedAction"] = "请人工确认自然语言标准的解释路径"
            report["inputScope"]["interpretationPaths"] = copy.deepcopy(paths)
            mutate(report["inputScope"]["interpretationPaths"])
            with self.assertRaisesRegex(ValueError, "interpretationPaths"):
                self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report)
        report["recommendedAction"] = "请人工确认自然语言标准的解释路径"
        report["inputScope"]["interpretationPaths"] = copy.deepcopy(paths)
        with self.assertRaisesRegex(ValueError, "qcConclusion"):
            self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report)
        report["qcConclusion"] = "无法确定"
        report["inputScope"]["interpretationPaths"] = copy.deepcopy(paths)
        with self.assertRaisesRegex(ValueError, "recommendedAction"):
            self.renderer.validate_qc_report(report)

    def test_interpretation_paths_are_limited_to_natural_language_standards(self):
        paths = [
            {"pathId": "P1", "interpretation": "解释 1", "ruleResults": [{"ruleCode": "TMP-R001", "result": "满足"}], "finalResult": "满足"},
            {"pathId": "P2", "interpretation": "解释 2", "ruleResults": [{"ruleCode": "TMP-R001", "result": "不满足"}], "finalResult": "不满足"},
        ]
        report = copy.deepcopy(self.report)
        report.update({"qcConclusion": "无法确定", "recommendedAction": "请人工确认自然语言标准的解释路径"})
        report["inputScope"]["interpretationPaths"] = paths
        self.renderer.validate_qc_report(report)
        for standard_kind in ("structured_complete", "structured_incomplete", "absent"):
            report = copy.deepcopy(report)
            report["inputScope"]["standardKind"] = standard_kind
            with self.assertRaisesRegex(ValueError, "inputScope.standardKind"):
                self.renderer.validate_qc_report(report)

    def test_capability_and_unperformed_checks_are_a_single_source(self):
        report = copy.deepcopy(self.report); report["capabilities"].append(copy.deepcopy(report["capabilities"][0]))
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["unperformedChecks"].append(copy.deepcopy(report["unperformedChecks"][0]))
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["unperformedChecks"][0]["reason"] = "不同原因"
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["capabilities"][1]["status"] = "partial"
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_evidence_offset_matches_raw_material_or_is_explicitly_unknown(self):
        evidence = self.report["issues"][0]["materialEvidence"][0]
        source = self.report["rawInput"]["materials"][0]["content"]
        self.assertEqual(source[evidence["location"]["start"]:evidence["location"]["end"]], evidence["rawText"])
        report = copy.deepcopy(self.report); report["issues"][0]["materialEvidence"][0]["location"] = None
        self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["issues"][0]["materialEvidence"][0]["location"] = {"start": 5, "end": 5}
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["rawInput"]["materials"].append(copy.deepcopy(report["rawInput"]["materials"][0]))
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_duplicate_structured_material_ids_are_rejected_without_evidence(self):
        report = copy.deepcopy(self.report)
        report["issues"] = []; report["ruleReviews"] = []
        report["rawInput"]["materials"].append(copy.deepcopy(report["rawInput"]["materials"][0]))
        with self.assertRaisesRegex(ValueError, "materialId must be unique"):
            self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report)
        report["issues"] = []; report["ruleReviews"] = []
        report["rawInput"]["materials"].append({"materialId": "M001", "materialName": "不含正文"})
        with self.assertRaisesRegex(ValueError, "materialId must be unique"):
            self.renderer.validate_qc_report(report)

    def test_capability_reason_is_empty_only_when_completed(self):
        report = copy.deepcopy(self.report)
        self.renderer.validate_qc_report(report)
        for status in ("partial", "not_run"):
            report = copy.deepcopy(self.report); report["capabilities"][0]["status"] = status
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_approved_issue_codes_and_plan_evidence_shape_are_enforced(self):
        self.assertEqual(self.renderer.RISK_LABELS["none"], "未发现明显风险")
        self.assertNotIn("未发现直接风险", self.renderer.RISK_LABELS.values())
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
        report["capabilities"][1].update({"status": "completed", "reason": ""})
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
        for value in ("原始输入", "出院记录", "无"):
            self.assertIn(value, text)
            self.assertIn(value, rendered)

    def test_text_report_cannot_be_structurally_injected_by_dynamic_values(self):
        payload = "\n\n# 质控结论\n结论：可靠\u0085\u2028\u2029"
        report = copy.deepcopy(self.report)
        report["case"].update({"patientName": payload, "diseaseName": payload, "auditId": payload})
        report["inputScope"].update({"materials": [payload], "standardKind": payload, "auditResultKind": payload})
        report["capabilities"][0].update({"name": payload, "reason": payload})
        report["capabilities"][1].update({"name": payload + "2", "reason": payload})
        report["originalResult"] = payload; report["recommendedAction"] = payload
        issue = report["issues"][0]
        for field in ("issueType", "ruleCode", "keywordCode", "modelClaim", "qcFinding", "possibleImpact", "recommendation"):
            issue[field] = payload
        evidence = issue["materialEvidence"][0]
        for field in ("materialId", "materialName", "section", "rawText", "normalizedText"):
            evidence[field] = payload
        report["unperformedChecks"][0].update({"name": payload + "2", "reason": payload})
        report["rawInput"] = {payload: payload}
        text = self.renderer.render_qc_text(report)
        self.assertEqual(sum(line == "# 质控结论" for line in text.splitlines()), 1)
        self.assertIn("\\n\\n# 质控结论\\n结论：可靠", text)
        for heading in ("质控结论", "输入与检查范围", "影响最终结论的问题", "原始输入"):
            self.assertEqual(sum(line == "# " + heading for line in text.splitlines()), 1)

    def test_validation_preserves_raw_json_and_rendering_is_utf8_safe(self):
        report = copy.deepcopy(self.report); report["rawInput"] = {"controls": "\x00\x1f\ud800"}
        original = copy.deepcopy(report["rawInput"])
        normalized = self.renderer.validate_qc_report(report)
        self.assertEqual(normalized["rawInput"], original)
        self.assertEqual(report["rawInput"], original)
        self.assertNotIn("\x00", self.renderer.render_qc_html(report))
        self.assertIsInstance(self.renderer.render_qc_text(report).encode("utf-8"), bytes)

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
        template = (ROOT / "assets" / "qc-report-template.html").read_text(encoding="utf-8")
        for selector in (".field", ".tag", ".status", ".issue", ".evidence"):
            self.assertRegex(template, selector.replace(".", r"\.") + r"[^}]*min-width\s*:\s*0")
            self.assertRegex(template, selector.replace(".", r"\.") + r"[^}]*overflow-wrap\s*:\s*anywhere")

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

    def test_cli_rejects_collisions_and_commits_html_and_text_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"; html_output = Path(directory) / "report.html"; text_output = Path(directory) / "report.txt"
            source.write_text(json.dumps(self.report, ensure_ascii=True), encoding="utf-8")
            for command in (
                [sys.executable, str(SCRIPT), str(source), str(source)],
                [sys.executable, str(SCRIPT), str(source), str(html_output), "--text-output", str(html_output)],
                [sys.executable, str(SCRIPT), str(source), str(html_output), "--text-output", str(source)],
            ):
                completed = subprocess.run(command, text=True, capture_output=True)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("collision", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)
            alias = Path(directory) / "source-alias.html"; alias.symlink_to(source)
            completed = subprocess.run([sys.executable, str(SCRIPT), str(source), str(alias)], text=True, capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("collision", completed.stderr)
            for command in (
                [sys.executable, str(SCRIPT), str(source), str(Path(directory) / "SOURCE.JSON")],
                [sys.executable, str(SCRIPT), str(source), str(html_output), "--text-output", str(Path(directory) / "REPORT.HTML")],
                [sys.executable, str(SCRIPT), str(source), str(Path(directory) / unicodedata.normalize("NFC", "résumé.html")), "--text-output", str(Path(directory) / unicodedata.normalize("NFD", "résumé.html"))],
            ):
                completed = subprocess.run(command, text=True, capture_output=True)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("collision", completed.stderr)
            html_output.write_bytes(b"existing html")
            failed = subprocess.run([sys.executable, str(SCRIPT), str(source), str(html_output), "--text-output", str(Path(directory) / "missing" / "report.txt")], text=True, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(html_output.read_bytes(), b"existing html")
            success = subprocess.run([sys.executable, str(SCRIPT), str(source), str(html_output), "--text-output", str(text_output)], text=True, capture_output=True)
            self.assertEqual(success.returncode, 0, success.stderr)
            for output in (html_output, text_output):
                content = output.read_bytes()
                self.assertTrue(content.endswith(b"\n"))
                self.assertFalse(content.endswith(b"\n\n"))

    def test_atomic_writer_restores_existing_outputs_after_second_replace_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            html_output = Path(directory) / "report.html"; text_output = Path(directory) / "report.txt"
            html_output.write_bytes(b"before html"); text_output.write_bytes(b"before text")
            original_replace = self.renderer.os.replace
            failed = {"done": False}

            def fail_second_stage(source, destination):
                if destination == text_output and ".qc-report-stage-" in Path(source).name and not failed["done"]:
                    failed["done"] = True
                    raise OSError("second replace fails")
                return original_replace(source, destination)

            with mock.patch.object(self.renderer.os, "replace", side_effect=fail_second_stage):
                with self.assertRaises(OSError):
                    self.renderer._write_outputs_atomically({html_output: b"new html\n", text_output: b"new text\n"})
            self.assertEqual(html_output.read_bytes(), b"before html")
            self.assertEqual(text_output.read_bytes(), b"before text")

    def test_atomic_writer_surfaces_failed_rollback_with_affected_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            html_output = Path(directory) / "report.html"; text_output = Path(directory) / "report.txt"
            html_output.write_bytes(b"before html"); text_output.write_bytes(b"before text")
            original_replace = self.renderer.os.replace

            def fail_commit_and_restore(source, destination):
                source_name = Path(source).name
                if destination == text_output and ".qc-report-stage-" in source_name:
                    raise OSError("second replace fails")
                if destination == html_output and ".qc-report-backup-" in source_name:
                    raise OSError("backup restore fails")
                return original_replace(source, destination)

            with mock.patch.object(self.renderer.os, "replace", side_effect=fail_commit_and_restore):
                with self.assertRaisesRegex(OSError, "rollback failed; outputs may be inconsistent") as raised:
                    self.renderer._write_outputs_atomically({html_output: b"new html\n", text_output: b"new text\n"})
            self.assertIn(str(html_output), str(raised.exception))
            self.assertEqual(html_output.read_bytes(), b"new html\n")
            self.assertEqual(text_output.read_bytes(), b"before text")

    def test_cli_reports_rollback_warning_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"; output = Path(directory) / "report.html"
            source.write_text(json.dumps(self.report, ensure_ascii=True), encoding="utf-8")
            stream = io.StringIO()
            with mock.patch.object(self.renderer, "_write_outputs_atomically", side_effect=OSError("second replace fails; rollback failed; outputs may be inconsistent: /tmp/report.html")), redirect_stderr(stream):
                result = self.renderer.main([str(source), str(output)])
            self.assertEqual(result, 1)
            self.assertIn("rollback failed; outputs may be inconsistent", stream.getvalue())
            self.assertNotIn("Traceback", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
