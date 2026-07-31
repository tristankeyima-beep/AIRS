import contextlib
import importlib.util
import io
import json
import pathlib
import re
import tempfile
import unittest


SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "render_audit_result.py"
TEMPLATE_PATH = SKILL_ROOT / "assets" / "audit-result-template.html"
SLOT_PATTERN = re.compile(
    r'<script id="audit-data" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def load_module():
    if not SCRIPT_PATH.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        "render_audit_result",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_result():
    return {
        "schemaVersion": "adp-audit-result-1.0",
        "templateVersion": "audit-result-template-1.0",
        "generatedAt": "2026-08-01T09:30:00+08:00",
        "audit": {
            "auditId": "AUDIT-SYNTHETIC-001",
            "diseaseName": "尿毒症透析",
            "diseaseCode": "MZMB-001",
            "finalResult": "不通过",
            "advice": "建议补充透析记录后由业务人员复核。",
            "materialCount": 2,
        },
        "ruleResults": [
            {
                "ruleCode": "R-001",
                "ruleContent": "规律透析治疗满三个月",
                "ruleResult": "不通过",
                "reasoningContent": "现有记录只覆盖两个月，未达到时长要求。",
                "ruleKeywordGuide": [
                    {
                        "keyword": "透析日期",
                        "found": True,
                        "results": [
                            {
                                "materialName": "透析治疗记录",
                                "materialId": "MAT-001",
                                "materialSource": "申请材料",
                                "rawText": "2026年6月至7月规律透析",
                                "value": "2个月",
                            }
                        ],
                    }
                ],
                "suspicionList": [
                    {
                        "suspicionType": "材料时限不足",
                        "detail": "透析记录未覆盖三个月。",
                        "sources": [
                            {
                                "materialName": "透析治疗记录",
                                "materialId": "MAT-001",
                            }
                        ],
                    }
                ],
            },
            {
                "ruleCode": "R-002",
                "ruleContent": "诊断材料完整",
                "ruleResult": "通过",
                "reasoningContent": "诊断证明可支持疾病诊断。",
                "ruleKeywordGuide": [],
                "suspicionList": [],
            },
        ],
        "execution": {
            "profile": "synthetic-profile",
            "runEnv": 1,
            "workflowRunId": "wfr-synthetic-001",
            "requestId": "req-synthetic-001",
        },
    }


class RenderAuditResultTests(unittest.TestCase):
    def require_module(self):
        self.assertIsNotNone(
            MODULE,
            "render_audit_result.py should exist",
        )
        return MODULE

    def read_template(self):
        self.assertTrue(
            TEMPLATE_PATH.exists(),
            "audit-result-template.html should exist",
        )
        return TEMPLATE_PATH.read_text(encoding="utf-8")

    def test_template_has_exactly_one_fixed_data_slot(self):
        template = self.read_template()
        slot = (
            '<script id="audit-data" type="application/json">'
            "__AUDIT_DATA_JSON__</script>"
        )
        self.assertEqual(template.count("__AUDIT_DATA_JSON__"), 1)
        self.assertEqual(template.count(slot), 1)

    def test_semantic_duplicate_data_slot_is_rejected(self):
        module = self.require_module()
        template = self.read_template().replace(
            "</body>",
            "<script type = 'application/json' id = 'audit-data'>"
            "{}</script>\n</body>",
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".html",
        ) as template_file:
            template_file.write(template)
            template_file.flush()
            with self.assertRaises(module.RenderError):
                module.render_result(sample_result(), template_file.name)

    def test_template_is_offline_and_uses_safe_dom_apis(self):
        template = self.read_template()
        self.assertNotRegex(template, r"https?://")
        self.assertNotIn("innerHTML", template)
        self.assertIn("textContent", template)
        self.assertIn("createElement", template)
        self.assertIn("replaceChildren", template)

    def test_template_has_print_and_narrow_screen_styles(self):
        template = self.read_template()
        self.assertIn("@media print", template)
        self.assertRegex(template, r"@media\s*\([^)]*max-width")
        self.assertIn("overflow-wrap", template)
        self.assertIn("break-inside", template)

    def test_template_contains_all_business_sections_and_fields(self):
        template = self.read_template()
        labels = (
            "报告概览",
            "病种",
            "编码",
            "审核流水号",
            "生成时间",
            "总审核结论",
            "申请材料数",
            "审核建议",
            "规则统计",
            "逐条认定结果",
            "疑点列表",
            "疑点类型",
            "疑点说明",
            "关联材料",
            "证据详情",
            "关键词",
            "材料名称",
            "材料 ID",
            "材料来源",
            "材料原文",
            "提取值",
            "推理说明",
            "工作流实例 ID",
            "请求 ID",
        )
        for label in labels:
            with self.subTest(label=label):
                self.assertIn(label, template)

    def test_rendered_slot_round_trips_exact_result(self):
        module = self.require_module()
        result = sample_result()
        html = module.render_result(result, TEMPLATE_PATH)
        matches = SLOT_PATTERN.findall(html)
        self.assertEqual(len(matches), 1)
        self.assertEqual(json.loads(matches[0]), result)
        self.assertNotIn("__AUDIT_DATA_JSON__", html)

    def test_script_breakout_and_ampersand_are_unicode_escaped(self):
        module = self.require_module()
        result = sample_result()
        dangerous = "</script><script>alert('x')</script>&<>"
        result["audit"]["advice"] = dangerous
        result["ruleResults"][0]["ruleKeywordGuide"][0]["results"][0][
            "rawText"
        ] = dangerous

        html = module.render_result(result, TEMPLATE_PATH)
        slot = SLOT_PATTERN.findall(html)[0]

        self.assertNotIn("</script>", slot)
        self.assertNotIn("<script>", slot)
        self.assertNotIn("&", slot)
        self.assertNotIn("<", slot)
        self.assertNotIn(">", slot)
        self.assertIn("\\u003c", slot)
        self.assertIn("\\u0026", slot)
        self.assertEqual(json.loads(slot), result)

    def test_schema_and_template_version_mismatches_are_rejected(self):
        module = self.require_module()
        for field in ("schemaVersion", "templateVersion"):
            with self.subTest(field=field):
                result = sample_result()
                result[field] = "unsupported"
                with self.assertRaises(module.RenderError):
                    module.render_result(result, TEMPLATE_PATH)

    def test_missing_or_wrongly_typed_contract_fields_are_rejected(self):
        module = self.require_module()
        invalid_results = []

        missing_generated_at = sample_result()
        missing_generated_at.pop("generatedAt")
        invalid_results.append(missing_generated_at)

        missing_audit_field = sample_result()
        missing_audit_field["audit"].pop("diseaseCode")
        invalid_results.append(missing_audit_field)

        bool_material_count = sample_result()
        bool_material_count["audit"]["materialCount"] = True
        invalid_results.append(bool_material_count)

        wrong_rule = sample_result()
        wrong_rule["ruleResults"] = ["not-an-object"]
        invalid_results.append(wrong_rule)

        wrong_guide = sample_result()
        wrong_guide["ruleResults"][0]["ruleKeywordGuide"] = [None]
        invalid_results.append(wrong_guide)

        wrong_evidence = sample_result()
        wrong_evidence["ruleResults"][0]["ruleKeywordGuide"][0][
            "results"
        ][0]["materialId"] = 123
        invalid_results.append(wrong_evidence)

        wrong_suspicion = sample_result()
        wrong_suspicion["ruleResults"][0]["suspicionList"] = [None]
        invalid_results.append(wrong_suspicion)

        wrong_source = sample_result()
        wrong_source["ruleResults"][0]["suspicionList"][0]["sources"] = [
            None
        ]
        invalid_results.append(wrong_source)

        missing_execution_field = sample_result()
        missing_execution_field["execution"].pop("workflowRunId")
        invalid_results.append(missing_execution_field)

        bool_run_env = sample_result()
        bool_run_env["execution"]["runEnv"] = True
        invalid_results.append(bool_run_env)

        for index, result in enumerate(invalid_results):
            with self.subTest(index=index):
                with self.assertRaises(module.RenderError):
                    module.render_result(result, TEMPLATE_PATH)

    def test_unsafe_audit_ids_are_rejected_without_directory_escape(self):
        module = self.require_module()
        unsafe_ids = (
            "../outside",
            "..",
            ".",
            "nested/report",
            "nested\\report",
            "line\nbreak",
            "control\x00character",
        )
        with tempfile.TemporaryDirectory() as directory:
            output_dir = pathlib.Path(directory) / "output"
            for audit_id in unsafe_ids:
                with self.subTest(audit_id=repr(audit_id)):
                    result = sample_result()
                    result["audit"]["auditId"] = audit_id
                    with self.assertRaises(module.RenderError):
                        module.write_html(
                            result,
                            TEMPLATE_PATH,
                            output_dir,
                        )
            self.assertFalse((pathlib.Path(directory) / "outside").exists())
            self.assertFalse(list(pathlib.Path(directory).rglob("*.tmp")))

    def test_write_html_uses_fixed_name_and_leaves_no_temp_file(self):
        module = self.require_module()
        with tempfile.TemporaryDirectory() as directory:
            path = module.write_html(
                sample_result(),
                TEMPLATE_PATH,
                directory,
            )
            self.assertEqual(
                path.name,
                "AUDIT-SYNTHETIC-001-智能审核结果.html",
            )
            self.assertEqual(path.parent, pathlib.Path(directory))
            self.assertTrue(path.is_file())
            self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_render_failure_leaves_no_partial_html_or_temp_file(self):
        module = self.require_module()
        with tempfile.TemporaryDirectory() as directory:
            result = sample_result()
            result["ruleResults"].append(float("nan"))
            with self.assertRaises(module.RenderError):
                module.write_html(
                    result,
                    TEMPLATE_PATH,
                    directory,
                )
            self.assertEqual(list(pathlib.Path(directory).iterdir()), [])

    def test_cli_success_prints_absolute_path(self):
        module = self.require_module()
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            input_path = root / "result.json"
            input_path.write_text(
                json.dumps(sample_result(), ensure_ascii=False),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            status = module.main(
                [
                    "--input-json",
                    str(input_path),
                    "--template",
                    str(TEMPLATE_PATH),
                    "--output-dir",
                    str(root / "output"),
                ],
                stdout=stdout,
            )
            response = json.loads(stdout.getvalue())

            self.assertEqual(status, 0)
            self.assertEqual(response["ok"], True)
            self.assertTrue(pathlib.Path(response["htmlPath"]).is_absolute())
            self.assertTrue(pathlib.Path(response["htmlPath"]).is_file())

    def test_cli_argument_errors_are_stable_json_without_stderr_or_echo(self):
        module = self.require_module()
        private_argument = "PRIVATE-UNKNOWN-ARGUMENT-VALUE"
        cases = (
            ["--unknown-option", private_argument],
            ["--input-json", private_argument],
        )
        expected = {
            "ok": False,
            "error": {
                "type": "render",
                "message": "命令参数无效",
            },
        }

        for argv in cases:
            with self.subTest(argv=argv[:1]):
                stdout = io.StringIO()
                stderr = io.StringIO()
                try:
                    with contextlib.redirect_stderr(stderr):
                        status = module.main(argv, stdout=stdout)
                except SystemExit as error:
                    status = error.code

                self.assertEqual(status, 1)
                self.assertEqual(json.loads(stdout.getvalue()), expected)
                self.assertEqual(stderr.getvalue(), "")
                self.assertNotIn(
                    private_argument,
                    stdout.getvalue() + stderr.getvalue(),
                )

    def test_cli_failure_is_render_error_without_traceback_or_user_text(self):
        module = self.require_module()
        private_text = "USER-PRIVATE-MATERIAL-TEXT"
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            input_path = root / "invalid.json"
            invalid = sample_result()
            invalid["audit"]["advice"] = private_text
            invalid["audit"]["materialCount"] = "two"
            input_path.write_text(
                json.dumps(invalid, ensure_ascii=False),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = module.main(
                    [
                        "--input-json",
                        str(input_path),
                        "--template",
                        str(TEMPLATE_PATH),
                        "--output-dir",
                        str(root / "output"),
                    ],
                    stdout=stdout,
                )
            response = json.loads(stdout.getvalue())
            combined = stdout.getvalue() + stderr.getvalue()

            self.assertEqual(status, 1)
            self.assertEqual(response["ok"], False)
            self.assertEqual(response["error"]["type"], "render")
            self.assertNotIn("Traceback", combined)
            self.assertNotIn(private_text, combined)
            output_dir = root / "output"
            if output_dir.exists():
                self.assertEqual(list(output_dir.iterdir()), [])


MODULE = load_module()


if __name__ == "__main__":
    unittest.main()
