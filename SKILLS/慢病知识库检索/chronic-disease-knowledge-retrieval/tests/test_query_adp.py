import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "query_adp.py"


def load_query_adp():
    spec = importlib.util.spec_from_file_location("query_adp", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QueryAdpContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.query_adp = load_query_adp()

    def test_build_request_uses_app_key_and_preserves_query_identity(self):
        config = {
            "app_key_env": "ADP_APP_KEY",
            "streaming_throttle": 10,
            "workflow_status": "enable",
            "search_network": "disable",
        }
        with mock.patch.dict(
            os.environ, {"ADP_APP_KEY": "test-only-key"}, clear=True
        ):
            request = self.query_adp.build_request(
                config, "糖尿病的诊断标准是什么？"
            )

        self.assertEqual(request["content"], "糖尿病的诊断标准是什么？")
        self.assertEqual(request["bot_app_key"], "test-only-key")
        self.assertEqual(request["session_id"], request["visitor_biz_id"])
        self.assertTrue(request["request_id"])
        self.assertEqual(request["workflow_status"], "enable")
        self.assertEqual(request["search_network"], "disable")
        self.assertEqual(request["streaming_throttle"], 10)

    def test_build_request_without_app_key_raises_safe_config_error(self):
        config = {
            "app_key_env": "ADP_APP_KEY",
            "streaming_throttle": 10,
            "workflow_status": "enable",
            "search_network": "disable",
        }
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                self.query_adp.ConfigError, "ADP_APP_KEY"
            ):
                self.query_adp.build_request(config, "test query")

    def test_read_sse_parses_legacy_reply_and_reference_events(self):
        stream = io.BytesIO(
            b'data: ["reply", {"type": "reply", "payload": '
            b'{"content": "test answer"}}]\n\n'
            b'data: ["reference", {"type": "reference", "payload": '
            b'{"references": [{"doc_name": "test document"}]}}]\n\n'
        )

        events = list(self.query_adp.read_sse(stream))

        self.assertEqual([event_name for event_name, _ in events], [
            "reply",
            "reference",
        ])
        self.assertEqual(
            events[0][1],
            {
                "type": "reply",
                "payload": {"content": "test answer"},
            },
        )
        self.assertEqual(
            events[1][1],
            {
                "type": "reference",
                "payload": {
                    "references": [{"doc_name": "test document"}],
                },
            },
        )

    def test_collect_result_separates_answer_reference_workflow_and_ids(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "test answer",
                        "is_final": True,
                        "request_id": "test-request-001",
                        "session_id": "test-session-001",
                        "knowledge": [
                            {
                                "title": "reply knowledge must not leak",
                                "content": "non-normalized reply metadata",
                            }
                        ],
                        "work_flow": {
                            "workflow_name": "test workflow",
                            "workflow_run_id": "test-run-001",
                            "outputs": {"result": "test output"},
                        },
                    },
                },
            ),
            (
                "reference",
                {
                    "payload": {
                        "references": [
                            {
                                "type": 2,
                                "doc_name": "test guideline",
                                "name": "test reference",
                                "url": "https://example.test/guideline",
                            }
                        ],
                    },
                },
            ),
            (
                "token_stat",
                {
                    "payload": {
                        "input_tokens": 10,
                        "output_tokens": 20,
                    },
                },
            ),
        ]

        result = self.query_adp.collect_result("test query", events)

        self.assertIs(result["ok"], True)
        self.assertEqual(result["query"], "test query")
        self.assertEqual(result["answer"], "test answer")
        self.assertEqual(len(result["knowledge"]), 1)
        self.assertEqual(result["knowledge"][0]["type"], "document")
        self.assertEqual(result["knowledge"][0]["title"], "test guideline")
        self.assertEqual(result["knowledge"][0]["content"], "")
        self.assertEqual(
            result["knowledge"][0]["url"],
            "https://example.test/guideline",
        )
        self.assertIsNone(result["knowledge"][0]["confidence"])
        self.assertEqual(result["workflow"]["name"], "test workflow")
        self.assertEqual(result["workflow"]["run_id"], "test-run-001")
        self.assertEqual(
            result["workflow"]["outputs"], {"result": "test output"}
        )
        self.assertEqual(result["meta"]["request_id"], "test-request-001")
        self.assertEqual(result["meta"]["session_id"], "test-session-001")
        self.assertEqual(result["meta"]["source"], "tencent-adp")

    def test_collect_result_raises_adp_error_for_error_event(self):
        events = [
            (
                "error",
                {
                    "payload": {
                        "message": "test upstream failure",
                        "request_id": "test-request-002",
                        "session_id": "test-session-002",
                    },
                },
            ),
        ]

        with self.assertRaises(self.query_adp.AdPError):
            self.query_adp.collect_result("test query", events)

    def test_collect_result_raises_adp_error_for_failed_token_status(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "partial test answer",
                        "is_final": False,
                        "request_id": "test-request-004",
                        "session_id": "test-session-004",
                        "knowledge": [],
                        "work_flow": {},
                    },
                },
            ),
            (
                "token_stat",
                {
                    "payload": {
                        "status_summary": "failed",
                        "input_tokens": 5,
                        "output_tokens": 2,
                    },
                },
            ),
        ]

        with self.assertRaises(self.query_adp.AdPError):
            self.query_adp.collect_result("test query", events)

    def test_collect_result_raises_adp_error_for_completed_empty_answer(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "",
                        "is_final": True,
                        "request_id": "test-request-003",
                        "session_id": "test-session-003",
                        "knowledge": [],
                        "work_flow": {
                            "workflow_name": "test workflow",
                            "workflow_run_id": "test-run-002",
                            "outputs": {},
                        },
                    },
                },
            ),
            (
                "token_stat",
                {
                    "payload": {
                        "input_tokens": 5,
                        "output_tokens": 0,
                    },
                },
            ),
        ]

        with self.assertRaises(self.query_adp.AdPError):
            self.query_adp.collect_result("test query", events)


if __name__ == "__main__":
    unittest.main()
