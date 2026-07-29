import importlib.util
import http.client
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
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
                        "app_key": "test-only-app-key",
                        "secret_id": "test-only-secret-id",
                        "secret_key": "test-only-secret-key",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = self.query_adp.load_config(path)

        self.assertEqual(config["app_key"], "test-only-app-key")
        self.assertEqual(config["secret_id"], "test-only-secret-id")
        self.assertEqual(config["secret_key"], "test-only-secret-key")

    def test_load_config_rejects_blank_app_key_without_leaking_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "chat_url": "https://example.test/chat/sse",
                        "app_key": " ",
                        "secret_id": "test-only-secret-id",
                        "secret_key": "test-only-secret-key",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                self.query_adp.ConfigError,
                r"^配置缺少有效字段: app_key$",
            ) as raised:
                self.query_adp.load_config(path)

        message = str(raised.exception)
        self.assertNotIn("test-only-secret-id", message)
        self.assertNotIn("test-only-secret-key", message)

    def test_load_config_rejects_missing_app_key_without_leaking_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "chat_url": "https://example.test/chat/sse",
                        "secret_id": "test-only-secret-id",
                        "secret_key": "test-only-secret-key",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                self.query_adp.ConfigError,
                r"^配置缺少有效字段: app_key$",
            ) as raised:
                self.query_adp.load_config(path)

        message = str(raised.exception)
        self.assertNotIn("test-only-secret-id", message)
        self.assertNotIn("test-only-secret-key", message)

    def test_load_config_allows_app_key_without_signing_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "chat_url": "https://example.test/chat/sse",
                        "app_key": "test-only-app-key",
                    }
                ),
                encoding="utf-8",
            )

            config = self.query_adp.load_config(path)

        self.assertEqual(config["app_key"], "test-only-app-key")
        self.assertNotIn("secret_id", config)
        self.assertNotIn("secret_key", config)

    def test_load_config_allows_each_optional_signing_field_individually(self):
        for field, value in (
            ("secret_id", "test-only-secret-id"),
            ("secret_key", "test-only-secret-key"),
        ):
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "config.json"
                    path.write_text(
                        json.dumps(
                            {
                                "chat_url": "https://example.test/chat/sse",
                                "app_key": "test-only-app-key",
                                field: value,
                            }
                        ),
                        encoding="utf-8",
                    )

                    config = self.query_adp.load_config(path)

                self.assertEqual(config["app_key"], "test-only-app-key")
                self.assertEqual(config[field], value)

    def test_load_config_rejects_chat_url_without_http_scheme_and_host(self):
        invalid_urls = (
            "ftp://example.test/chat/sse",
            "https:///missing-host",
            "example.test/chat/sse",
        )
        for chat_url in invalid_urls:
            with self.subTest(chat_url=chat_url):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "config.json"
                    path.write_text(
                        json.dumps(
                            {
                                "chat_url": chat_url,
                                "app_key_env": "TEST_ADP_KEY",
                                "app_key": "test-only-app-key",
                            }
                        ),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        self.query_adp.ConfigError, "chat_url"
                    ):
                        self.query_adp.load_config(path)

    def test_load_config_rejects_invalid_timeout_and_throttle_values(self):
        invalid_values = (
            ("timeout_seconds", 0),
            ("timeout_seconds", -1),
            ("timeout_seconds", True),
            ("timeout_seconds", "30"),
            ("streaming_throttle", 0),
            ("streaming_throttle", 101),
            ("streaming_throttle", True),
            ("streaming_throttle", 1.5),
        )
        for field, value in invalid_values:
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "config.json"
                    config = {
                        "chat_url": "https://example.test/chat/sse",
                        "app_key_env": "TEST_ADP_KEY",
                        "app_key": "test-only-app-key",
                        field: value,
                    }
                    path.write_text(
                        json.dumps(config),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        self.query_adp.ConfigError, field
                    ):
                        self.query_adp.load_config(path)

    def test_load_config_rejects_nonfinite_timeout_values(self):
        invalid_timeouts = ("1e999", "Infinity", "NaN")
        for timeout in invalid_timeouts:
            with self.subTest(timeout=timeout):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "config.json"
                    path.write_text(
                        (
                            '{"chat_url":"https://example.test/chat/sse",'
                            '"app_key_env":"TEST_ADP_KEY",'
                            '"app_key":"test-only-app-key",'
                            f'"timeout_seconds":{timeout}}}'
                        ),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        self.query_adp.ConfigError, "timeout_seconds"
                    ):
                        self.query_adp.load_config(path)

    def test_main_reports_invalid_stream_config_as_config_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "chat_url": "not-a-url",
                        "app_key_env": "TEST_ADP_KEY",
                        "app_key": "test-only-app-key",
                        "timeout_seconds": 0,
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
        self.assertEqual(output["error_type"], "config")
        self.assertEqual(stderr.getvalue(), "")

    def test_build_request_uses_app_key_and_preserves_query_identity(self):
        config = {
            "app_key": "test-only-app-key",
            "secret_id": "test-only-secret-id",
            "secret_key": "test-only-secret-key",
            "streaming_throttle": 10,
            "workflow_status": "enable",
            "search_network": "disable",
        }
        with mock.patch.dict(
            os.environ,
            {
                "ADP_APP_KEY": "poison-default-app-key",
                "TEST_LEGACY_ADP_KEY": "poison-custom-app-key",
            },
            clear=True,
        ):
            request = self.query_adp.build_request(
                config, "糖尿病的诊断标准是什么？"
            )

        self.assertEqual(request["content"], "糖尿病的诊断标准是什么？")
        self.assertEqual(request["bot_app_key"], "test-only-app-key")
        self.assertEqual(request["session_id"], request["visitor_biz_id"])
        self.assertTrue(request["request_id"])
        self.assertEqual(request["workflow_status"], "enable")
        self.assertEqual(request["search_network"], "disable")
        self.assertEqual(request["streaming_throttle"], 10)
        self.assertEqual(request["incremental"], False)
        self.assertEqual(request["visitor_labels"], [])
        self.assertEqual(request["custom_variables"], {})
        self.assertEqual(request["stream"], "enable")
        request_json = json.dumps(request)
        self.assertNotIn("secret_id", request)
        self.assertNotIn("secret_key", request)
        self.assertNotIn("test-only-secret-id", request_json)
        self.assertNotIn("test-only-secret-key", request_json)
        self.assertNotIn("poison-default-app-key", request_json)
        self.assertNotIn("poison-custom-app-key", request_json)
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

    def test_build_request_works_without_environment_when_config_has_app_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            request = self.query_adp.build_request(
                {"app_key": "test-only-app-key"}, "  test query  "
            )

        self.assertEqual(request["content"], "test query")
        self.assertEqual(request["bot_app_key"], "test-only-app-key")

    def test_build_request_rejects_blank_query(self):
        with self.assertRaisesRegex(
            self.query_adp.ConfigError, "查询内容不能为空"
        ):
            self.query_adp.build_request({}, " \n ")

    def test_build_request_without_app_key_raises_safe_config_error(self):
        config = {
            "secret_id": "test-only-secret-id",
            "secret_key": "test-only-secret-key",
            "streaming_throttle": 10,
            "workflow_status": "enable",
            "search_network": "disable",
        }
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                self.query_adp.ConfigError, "app_key"
            ) as raised:
                self.query_adp.build_request(config, "test query")

        message = str(raised.exception)
        self.assertNotIn("test-only-app-key", message)
        self.assertNotIn("test-only-secret-id", message)
        self.assertNotIn("test-only-secret-key", message)

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

    def test_read_sse_rejects_nonfinite_json_constants(self):
        constants = (b"NaN", b"Infinity", b"-Infinity")
        for constant in constants:
            with self.subTest(constant=constant):
                stream = io.BytesIO(
                    b'data: {"type": "reply", "payload": {"content": '
                    + constant
                    + b"}}\n\n"
                )

                with self.assertRaises(self.query_adp.AdPError) as raised:
                    list(self.query_adp.read_sse(stream))

                self.assertEqual(raised.exception.error_type, "sse")
                self.assertNotIn(
                    constant.decode("ascii"),
                    str(raised.exception),
                )

    def test_read_sse_discards_unterminated_event_at_eof(self):
        stream = io.BytesIO(
            b'data: {"type": "reply", "payload": '
            b'{"content": "truncated answer"}}\n'
        )

        events = list(self.query_adp.read_sse(stream))

        self.assertEqual(events, [])
        with self.assertRaises(self.query_adp.AdPError) as raised:
            self.query_adp.collect_result("query", events)
        self.assertEqual(raised.exception.error_type, "empty_result")

    def test_read_sse_stops_after_terminal_token_status(self):
        class TerminalStream:
            def __iter__(self):
                yield (
                    b'data: {"type": "reply", "payload": '
                    b'{"content": "answer"}}\n'
                )
                yield b"\n"
                yield (
                    b'data: {"type": "token_stat", "payload": '
                    b'{"status_summary": "success"}}\n'
                )
                yield b"\n"
                raise RuntimeError("stream read past terminal event")

        try:
            events = list(self.query_adp.read_sse(TerminalStream()))
        except RuntimeError:
            self.fail("read_sse consumed data after terminal token status")

        self.assertEqual(
            [event_name for event_name, _ in events],
            ["reply", "token_stat"],
        )

    def test_read_sse_rejects_more_than_one_thousand_events(self):
        event = b'data: {"type": "reply", "payload": {}}\n\n'
        stream = io.BytesIO(event * 1001)

        with self.assertRaises(self.query_adp.AdPError) as raised:
            list(self.query_adp.read_sse(stream))

        self.assertEqual(raised.exception.error_type, "sse")

    def test_read_sse_rejects_stream_larger_than_five_megabytes(self):
        content = "x" * (5 * 1024 * 1024)
        stream = io.BytesIO(
            (
                'data: {"type": "reply", "payload": {"content": "'
                + content
                + '"}}\n\n'
            ).encode("utf-8")
        )

        with self.assertRaises(self.query_adp.AdPError) as raised:
            list(self.query_adp.read_sse(stream))

        self.assertEqual(raised.exception.error_type, "sse")

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
                            "outputs": ["test output"],
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
            result["workflow"]["outputs"], ["test output"]
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

    def test_collect_result_accepts_final_bot_reply_at_clean_eof(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "partial secret answer",
                        "is_from_self": False,
                        "is_final": True,
                    },
                },
            ),
        ]

        result = self.query_adp.collect_result("test query", events)

        self.assertEqual(result["answer"], "partial secret answer")

    def test_collect_result_rejects_nonfinal_bot_reply_at_clean_eof(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "partial secret answer",
                        "is_from_self": False,
                        "is_final": False,
                    },
                },
            ),
        ]

        with self.assertRaises(self.query_adp.AdPError) as raised:
            self.query_adp.collect_result("test query", events)

        self.assertEqual(raised.exception.error_type, "sse")
        self.assertNotIn("partial secret answer", str(raised.exception))

    def test_collect_result_accepts_bot_reply_after_token_success(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "partial answer",
                        "is_from_self": False,
                        "is_final": False,
                    },
                },
            ),
            (
                "token_stat",
                {
                    "payload": {
                        "status_summary": "success",
                    },
                },
            ),
        ]

        result = self.query_adp.collect_result("test query", events)

        self.assertEqual(result["answer"], "partial answer")

    def test_collect_result_selects_latest_bot_reply_from_cloud_sequence(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "原查询",
                        "is_from_self": True,
                        "is_final": True,
                    },
                },
            ),
            ("token_stat", {"payload": {"status_summary": "processing"}}),
        ]
        for content in (
            "糖",
            "糖尿病",
            "糖尿病诊断",
            "糖尿病诊断标准",
            "糖尿病诊断标准完整",
            "糖尿病诊断标准完整答案",
        ):
            events.append(
                (
                    "reply",
                    {
                        "payload": {
                            "content": content,
                            "is_from_self": False,
                            "is_final": False,
                        },
                    },
                )
            )
        events.append(
            ("token_stat", {"payload": {"status_summary": "success"}})
        )

        result = self.query_adp.collect_result("原查询", events)

        self.assertEqual(result["answer"], "糖尿病诊断标准完整答案")

    def test_collect_result_keeps_nonempty_bot_reply_before_empty_update(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "原查询",
                        "is_from_self": True,
                        "is_final": True,
                    },
                },
            ),
            ("token_stat", {"payload": {"status_summary": "processing"}}),
            (
                "reply",
                {
                    "payload": {
                        "content": "完整 bot 答案",
                        "is_from_self": False,
                        "is_final": False,
                    },
                },
            ),
            (
                "reply",
                {
                    "payload": {
                        "content": "",
                        "is_from_self": False,
                        "is_final": False,
                    },
                },
            ),
            ("token_stat", {"payload": {"status_summary": "success"}}),
        ]

        result = self.query_adp.collect_result("原查询", events)

        self.assertEqual(result["answer"], "完整 bot 答案")

    def test_collect_result_rejects_stream_with_only_self_echo(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "原查询",
                        "is_from_self": True,
                        "is_final": True,
                    },
                },
            ),
            ("token_stat", {"payload": {"status_summary": "success"}}),
        ]

        with self.assertRaises(self.query_adp.AdPError) as raised:
            self.query_adp.collect_result("原查询", events)

        self.assertEqual(raised.exception.error_type, "empty_result")

    def test_collect_result_keeps_nonempty_bot_content_when_later_reply_is_empty(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "partial secret answer",
                        "is_from_self": False,
                        "is_final": False,
                    },
                },
            ),
            (
                "reply",
                {
                    "payload": {
                        "content": "",
                        "is_from_self": False,
                        "is_final": True,
                    },
                },
            ),
        ]

        result = self.query_adp.collect_result("test query", events)

        self.assertEqual(result["answer"], "partial secret answer")

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

    def test_collect_result_maps_only_supported_integer_reference_types(self):
        reference_types = (True, False, 1.0, [], {}, 3, 1, 2, 4)
        events = [
            ("reply", {"payload": {"content": "answer"}}),
            (
                "reference",
                {
                    "payload": {
                        "references": [
                            {"type": value} for value in reference_types
                        ]
                    }
                },
            ),
        ]

        result = self.query_adp.collect_result("query", events)

        self.assertEqual(
            [item["type"] for item in result["knowledge"]],
            [
                "unknown",
                "unknown",
                "unknown",
                "unknown",
                "unknown",
                "unknown",
                "qa",
                "document",
                "web",
            ],
        )

    def test_collect_result_uses_stable_empty_workflow_defaults(self):
        result = self.query_adp.collect_result(
            "query",
            [("reply", {"payload": {"content": "answer"}})],
        )

        self.assertEqual(
            result["workflow"],
            {"name": "", "run_id": "", "outputs": []},
        )

    def test_collect_result_normalizes_schema_drift_to_stable_types(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "answer",
                        "is_final": True,
                        "work_flow": {
                            "workflow_name": 123,
                            "workflow_run_id": {"unexpected": "object"},
                            "outputs": {"unexpected": "object"},
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
                                "doc_name": 123,
                                "name": ["unexpected"],
                                "content": {"unexpected": "object"},
                                "url": 456,
                                "confidence": True,
                            }
                        ],
                    },
                },
            ),
        ]

        result = self.query_adp.collect_result("query", events)

        self.assertEqual(
            result["knowledge"],
            [
                {
                    "type": "document",
                    "title": "",
                    "content": "",
                    "url": "",
                    "confidence": None,
                }
            ],
        )
        self.assertEqual(
            result["workflow"],
            {"name": "", "run_id": "", "outputs": []},
        )

    def test_collect_result_normalizes_ids_and_nonfinite_confidence(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "answer",
                        "request_id": 123,
                        "session_id": {"unexpected": "object"},
                    },
                },
            ),
            (
                "reference",
                {
                    "payload": {
                        "references": [
                            {"type": 2, "confidence": float("nan")},
                            {"type": 2, "confidence": float("inf")},
                            {"type": 2, "confidence": float("-inf")},
                            {"type": 2, "confidence": 0.5},
                        ],
                    },
                },
            ),
        ]

        result = self.query_adp.collect_result("query", events)

        self.assertIsNone(result["meta"]["request_id"])
        self.assertIsNone(result["meta"]["session_id"])
        self.assertEqual(
            [item["confidence"] for item in result["knowledge"]],
            [None, None, None, 0.5],
        )

    def test_collect_result_normalizes_nested_nonfinite_workflow_outputs(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "answer",
                        "work_flow": {
                            "outputs": [
                                {
                                    "scores": [
                                        float("nan"),
                                        float("inf"),
                                        0.5,
                                    ]
                                }
                            ]
                        },
                    },
                },
            ),
        ]

        result = self.query_adp.collect_result("query", events)

        self.assertEqual(
            result["workflow"]["outputs"],
            [{"scores": [None, None, 0.5]}],
        )
        json.dumps(result, ensure_ascii=False, allow_nan=False)

    def test_collect_result_rejects_non_object_payload_with_safe_message(self):
        secret_payload = (
            "answer=secret-answer "
            "url=https://secret.example "
            "key=test-only-key "
            "body=secret-request-body"
        )

        try:
            self.query_adp.collect_result(
                "query",
                [("reply", {"payload": secret_payload})],
            )
        except Exception as error:
            self.assertIsInstance(error, self.query_adp.AdPError)
            self.assertEqual(error.error_type, "sse")
            self.assertNotIn("secret", str(error))
            self.assertNotIn("test-only-key", str(error))
        else:
            self.fail("non-object payload was accepted")

    def test_query_adp_posts_json_headers_and_timeout(self):
        captured = {}
        response = io.BytesIO(
            b'data: {"type": "reply", "payload": '
            b'{"content": "answer", "request_id": "req", '
            b'"session_id": "session"}}\n\n'
        )
        response.headers = {
            "Content-Type": "text/event-stream; charset=utf-8"
        }

        def opener(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return response

        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key": "test-only-app-key",
            "secret_id": "test-only-secret-id",
            "secret_key": "test-only-secret-key",
            "timeout_seconds": 37,
        }
        with mock.patch.dict(
            os.environ,
            {
                "ADP_APP_KEY": "poison-default-app-key",
                "TEST_LEGACY_ADP_KEY": "poison-custom-app-key",
            },
            clear=True,
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
        self.assertEqual(body["bot_app_key"], "test-only-app-key")
        self.assertNotIn("secret_id", body)
        self.assertNotIn("secret_key", body)
        body_json = request.data.decode("utf-8")
        self.assertNotIn("test-only-secret-id", body_json)
        self.assertNotIn("test-only-secret-key", body_json)
        self.assertNotIn("poison-default-app-key", body_json)
        self.assertNotIn("poison-custom-app-key", body_json)
        self.assertEqual(result["answer"], "answer")

    def test_query_adp_passes_event_generator_directly_to_collector(self):
        response = io.BytesIO(
            b'data: {"type": "reply", "payload": '
            b'{"content": "answer"}}\n\n'
        )
        response.headers = {"Content-Type": "text/event-stream"}
        captured = {}

        def collect(query, events):
            captured["events"] = events
            self.assertNotIsInstance(events, list)
            return {"ok": True}

        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
            "app_key": "test-only-app-key",
            "timeout_seconds": 30,
        }
        with mock.patch.dict(
            os.environ, {"TEST_ADP_KEY": "test-only-key"}, clear=True
        ):
            with mock.patch.object(
                self.query_adp,
                "collect_result",
                side_effect=collect,
            ):
                result = self.query_adp.query_adp(
                    config,
                    "test query",
                    opener=lambda request, timeout: response,
                )

        self.assertEqual(result, {"ok": True})
        self.assertTrue(hasattr(captured["events"], "__next__"))

    def test_query_adp_enforces_monotonic_stream_deadline(self):
        response = io.BytesIO(
            b'data: {"type": "reply", "payload": '
            b'{"content": "answer"}}\n\n'
        )
        response.headers = {"Content-Type": "text/event-stream"}
        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
            "app_key": "test-only-app-key",
            "timeout_seconds": 1,
        }
        with mock.patch.dict(
            os.environ, {"TEST_ADP_KEY": "test-only-key"}, clear=True
        ):
            with mock.patch("time.monotonic", side_effect=[0, 2]):
                with self.assertRaises(self.query_adp.AdPError) as raised:
                    self.query_adp.query_adp(
                        config,
                        "test query",
                        opener=lambda request, timeout: response,
                    )

        self.assertEqual(raised.exception.error_type, "timeout")

    def test_query_adp_deadline_interrupts_blocking_line_read(self):
        class SlowResponse:
            headers = {"Content-Type": "text/event-stream"}

            def __init__(self):
                self.closed = False

            def readline(self, limit):
                time.sleep(0.2)
                return b""

            def __iter__(self):
                time.sleep(0.2)
                return iter(())

            def close(self):
                self.closed = True

        response = SlowResponse()
        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
            "app_key": "test-only-app-key",
            "timeout_seconds": 0.05,
        }
        started = time.monotonic()
        with mock.patch.dict(
            os.environ, {"TEST_ADP_KEY": "test-only-key"}, clear=True
        ):
            with self.assertRaises(self.query_adp.AdPError) as raised:
                self.query_adp.query_adp(
                    config,
                    "test query",
                    opener=lambda request, timeout: response,
                )
        elapsed = time.monotonic() - started

        self.assertEqual(raised.exception.error_type, "timeout")
        self.assertGreater(elapsed, 0.03)
        self.assertLess(elapsed, 0.15)
        self.assertTrue(response.closed)

    def test_query_adp_interrupts_socket_backed_reader_before_close(self):
        client_socket, peer_socket = socket.socketpair()
        reader = client_socket.makefile("rb")

        class SocketResponse:
            headers = {"Content-Type": "text/event-stream"}

            def __init__(self):
                self.fp = reader

            def readline(self, limit):
                return reader.readline(limit)

            def close(self):
                reader.close()
                client_socket.close()

        response = SocketResponse()
        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
            "app_key": "test-only-app-key",
            "timeout_seconds": 0.05,
        }

        def release_peer():
            try:
                peer_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            peer_socket.close()

        cleanup_timer = threading.Timer(0.22, release_peer)
        cleanup_timer.daemon = True
        cleanup_timer.start()
        started = time.monotonic()
        try:
            with mock.patch.dict(
                os.environ,
                {"TEST_ADP_KEY": "test-only-key"},
                clear=True,
            ):
                with self.assertRaises(self.query_adp.AdPError) as raised:
                    self.query_adp.query_adp(
                        config,
                        "test query",
                        opener=lambda request, timeout: response,
                    )
            elapsed = time.monotonic() - started
        finally:
            cleanup_timer.cancel()
            release_peer()
            try:
                client_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client_socket.close()

        self.assertEqual(raised.exception.error_type, "timeout")
        self.assertLess(elapsed, 0.15)

    def test_read_sse_uses_bounded_readline_for_long_unbroken_data(self):
        max_sse_bytes = self.query_adp.MAX_SSE_BYTES

        class LongLineResponse:
            def __init__(self):
                self.limits = []
                self.iterated = False
                self.sent = False

            def readline(self, limit):
                self.limits.append(limit)
                if self.sent:
                    return b""
                self.sent = True
                return b"x" * limit

            def __iter__(self):
                self.iterated = True
                yield b"x" * (max_sse_bytes + 2)

        response = LongLineResponse()

        with self.assertRaises(self.query_adp.AdPError) as raised:
            list(self.query_adp.read_sse(response))

        self.assertEqual(raised.exception.error_type, "sse")
        self.assertFalse(response.iterated)
        self.assertTrue(response.limits)
        self.assertLessEqual(
            max(response.limits),
            max_sse_bytes + 1,
        )

    def test_query_adp_rejects_non_sse_and_missing_content_types(self):
        cases = (
            ("text/html; charset=utf-8", b"<html>secret login</html>"),
            ("application/json", b'{"secret": "login"}'),
            (None, b"secret body"),
        )
        config = {
            "chat_url": "https://secret.example/login",
            "app_key_env": "TEST_ADP_KEY",
            "app_key": "test-only-app-key",
            "timeout_seconds": 30,
        }
        for content_type, response_body in cases:
            with self.subTest(content_type=content_type):
                response = io.BytesIO(response_body)
                response.headers = (
                    {"Content-Type": content_type}
                    if content_type is not None
                    else {}
                )
                with mock.patch.dict(
                    os.environ,
                    {"TEST_ADP_KEY": "test-only-key"},
                    clear=True,
                ):
                    with self.assertRaises(self.query_adp.AdPError) as raised:
                        self.query_adp.query_adp(
                            config,
                            "test query",
                            opener=lambda request, timeout: response,
                        )

                self.assertEqual(raised.exception.error_type, "sse")
                self.assertNotIn("secret", str(raised.exception))
                self.assertNotIn("test-only-key", str(raised.exception))

    def test_all_production_json_dumps_disable_nan_output(self):
        response = io.BytesIO(
            b'data: {"type": "reply", "payload": '
            b'{"content": "answer"}}\n\n'
        )
        response.headers = {"Content-Type": "text/event-stream"}
        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
            "app_key": "test-only-app-key",
        }
        real_dumps = json.dumps
        dump_options = []

        def strict_dump(*args, **kwargs):
            dump_options.append(kwargs.copy())
            return real_dumps(*args, **kwargs)

        stdout = io.StringIO()
        with mock.patch.dict(
            os.environ, {"TEST_ADP_KEY": "test-only-key"}, clear=True
        ):
            with mock.patch.object(
                self.query_adp.json,
                "dumps",
                side_effect=strict_dump,
            ):
                self.query_adp.query_adp(
                    config,
                    "query",
                    opener=lambda request, timeout: response,
                )
                with mock.patch.object(
                    self.query_adp,
                    "load_config",
                    return_value=config,
                ):
                    with mock.patch.object(
                        self.query_adp,
                        "query_adp",
                        return_value={
                            "ok": True,
                            "query": "query",
                            "answer": "answer",
                            "knowledge": [],
                            "workflow": {
                                "name": "",
                                "run_id": "",
                                "outputs": [],
                            },
                            "meta": {
                                "session_id": None,
                                "request_id": None,
                                "source": "tencent-adp",
                            },
                        },
                    ):
                        with mock.patch("sys.stdout", stdout):
                            exit_code = self.query_adp.main(
                                [
                                    "--config",
                                    "unused.json",
                                    "--query",
                                    "query",
                                ]
                            )

        self.assertEqual(exit_code, 0)
        self.assertGreaterEqual(len(dump_options), 2)
        self.assertTrue(
            all(options.get("allow_nan") is False for options in dump_options)
        )

    def test_query_adp_classifies_sse_connection_reset_as_safe_network_error(self):
        class ResettingResponse:
            headers = {"Content-Type": "text/event-stream"}

            def __iter__(self):
                raise ConnectionResetError("secret transport details")

            def close(self):
                pass

        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
            "app_key": "test-only-app-key",
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
            headers = {"Content-Type": "text/event-stream"}

            def __iter__(self):
                raise OSError("secret stream failure")

            def close(self):
                pass

        stdout = io.StringIO()
        stderr = io.StringIO()
        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
            "app_key": "test-only-app-key",
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

    def test_query_adp_classifies_incomplete_read_as_safe_network_error(self):
        class TruncatedResponse:
            headers = {"Content-Type": "text/event-stream"}

            def __iter__(self):
                raise http.client.IncompleteRead(
                    b"secret partial response",
                    100,
                )

            def close(self):
                pass

        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
            "app_key": "test-only-app-key",
        }
        with mock.patch.dict(
            os.environ, {"TEST_ADP_KEY": "test-only-key"}, clear=True
        ):
            try:
                self.query_adp.query_adp(
                    config,
                    "test query",
                    opener=lambda request, timeout: TruncatedResponse(),
                )
            except Exception as error:
                self.assertIsInstance(error, self.query_adp.AdPError)
                self.assertEqual(error.error_type, "network")
                self.assertNotIn("secret", str(error))
                self.assertNotIn("test-only-key", str(error))
            else:
                self.fail("query_adp did not report a network failure")

    def test_main_handles_http_exception_without_traceback_or_secret(self):
        class FailingResponse:
            headers = {"Content-Type": "text/event-stream"}

            def __iter__(self):
                raise http.client.HTTPException("secret protocol details")

            def close(self):
                pass

        stdout = io.StringIO()
        stderr = io.StringIO()
        config = {
            "chat_url": "https://example.test/chat/sse",
            "app_key_env": "TEST_ADP_KEY",
            "app_key": "test-only-app-key",
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
                        "app_key": "test-only-app-key",
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
        self.assertEqual(output["error_type"], "config")
        self.assertIn("TEST_ADP_KEY", output["message"])
        self.assertEqual(stderr.getvalue(), "")

    def test_main_reads_query_stdin_as_plain_text_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "must-not-exist"
            question = (
                f'"quoted" $(touch {marker}) '
                f"`touch {marker}`; touch {marker}"
            )
            captured = {}

            def fake_query(config, query, debug=False):
                captured["body"] = self.query_adp.build_request(config, query)
                return {
                    "ok": True,
                    "query": query,
                    "answer": "answer",
                    "knowledge": [],
                    "workflow": {"name": "", "run_id": "", "outputs": []},
                    "meta": {
                        "session_id": "session",
                        "request_id": "request",
                        "source": "tencent-adp",
                    },
                }

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.dict(
                os.environ, {"TEST_ADP_KEY": "test-only-key"}, clear=True
            ):
                with mock.patch.object(
                    self.query_adp,
                    "load_config",
                    return_value={
                        "chat_url": "https://example.test/chat/sse",
                        "app_key_env": "TEST_ADP_KEY",
                        "app_key": "test-only-app-key",
                    },
                ):
                    with mock.patch.object(
                        self.query_adp,
                        "query_adp",
                        side_effect=fake_query,
                    ):
                        with mock.patch("sys.stdin", io.StringIO(question)):
                            with mock.patch("sys.stdout", stdout):
                                with mock.patch("sys.stderr", stderr):
                                    try:
                                        exit_code = self.query_adp.main(
                                            [
                                                "--config",
                                                "unused.json",
                                                "--query-stdin",
                                            ]
                                        )
                                    except SystemExit as error:
                                        self.fail(
                                            "query-stdin rejected with exit "
                                            + str(error.code)
                                        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["body"]["content"], question)
        self.assertFalse(marker.exists())
        self.assertEqual(stderr.getvalue(), "")

    def test_query_stdin_processes_one_pipe_line_without_waiting_for_eof(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_config = Path(directory) / "missing.json"
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--config",
                    str(missing_config),
                    "--query-stdin",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertIsNotNone(process.stdin)
            process.stdin.write('"quoted" $() `backtick`; semicolon\n')
            process.stdin.flush()
            finished_without_eof = True
            try:
                process.wait(timeout=0.3)
            except subprocess.TimeoutExpired:
                finished_without_eof = False
            finally:
                process.stdin.close()
                if process.poll() is None:
                    process.wait(timeout=1)

            self.assertIsNotNone(process.stdout)
            stdout = process.stdout.read()
            process.stdout.close()
            self.assertIsNotNone(process.stderr)
            process.stderr.close()

        self.assertTrue(
            finished_without_eof,
            "query-stdin waited for pipe EOF after receiving one line",
        )
        output = json.loads(stdout)
        self.assertEqual(output["error_type"], "config")

    def test_main_classifies_timeout_without_leaking_exception_details(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
            self.query_adp,
            "load_config",
            return_value={
                "chat_url": "https://secret.example/path?token=secret",
                "app_key_env": "TEST_ADP_KEY",
                "app_key": "test-only-app-key",
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
