import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import tempfile
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

    def test_load_config_reads_utf8_json_and_validates_required_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "配置.json"
            path.write_text(
                json.dumps(
                    {
                        "chat_url": "https://example.test/chat/sse",
                        "app_key_env": "TEST_ADP_KEY",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = self.query_adp.load_config(path)

        self.assertEqual(config["app_key_env"], "TEST_ADP_KEY")

    def test_load_config_rejects_blank_required_field_without_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                '{"chat_url": " ", "app_key_env": "TEST_ADP_KEY"}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                self.query_adp.ConfigError, "chat_url"
            ) as raised:
                self.query_adp.load_config(path)

        self.assertNotIn("test-only-key", str(raised.exception))

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
        self.assertEqual(request["incremental"], False)
        self.assertEqual(request["visitor_labels"], [])
        self.assertEqual(request["custom_variables"], {})
        self.assertEqual(request["stream"], "enable")
        self.assertEqual(
            set(request),
            {
                "request_id",
                "session_id",
                "visitor_biz_id",
                "bot_app_key",
                "content",
                "incremental",
                "streaming_throttle",
                "visitor_labels",
                "custom_variables",
                "search_network",
                "stream",
                "workflow_status",
            },
        )

    def test_build_request_trims_query_and_uses_default_app_key_env(self):
        with mock.patch.dict(
            os.environ, {"ADP_APP_KEY": "test-only-key"}, clear=True
        ):
            request = self.query_adp.build_request({}, "  test query  ")

        self.assertEqual(request["content"], "test query")

    def test_build_request_rejects_blank_query(self):
        with self.assertRaisesRegex(
            self.query_adp.ConfigError, "查询内容不能为空"
        ):
            self.query_adp.build_request({}, " \n ")

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

    def test_read_sse_ignores_comments_and_parses_modern_multiline_event(self):
        stream = io.BytesIO(
            b": keep-alive\n"
            b'data: {"type": "reply",\n'
            b'data: "payload": {"content": "modern answer"}}\n\n'
        )

        events = list(self.query_adp.read_sse(stream))

        self.assertEqual(
            events,
            [
                (
                    "reply",
                    {
                        "type": "reply",
                        "payload": {"content": "modern answer"},
                    },
                )
            ],
        )

    def test_read_sse_rejects_malformed_json_with_safe_message(self):
        with self.assertRaisesRegex(
            self.query_adp.AdPError, "^SSE 事件不是有效 JSON$"
        ):
            list(self.query_adp.read_sse(io.BytesIO(b"data: {bad}\n\n")))

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

    def test_collect_result_uses_latest_reply_and_maps_reference_types(self):
        events = [
            ("reply", {"payload": {"content": "first"}}),
            ("reply", {"payload": {"content": "  "}}),
            (
                "reply",
                {
                    "payload": {
                        "content": "latest",
                        "request_id": "request-latest",
                        "session_id": "session-latest",
                    }
                },
            ),
            (
                "reference",
                {
                    "payload": {
                        "references": [
                            {"type": 1, "name": "qa"},
                            {"type": 2, "name": "document"},
                            {"type": 4, "name": "web"},
                        ]
                    }
                },
            ),
        ]

        result = self.query_adp.collect_result("query", events)

        self.assertEqual(result["answer"], "latest")
        self.assertEqual(
            [item["type"] for item in result["knowledge"]],
            ["qa", "document", "web"],
        )
        self.assertNotIn("bot_app_key", json.dumps(result))

    def test_collect_result_uses_stable_empty_workflow_defaults(self):
        result = self.query_adp.collect_result(
            "query",
            [("reply", {"payload": {"content": "answer"}})],
        )

        self.assertEqual(
            result["workflow"],
            {"name": "", "run_id": "", "outputs": []},
        )

    def test_query_adp_posts_json_headers_and_timeout(self):
        captured = {}
        response = io.BytesIO(
            b'data: {"type": "reply", "payload": '
            b'{"content": "answer", "request_id": "req", '
            b'"session_id": "session"}}\n\n'
        )

        def opener(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return response

        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
            "timeout_seconds": 37,
        }
        with mock.patch.dict(
            os.environ, {"TEST_ADP_KEY": "test-only-key"}, clear=True
        ):
            result = self.query_adp.query_adp(
                config, " test query ", opener=opener
            )

        request = captured["request"]
        headers = {name.lower(): value for name, value in request.header_items()}
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, config["chat_url"])
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["accept"], "text/event-stream")
        self.assertEqual(captured["timeout"], 37)
        self.assertEqual(body["content"], "test query")
        self.assertEqual(result["answer"], "answer")

    def test_query_adp_classifies_sse_connection_reset_as_safe_network_error(self):
        class ResettingResponse:
            def __iter__(self):
                raise ConnectionResetError("secret transport details")

            def close(self):
                pass

        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
        }
        with mock.patch.dict(
            os.environ, {"TEST_ADP_KEY": "test-only-key"}, clear=True
        ):
            try:
                self.query_adp.query_adp(
                    config,
                    "test query",
                    opener=lambda request, timeout: ResettingResponse(),
                )
            except Exception as error:
                self.assertIsInstance(error, self.query_adp.AdPError)
                self.assertEqual(error.error_type, "network")
                self.assertNotIn("secret", str(error))
                self.assertNotIn("test-only-key", str(error))
            else:
                self.fail("query_adp did not report a network failure")

    def test_main_handles_sse_oserror_without_traceback_or_secret(self):
        class FailingResponse:
            def __iter__(self):
                raise OSError("secret stream failure")

            def close(self):
                pass

        stdout = io.StringIO()
        stderr = io.StringIO()
        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
        }
        with mock.patch.dict(
            os.environ, {"TEST_ADP_KEY": "test-only-key"}, clear=True
        ):
            with mock.patch.object(
                self.query_adp, "load_config", return_value=config
            ):
                with mock.patch.object(
                    self.query_adp.urllib.request,
                    "urlopen",
                    return_value=FailingResponse(),
                ):
                    with mock.patch("sys.stdout", stdout):
                        with mock.patch("sys.stderr", stderr):
                            try:
                                exit_code = self.query_adp.main(
                                    [
                                        "--config",
                                        "unused.json",
                                        "--query",
                                        "query",
                                    ]
                                )
                            except Exception as error:
                                self.fail(
                                    "main leaked exception type "
                                    + type(error).__name__
                                )

        output = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(output["error_type"], "network")
        self.assertNotIn("secret", stdout.getvalue())
        self.assertNotIn("test-only-key", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_main_prints_safe_json_for_missing_app_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "chat_url": "https://example.test/chat/sse",
                        "app_key_env": "TEST_ADP_KEY",
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("sys.stdout", stdout):
                    with mock.patch("sys.stderr", stderr):
                        exit_code = self.query_adp.main(
                            ["--config", str(path), "--query", "query"]
                        )

        output = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertIs(output["ok"], False)
        self.assertEqual(output["error_type"], "auth")
        self.assertIn("TEST_ADP_KEY", output["message"])
        self.assertNotIn("test-only-key", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_main_classifies_timeout_without_leaking_exception_details(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
            self.query_adp,
            "load_config",
            return_value={
                "chat_url": "https://secret.example/path?token=secret",
                "app_key_env": "TEST_ADP_KEY",
            },
        ):
            with mock.patch.object(
                self.query_adp,
                "query_adp",
                side_effect=socket.timeout("secret timeout details"),
            ):
                with mock.patch("sys.stdout", stdout):
                    with mock.patch("sys.stderr", stderr):
                        exit_code = self.query_adp.main(
                            ["--config", "unused.json", "--query", "query"]
                        )

        output = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(output["error_type"], "timeout")
        self.assertNotIn("secret", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
