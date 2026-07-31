import importlib.util
import json
import pathlib
import re
import tempfile
import unittest


SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OfflineIntegrationTests(unittest.TestCase):
    def test_workflow_result_writes_json_and_matching_fixed_html(self):
        self.assertTrue(
            (SKILL_ROOT / "scripts" / "run_adp_audit_workflow.py").is_file(),
            "new ADP audit client must exist before integration can pass",
        )
        self.assertTrue(
            (SKILL_ROOT / "scripts" / "render_audit_result.py").is_file(),
            "fixed-template renderer must exist before integration can pass",
        )
        client = load_module(
            "adp_audit_client",
            SKILL_ROOT / "scripts" / "run_adp_audit_workflow.py",
        )
        renderer = load_module(
            "adp_audit_renderer",
            SKILL_ROOT / "scripts" / "render_audit_result.py",
        )
        audit_input = json.loads(
            (FIXTURES / "canonical-audit-input.json").read_text(
                encoding="utf-8"
            )
        )
        workflow_output = json.loads(
            (FIXTURES / "successful-workflow-output.json").read_text(
                encoding="utf-8"
            )
        )
        config = {
            "profile": "cloud",
            "api_host": "https://example.test",
            "app_id": "app-test",
            "app_key": "APPKEY_TEST_ONLY",
            "secret_id": "SECRET_ID_TEST_ONLY",
            "secret_key": "SECRET_KEY_TEST_ONLY",
            "run_env": 0,
            "region": "1",
            "service": "lke",
            "version": "2023-11-30",
            "poll_interval_seconds": 1,
            "timeout_seconds": 5,
        }
        responses = [
            {
                "Response": {
                    "WorkflowRunId": "wfr-synthetic-001",
                    "RequestId": "req-create",
                }
            },
            {
                "Response": {
                    "WorkflowRun": {
                        "State": 2,
                        "Output": workflow_output,
                    },
                    "RequestId": "req-synthetic-001",
                }
            },
        ]

        result = client.run_audit_workflow(
            config,
            audit_input,
            post=lambda *_: responses.pop(0),
            uuid_factory=lambda: "visitor-test",
            now_factory=lambda: "2026-08-01T01:30:00Z",
        )

        with tempfile.TemporaryDirectory() as directory:
            json_path = client.write_result_atomic(result, directory)
            html_path = renderer.write_html(
                result,
                SKILL_ROOT / "assets" / "audit-result-template.html",
                directory,
            )
            delivered_json = json.loads(
                json_path.read_text(encoding="utf-8")
            )
            html = html_path.read_text(encoding="utf-8")
            embedded = re.search(
                r'<script id="audit-data" type="application/json">'
                r"(.*?)</script>",
                html,
                re.DOTALL,
            )

            self.assertIsNotNone(embedded)
            self.assertEqual(json.loads(embedded.group(1)), delivered_json)
            artifacts = list(pathlib.Path(directory).iterdir())
            self.assertEqual(len(artifacts), 2)
            self.assertEqual({path.suffix for path in artifacts}, {".json", ".html"})
            delivered_text = json_path.read_text(encoding="utf-8") + html
            self.assertNotIn("SECRET_KEY_TEST_ONLY", delivered_text)
            self.assertNotIn("materialContent", delivered_text)


if __name__ == "__main__":
    unittest.main()
