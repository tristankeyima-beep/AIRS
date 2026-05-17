import importlib.util
import json
import ssl
import tempfile
import unittest
from pathlib import Path


TOOL_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = TOOL_DIR / "dify_airs_runner.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("dify_airs_runner", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DifyAirsRunnerTests(unittest.TestCase):
    def test_prepare_input_writes_case_with_unknown_patient_and_stringified_inputs(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            raw_input = {
                "auditId": "AUDIT-DEMO-001",
                "certification_list": {
                    "meta": {"chronicDiseaseName": "尿毒症肾透析治疗"},
                    "ruleRepository": [],
                },
                "material_list": [
                    {
                        "materialName": "病案首页",
                        "materialContent": "出院诊断：慢性肾衰竭。",
                    }
                ],
            }
            source = tmp_path / "raw.json"
            source.write_text(json.dumps(raw_input, ensure_ascii=False), encoding="utf-8")

            result = runner.prepare_input_file(
                source,
                tmp_path,
                now=runner.parse_local_time("2026-05-16T15:30:31+08:00"),
            )

            self.assertEqual(result.patient_name, "未知患者")
            self.assertEqual(result.disease_name, "尿毒症肾透析治疗")
            self.assertEqual(result.case_dir.name, "未知患者_尿毒症肾透析治疗_20260516-153031")
            saved = json.loads((result.case_dir / "入参.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["dify_payload"]["inputs"]["auditId"], "AUDIT-DEMO-001")
            self.assertIsInstance(saved["dify_payload"]["inputs"]["certification_list"], str)
            self.assertIsInstance(saved["dify_payload"]["inputs"]["material_list"], str)
            self.assertEqual(
                json.loads(saved["dify_payload"]["inputs"]["certification_list"])["meta"]["chronicDiseaseName"],
                "尿毒症肾透析治疗",
            )

    def test_prepare_input_parses_string_inputs_and_extracts_patient_name(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            raw_input = {
                "certification_list": json.dumps(
                    {"meta": {"chronicDiseaseName": "糖尿病"}, "ruleRepository": []},
                    ensure_ascii=False,
                ),
                "material_list": json.dumps(
                    [{"materialName": "入院记录", "materialContent": "姓名：刘会芝\n年龄：69岁"}],
                    ensure_ascii=False,
                ),
                "system_prompt": "",
                "user_prompt": "请审核",
                "suspicion_type_options": "指标异常;信息缺失",
                "auditId": "2055213118690373632",
            }
            source = tmp_path / "raw-string.json"
            source.write_text(json.dumps(raw_input, ensure_ascii=False), encoding="utf-8")

            result = runner.prepare_input_file(
                source,
                tmp_path,
                now=runner.parse_local_time("2026-05-16T15:30:31+08:00"),
            )
            saved = json.loads((result.case_dir / "入参.json").read_text(encoding="utf-8"))

            self.assertEqual(result.patient_name, "刘会芝")
            self.assertEqual(result.disease_name, "糖尿病")
            self.assertEqual(result.case_dir.name, "刘会芝_糖尿病_20260516-153031")
            self.assertEqual(saved["dify_payload"]["inputs"]["system_prompt"], "")
            self.assertEqual(saved["dify_payload"]["inputs"]["user_prompt"], "请审核")
            self.assertEqual(saved["dify_payload"]["inputs"]["suspicion_type_options"], "指标异常;信息缺失")
            self.assertEqual(saved["dify_payload"]["inputs"]["auditId"], "2055213118690373632")

    def test_result_directory_uses_workflow_run_id_and_html_masks_authorization(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            case_dir = tmp_path / "刘会芝_糖尿病_20260516-153031"
            case_dir.mkdir()
            (case_dir / "入参.json").write_text(
                json.dumps(
                    {
                        "metadata": {"patientName": "刘会芝", "diseaseName": "糖尿病"},
                        "dify_payload": {
                            "inputs": {"auditId": "A1"},
                            "response_mode": "streaming",
                            "user": "dify-airs-workflow-test",
                        },
                        "terminal_command": "cd x && python3 dify_airs_runner.py run --case-dir y",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            record = {
                "startedAt": "2026-05-16T15:40:56+08:00",
                "request": {"headers": {"Authorization": "Bearer ***"}},
                "events": [
                    {
                        "payload": {
                            "event": "workflow_finished",
                            "workflow_run_id": "abc-123",
                            "data": {"outputs": {"reviewResult": "通过"}},
                        }
                    }
                ],
                "nodeRuns": [],
                "finalOutputs": {"reviewResult": "通过"},
                "response": {"status": 200},
            }

            output_dir, raw_path, html_path = runner.write_result_record(
                case_dir,
                record,
                runner.parse_local_time("2026-05-16T15:40:56+08:00"),
            )

            self.assertEqual(output_dir.name, "20260516-154056_abc-123")
            self.assertEqual(raw_path.name, "20260516-154056_abc-123_raw-result.json")
            self.assertEqual(html_path.name, "20260516-154056_abc-123_result.html")
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("刘会芝", html)
            self.assertIn("糖尿病", html)
            self.assertIn("abc-123", html)
            self.assertIn("完整原始数据", html)
            self.assertIn("Bearer ***", html)
            self.assertNotIn("app-Tu3IsM34EGqwxC0j0OpVq5mm", html)

    def test_html_renders_auditable_rule_evidence_layout(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            case_dir = tmp_path / "宋绍兵_脑梗死（恢复期）_20260516-161058"
            case_dir.mkdir()
            (case_dir / "入参.json").write_text(
                json.dumps(
                    {
                        "metadata": {"patientName": "宋绍兵", "diseaseName": "脑梗死（恢复期）"},
                        "raw_input": {"auditId": "A1"},
                        "parsed_input": {
                            "certification_list": {
                                "logicTopology": {
                                    "type": "GROUP",
                                    "operator": "AND",
                                    "children": [{"type": "RULE_REF", "ruleCode": "1001"}],
                                }
                            }
                        },
                        "dify_payload": {"inputs": {"auditId": "A1"}},
                        "terminal_command": "cd x && python3 dify_airs_runner.py run --case-dir y",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            record = {
                "startedAt": "2026-05-16T16:39:25+08:00",
                "request": {"headers": {"Authorization": "Bearer ***"}},
                "response": {"status": 200},
                "events": [],
                "nodeRuns": [
                    {
                        "title": "原文精解",
                        "type": "llm",
                        "status": "succeeded",
                        "elapsedSeconds": 12.5,
                        "outputs": {"text": "{\"ruleCode\":\"1001\"}"},
                    },
                    {
                        "title": "逐条认定",
                        "type": "llm",
                        "status": "succeeded",
                        "elapsedSeconds": 8.2,
                        "outputs": {"text": "{\"ruleCode\":\"1001\",\"ruleResult\":\"不通过\"}"},
                    },
                ],
                "finalOutputs": {
                    "finalResult": "不通过",
                    "auditId": "A1",
                    "advice": "本次审核未通过。",
                    "ruleResults": [
                        {
                            "ruleCode": "1001",
                            "ruleContent": "临床出现相应的脑部神经系统症状及体征。",
                            "ruleResult": "不通过",
                            "reasoningContent": "未见住院治疗后仍遗有神经症状需继续治疗。",
                            "ruleKeywordGuide": [
                                {
                                    "keywordCode": "1001_01",
                                    "found": True,
                                    "results": [
                                        {
                                            "materialName": "出院记录",
                                            "materialId": "M1",
                                            "rawText": "出院诊断：多发性脑梗死",
                                            "value": "脑梗死（脑栓塞）",
                                        }
                                    ],
                                }
                            ],
                            "suspicionList": [
                                {
                                    "suspicionType": "临床表现不足",
                                    "detail": "未见脑部神经系统症状及体征的描述。",
                                    "sources": [
                                        {"materialName": "出院记录", "materialId": "M1", "refContent": "出院诊断：多发性脑梗死"}
                                    ],
                                }
                            ],
                        }
                    ],
                },
                "error": None,
            }

            rendered = runner.render_html(case_dir, record, "run-1")

            self.assertIn("side-nav", rendered)
            self.assertIn("审核结论", rendered)
            self.assertIn("规则判定总览", rendered)
            self.assertIn("AND · 全部条件满足", rendered)
            self.assertIn("overview-rule", rendered)
            self.assertIn("规则链路", rendered)
            self.assertIn("证据原文", rendered)
            self.assertIn("疑点说明", rendered)
            self.assertIn("完整模型推理过程", rendered)
            self.assertIn("decision-box", rendered)
            self.assertIn("<details class=\"keyword-card\">", rendered)
            self.assertIn("并行分支处理链路", rendered)
            self.assertIn("原文精解", rendered)
            self.assertIn("12.50 秒", rendered)
            self.assertIn("完整节点明细", rendered)
            self.assertIn("出院诊断：多发性脑梗死", rendered)
            self.assertIn("临床表现不足", rendered)

    def test_result_record_writes_html_when_response_is_none(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            case_dir = tmp_path / "宋绍兵_脑梗死（恢复期）_20260516-161058"
            case_dir.mkdir()
            (case_dir / "入参.json").write_text(
                json.dumps(
                    {
                        "metadata": {"patientName": "宋绍兵", "diseaseName": "脑梗死（恢复期）"},
                        "raw_input": {"auditId": "2055137621038018560"},
                        "dify_payload": {"inputs": {"auditId": "2055137621038018560"}},
                        "terminal_command": "cd x && python3 dify_airs_runner.py run --case-dir y",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            record = {
                "startedAt": "2026-05-16T16:30:00+08:00",
                "request": {"headers": {"Authorization": "Bearer ***"}},
                "response": None,
                "events": [],
                "nodeRuns": [],
                "finalOutputs": None,
                "error": {"type": "URLError", "message": "timed out"},
            }

            output_dir, raw_path, html_path = runner.write_result_record(
                case_dir,
                record,
                runner.parse_local_time("2026-05-16T16:30:00+08:00"),
            )

            self.assertEqual(output_dir.name, "20260516-163000_no-workflowrunid")
            self.assertTrue(raw_path.exists())
            self.assertTrue(html_path.exists())
            rendered = html_path.read_text(encoding="utf-8")
            self.assertIn("宋绍兵", rendered)
            self.assertIn("脑梗死（恢复期）", rendered)
            self.assertIn("timed out", rendered)

    def test_default_api_base_uses_https_and_ssl_context_is_available(self):
        runner = load_runner()

        self.assertEqual(runner.DEFAULT_API_BASE, "https://dify.hzmarvel.com/v1")
        context = runner.create_ssl_context()
        self.assertIsNotNone(context)
        if hasattr(ssl, "OP_IGNORE_UNEXPECTED_EOF"):
            self.assertTrue(context.options & ssl.OP_IGNORE_UNEXPECTED_EOF)

    def test_run_error_hint_explains_invalid_access_token(self):
        runner = load_runner()
        record = {
            "error": {"type": "HTTPError", "message": "HTTP Error 401: UNAUTHORIZED"},
            "response": {
                "status": 401,
                "body": "{\"code\":\"unauthorized\",\"message\":\"Access token is invalid\",\"status\":401}\n",
            },
        }

        hint = runner.get_run_error_hint(record)

        self.assertIn("API Key 无效", hint)
        self.assertIn("README.md", hint)
        self.assertIn("--api-key", hint)

    def test_collect_curl_response_parses_streaming_workflow_run_id(self):
        runner = load_runner()
        output = (
            'data: {"event":"workflow_started","workflow_run_id":"run-1","data":{"id":"run-1"}}\n\n'
            'data: {"event":"workflow_finished","workflow_run_id":"run-1","data":{"outputs":{"reviewResult":"通过"}}}\n\n'
            '\n__DIFY_HTTP_STATUS__:200\n'
        )
        record = {
            "response": None,
            "events": [],
            "nodeRuns": [],
            "finalOutputs": None,
            "error": None,
        }

        runner.collect_curl_response(record, output, "")

        self.assertEqual(record["response"]["status"], 200)
        self.assertEqual(len(record["events"]), 2)
        self.assertEqual(record["finalOutputs"], {"reviewResult": "通过"})
        self.assertEqual(runner.find_workflow_run_id(record), "run-1")


if __name__ == "__main__":
    unittest.main()
