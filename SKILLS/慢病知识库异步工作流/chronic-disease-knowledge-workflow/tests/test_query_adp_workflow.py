import importlib.util
import io
import json
import pathlib
import tempfile
import unittest


SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "query_adp_workflow.py"


def load_module():
    if not SCRIPT_PATH.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        "query_adp_workflow",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


def sample_config():
    return {
        "api_host": "http://10.80.38.161",
        "app_id": "2082072305231359424",
        "secret_id": "AKIDEXAMPLE",
        "secret_key": "SECRETEXAMPLE",
        "run_env": 1,
        "region": "1",
        "service": "lke",
        "version": "2023-11-30",
        "poll_interval_seconds": 1,
        "timeout_seconds": 5,
    }


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class QueryAdpWorkflowTests(unittest.TestCase):
    def require_module(self):
        self.assertIsNotNone(
            MODULE,
            "query_adp_workflow.py should exist",
        )
        return MODULE

    def test_template_contains_direct_private_deployment_fields(self):
        template_path = (
            SKILL_ROOT / "config" / "adp-config.template.json"
        )
        config = json.loads(template_path.read_text(encoding="utf-8"))
        self.assertEqual(
            list(config),
            [
                "api_host",
                "app_id",
                "secret_id",
                "secret_key",
                "run_env",
                "region",
                "service",
                "version",
                "poll_interval_seconds",
                "timeout_seconds",
            ],
        )
        self.assertEqual(config["service"], "lke")
        self.assertEqual(config["version"], "2023-11-30")

    def test_load_config_reads_direct_credentials(self):
        module = self.require_module()
        config = sample_config()
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
        ) as file:
            json.dump(config, file)
            file.flush()
            loaded = module.load_config(file.name)
        self.assertEqual(loaded["api_host"], config["api_host"])
        self.assertEqual(loaded["app_id"], config["app_id"])
        self.assertEqual(loaded["secret_id"], config["secret_id"])
        self.assertEqual(loaded["secret_key"], config["secret_key"])

    def test_load_config_rejects_missing_required_field_without_secret(self):
        module = self.require_module()
        config = sample_config()
        secret = config.pop("secret_key")
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
        ) as file:
            json.dump(config, file)
            file.flush()
            with self.assertRaises(module.ConfigError) as raised:
                module.load_config(file.name)
        self.assertEqual(raised.exception.error_type, "config")
        self.assertNotIn(secret, str(raised.exception))

    def test_tc3_signature_matches_fixed_vector(self):
        module = self.require_module()
        config = sample_config()
        body = (
            b'{"AppBizId":"2082072305231359424","Query":"test",'
            b'"RunEnv":1,"VisitorId":"visitor-1"}'
        )
        headers = module.build_signed_headers(
            config,
            "CreateWorkflowRun",
            body,
            1700000000,
        )
        self.assertEqual(headers["X-TC-Timestamp"], "1700000000")
        self.assertEqual(headers["X-TC-Action"], "CreateWorkflowRun")
        self.assertIn(
            "Signature="
            "bfbf0ed5100b0f135a48b11e7f44ada7c4e583b70479c2741c63b81bc96d3fd0",
            headers["Authorization"],
        )
        self.assertIn(
            "SignedHeaders=content-type;host",
            headers["Authorization"],
        )

    def test_query_workflow_creates_polls_and_extracts_answer(self):
        module = self.require_module()
        calls = []
        responses = [
            {
                "Response": {
                    "WorkflowRunId": "wfr-test",
                    "RequestId": "req-create",
                }
            },
            {
                "Response": {
                    "WorkflowRun": {
                        "WorkflowRunId": "wfr-test",
                        "State": 1,
                        "Output": "",
                    },
                    "RequestId": "req-pending",
                }
            },
            {
                "Response": {
                    "WorkflowRun": {
                        "WorkflowRunId": "wfr-test",
                        "State": 2,
                        "Output": json.dumps(
                            {"answer": "知识库检索结果"},
                            ensure_ascii=False,
                        ),
                    },
                    "RequestId": "req-finished",
                }
            },
        ]

        def fake_post(config, action, payload):
            calls.append((action, payload))
            return responses.pop(0)

        clock = FakeClock()
        result = module.query_workflow(
            sample_config(),
            "尿毒症透析认定标准",
            post=fake_post,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            visitor_id_factory=lambda: "visitor-test",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["answer"], "知识库检索结果")
        self.assertEqual(result["workflow"]["run_id"], "wfr-test")
        self.assertEqual(result["workflow"]["state"], 2)
        self.assertEqual(
            result["workflow"]["output"],
            {"answer": "知识库检索结果"},
        )
        self.assertEqual(
            calls[0],
            (
                "CreateWorkflowRun",
                {
                    "AppBizId": "2082072305231359424",
                    "RunEnv": 1,
                    "Query": "尿毒症透析认定标准",
                    "VisitorId": "visitor-test",
                },
            ),
        )
        self.assertEqual(
            calls[1],
            (
                "DescribeWorkflowRun",
                {
                    "AppBizId": "2082072305231359424",
                    "WorkflowRunId": "wfr-test",
                },
            ),
        )

    def test_query_workflow_classifies_adp_auth_error(self):
        module = self.require_module()

        def fake_post(config, action, payload):
            return {
                "Response": {
                    "Error": {
                        "Code": "AuthFailure.SignatureFailure",
                        "Message": "signature failed",
                    },
                    "RequestId": "req-auth",
                }
            }

        with self.assertRaises(module.WorkflowError) as raised:
            module.query_workflow(
                sample_config(),
                "测试",
                post=fake_post,
            )
        self.assertEqual(raised.exception.error_type, "auth")
        self.assertEqual(raised.exception.request_id, "req-auth")

    def test_query_workflow_reports_failed_run(self):
        module = self.require_module()
        responses = [
            {
                "Response": {
                    "WorkflowRunId": "wfr-failed",
                    "RequestId": "req-create",
                }
            },
            {
                "Response": {
                    "WorkflowRun": {
                        "WorkflowRunId": "wfr-failed",
                        "State": 3,
                        "FailMessage": "应用模式不支持",
                        "Output": "",
                    },
                    "RequestId": "req-failed",
                }
            },
        ]

        def fake_post(config, action, payload):
            return responses.pop(0)

        with self.assertRaises(module.WorkflowError) as raised:
            module.query_workflow(
                sample_config(),
                "测试",
                post=fake_post,
            )
        self.assertEqual(raised.exception.error_type, "workflow")
        self.assertEqual(raised.exception.request_id, "req-failed")

    def test_query_workflow_times_out_while_pending(self):
        module = self.require_module()

        def fake_post(config, action, payload):
            if action == "CreateWorkflowRun":
                return {
                    "Response": {
                        "WorkflowRunId": "wfr-timeout",
                        "RequestId": "req-create",
                    }
                }
            return {
                "Response": {
                    "WorkflowRun": {
                        "WorkflowRunId": "wfr-timeout",
                        "State": 1,
                        "Output": "",
                    },
                    "RequestId": "req-pending",
                }
            }

        config = sample_config()
        config["timeout_seconds"] = 2
        clock = FakeClock()
        with self.assertRaises(module.WorkflowError) as raised:
            module.query_workflow(
                config,
                "测试",
                post=fake_post,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )
        self.assertEqual(raised.exception.error_type, "timeout")

    def test_print_error_never_includes_secret(self):
        module = self.require_module()
        secret = sample_config()["secret_key"]
        output = io.StringIO()
        module.print_error(
            module.WorkflowError(
                "ADP 请求失败",
                error_type="http",
                request_id="req-safe",
            ),
            stream=output,
        )
        parsed = json.loads(output.getvalue())
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["error"]["request_id"], "req-safe")
        self.assertNotIn(secret, output.getvalue())


if __name__ == "__main__":
    unittest.main()
