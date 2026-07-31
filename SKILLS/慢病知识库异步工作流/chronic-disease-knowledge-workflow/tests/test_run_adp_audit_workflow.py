import importlib.util
import inspect
import io
import json
import os
import pathlib
import tempfile
import unittest
import urllib.error
from unittest import mock


SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "run_adp_audit_workflow.py"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
DEFAULT_SUSPICIONS = "指标异常;信息缺失;资质不符;临床表现不足;材料不全"


def load_module():
    if not SCRIPT_PATH.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        "run_adp_audit_workflow",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


def profile_config():
    return {
        "active_profile": "cloud",
        "profiles": {
            "cloud": {
                "api_host": "https://lkeap.tencentcloudapi.com",
                "app_id": "app-test-001",
                "app_key": "APPKEY_TEST_ONLY",
                "secret_id": "AKID_TEST_ONLY",
                "secret_key": "SECRET_TEST_ONLY",
                "run_env": 1,
                "region": "ap-guangzhou",
                "service": "lke",
                "version": "2023-11-30",
            },
            "provincial_intranet": {
                "api_host": "http://192.0.2.10",
                "app_id": "app-test-002",
                "app_key": "APPKEY_INTRAnet_TEST_ONLY",
                "secret_id": "AKID_INTRAnet_TEST_ONLY",
                "secret_key": "SECRET_INTRAnet_TEST_ONLY",
                "run_env": 0,
                "region": "1",
                "service": "lke",
                "version": "2023-11-30",
            },
        },
        "poll_interval_seconds": 0.1,
        "timeout_seconds": 5,
    }


def canonical_input():
    return json.loads(
        (FIXTURES / "canonical-audit-input.json").read_text(
            encoding="utf-8"
        )
    )


def loaded_profile():
    root = profile_config()
    profile = dict(root["profiles"]["cloud"])
    profile.update(
        {
            "profile": "cloud",
            "poll_interval_seconds": root["poll_interval_seconds"],
            "timeout_seconds": root["timeout_seconds"],
        }
    )
    return profile


def successful_output():
    return json.loads(
        (FIXTURES / "successful-workflow-output.json").read_text(
            encoding="utf-8"
        )
    )


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class FakeHttpResponse:
    def __init__(self, body, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, size=-1):
        return self.body[:size]


class CloseTrackingBody(io.BytesIO):
    def __init__(self, value):
        super().__init__(value)
        self.close_called = False

    def close(self):
        self.close_called = True
        super().close()


class RecordingStdin:
    def __init__(self, value):
        self.value = value
        self.read_size = None

    def read(self, size=-1):
        self.read_size = size
        return self.value if size < 0 else self.value[:size]


class CoreContractTests(unittest.TestCase):
    def require_module(self):
        self.assertIsNotNone(
            MODULE,
            "run_adp_audit_workflow.py should exist",
        )
        return MODULE

    def write_config(self, value):
        file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        )
        with file:
            json.dump(value, file)
        return pathlib.Path(file.name)

    def test_template_has_two_empty_credential_profiles(self):
        template = json.loads(
            (SKILL_ROOT / "config" / "adp-config.template.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(template["active_profile"], "cloud")
        self.assertEqual(
            set(template["profiles"]),
            {"cloud", "provincial_intranet"},
        )
        required = {
            "api_host",
            "app_id",
            "app_key",
            "secret_id",
            "secret_key",
            "run_env",
            "region",
            "service",
            "version",
        }
        for profile in template["profiles"].values():
            self.assertEqual(set(profile), required)
            for name in (
                "api_host",
                "app_id",
                "app_key",
                "secret_id",
                "secret_key",
            ):
                self.assertEqual(profile[name], "")
        self.assertIn("poll_interval_seconds", template)
        self.assertIn("timeout_seconds", template)

    def test_load_config_selects_active_profile_and_keeps_app_key(self):
        module = self.require_module()
        path = self.write_config(profile_config())
        loaded = module.load_config(path)
        self.assertEqual(loaded["profile"], "cloud")
        self.assertEqual(loaded["app_id"], "app-test-001")
        self.assertEqual(loaded["app_key"], "APPKEY_TEST_ONLY")
        self.assertEqual(loaded["poll_interval_seconds"], 0.1)

    def test_load_config_supports_provincial_intranet_profile(self):
        module = self.require_module()
        config = profile_config()
        config["active_profile"] = "provincial_intranet"
        loaded = module.load_config(self.write_config(config))
        self.assertEqual(loaded["profile"], "provincial_intranet")
        self.assertEqual(loaded["run_env"], 0)
        self.assertEqual(loaded["api_host"], "http://192.0.2.10")

    def test_load_config_rejects_unapproved_active_profile(self):
        module = self.require_module()
        config = profile_config()
        config["active_profile"] = "unapproved_destination"
        config["profiles"]["unapproved_destination"] = dict(
            config["profiles"]["cloud"]
        )

        with self.assertRaises(module.AuditClientError) as raised:
            module.load_config(self.write_config(config))

        self.assertEqual(raised.exception.error_type, "config")

    def test_load_config_rejects_missing_app_key_without_leaking_secret(self):
        module = self.require_module()
        config = profile_config()
        secret = config["profiles"]["cloud"]["secret_key"]
        config["profiles"]["cloud"]["app_key"] = ""
        with self.assertRaises(module.AuditClientError) as raised:
            module.load_config(self.write_config(config))
        self.assertEqual(raised.exception.error_type, "config")
        self.assertNotIn(secret, str(raised.exception))

    def test_load_config_classifies_malformed_hosts_and_ports(self):
        module = self.require_module()
        invalid_hosts = (
            "http://[::1",
            "https://example.test:notaport",
            "https://example.test:70000",
        )
        for api_host in invalid_hosts:
            config = profile_config()
            config["profiles"]["cloud"]["api_host"] = api_host
            with self.subTest(api_host=api_host):
                try:
                    module.load_config(self.write_config(config))
                except module.AuditClientError as error:
                    self.assertEqual(error.error_type, "config")
                    self.assertEqual(error.code, "invalid_api_host")
                except Exception as error:
                    self.fail(
                        "malformed api_host leaked " + type(error).__name__
                    )
                else:
                    self.fail("malformed api_host was accepted")

    def test_parse_jsonish_accepts_json_bom_fence_and_python_literals(self):
        module = self.require_module()
        self.assertEqual(module.parse_jsonish('{"a":1}'), {"a": 1})
        self.assertEqual(
            module.parse_jsonish('\ufeff```json\n{"a":1}\n```'),
            {"a": 1},
        )
        self.assertEqual(
            module.parse_jsonish("{'a': True, 'b': None,}"),
            {"a": True, "b": None},
        )

    def test_parse_jsonish_never_executes_expressions(self):
        module = self.require_module()
        marker = pathlib.Path(tempfile.gettempdir()) / "adp-audit-eval-marker"
        marker.unlink(missing_ok=True)
        payload = "__import__('pathlib').Path(%r).touch()" % str(marker)
        with self.assertRaises(module.AuditClientError) as raised:
            module.parse_jsonish(payload)
        self.assertEqual(raised.exception.error_type, "input")
        self.assertFalse(marker.exists())

    def test_parse_jsonish_enforces_utf8_byte_boundary(self):
        module = self.require_module()
        self.assertTrue(
            hasattr(module, "MAX_INPUT_BYTES"),
            "client should define MAX_INPUT_BYTES",
        )
        with mock.patch.object(module, "MAX_INPUT_BYTES", 16):
            exact = '"' + ("a" * 14) + '"'
            self.assertEqual(module.parse_jsonish(exact), "a" * 14)
            over = '"' + ("a" * 15) + '"'
            with self.assertRaises(module.AuditClientError) as raised:
                module.parse_jsonish(over)
        self.assertEqual(raised.exception.error_type, "input")
        self.assertEqual(raised.exception.code, "input_too_large")
        self.assertNotIn("aaa", str(raised.exception))

    def test_normalize_unwraps_one_certification_candidate(self):
        module = self.require_module()
        value = canonical_input()
        value["certification_list"] = [value["certification_list"]]
        normalized = module.normalize_audit_input(value)
        self.assertIsInstance(normalized["certification_list"], dict)
        self.assertEqual(normalized["auditId"], "audit-test-001")

    def test_normalize_rejects_multiple_certification_candidates(self):
        module = self.require_module()
        value = canonical_input()
        candidate = value["certification_list"]
        value["certification_list"] = [candidate, candidate]
        with self.assertRaises(module.AuditClientError) as raised:
            module.normalize_audit_input(value)
        self.assertEqual(raised.exception.error_type, "input")
        self.assertEqual(
            raised.exception.code,
            "multiple_certification_candidates",
        )

    def test_normalize_requires_nonempty_disease_meta(self):
        module = self.require_module()
        for field in ("chronicDiseaseName", "chronicDiseaseCode"):
            with self.subTest(field=field):
                value = canonical_input()
                value["certification_list"]["meta"][field] = "  "
                with self.assertRaises(module.AuditClientError) as raised:
                    module.normalize_audit_input(value)
                self.assertEqual(raised.exception.error_type, "input")

    def test_normalize_generates_missing_ids_and_default_suspicions(self):
        module = self.require_module()
        value = canonical_input()
        del value["auditId"]
        del value["material_list"][0]["materialId"]
        del value["suspicion_type_options"]
        ids = iter(["audit-generated", "material-generated"])
        normalized = module.normalize_audit_input(
            value,
            uuid_factory=lambda: next(ids),
        )
        self.assertEqual(normalized["auditId"], "audit-generated")
        self.assertEqual(
            normalized["material_list"][0]["materialId"],
            "material-generated",
        )
        self.assertEqual(
            normalized["suspicion_type_options"],
            DEFAULT_SUSPICIONS,
        )

    def test_normalize_generates_audit_id_for_empty_string(self):
        module = self.require_module()
        value = canonical_input()
        value["auditId"] = ""

        normalized = module.normalize_audit_input(
            value,
            uuid_factory=lambda: "audit-generated",
        )

        self.assertEqual(normalized["auditId"], "audit-generated")

    def test_normalize_generates_material_id_for_empty_string(self):
        module = self.require_module()
        value = canonical_input()
        value["material_list"][0]["materialId"] = ""

        normalized = module.normalize_audit_input(
            value,
            uuid_factory=lambda: "material-generated",
        )

        self.assertEqual(
            normalized["material_list"][0]["materialId"],
            "material-generated",
        )

    def test_normalize_uses_default_suspicions_for_empty_string(self):
        module = self.require_module()
        value = canonical_input()
        value["suspicion_type_options"] = ""

        normalized = module.normalize_audit_input(value)

        self.assertEqual(
            normalized["suspicion_type_options"],
            DEFAULT_SUSPICIONS,
        )

    def test_normalize_rejects_whitespace_only_optional_values(self):
        module = self.require_module()
        for field_path in (
            ("auditId",),
            ("material_list", 0, "materialId"),
            ("suspicion_type_options",),
        ):
            with self.subTest(field_path=field_path):
                value = canonical_input()
                target = value
                for component in field_path[:-1]:
                    target = target[component]
                target[field_path[-1]] = "  "

                with self.assertRaises(module.AuditClientError) as raised:
                    module.normalize_audit_input(value)

                self.assertEqual(raised.exception.error_type, "input")

    def test_normalize_preserves_existing_ids(self):
        module = self.require_module()
        normalized = module.normalize_audit_input(
            canonical_input(),
            uuid_factory=lambda: self.fail("must not generate UUID"),
        )
        self.assertEqual(normalized["auditId"], "audit-test-001")
        self.assertEqual(
            normalized["material_list"][0]["materialId"],
            "material-test-001",
        )

    def test_normalize_rejects_bad_materials_and_path_traversal(self):
        module = self.require_module()
        bad_values = []
        empty = canonical_input()
        empty["material_list"] = []
        bad_values.append(empty)
        blank_name = canonical_input()
        blank_name["material_list"][0]["materialName"] = ""
        bad_values.append(blank_name)
        wrong_item = canonical_input()
        wrong_item["material_list"] = ["not-object"]
        bad_values.append(wrong_item)
        traversal = canonical_input()
        traversal["auditId"] = "../../escape"
        bad_values.append(traversal)
        for audit_id in (
            "audit\nlinebreak",
            "\naudit",
            "audit\n",
            "\taudit\t",
        ):
            control_character = canonical_input()
            control_character["auditId"] = audit_id
            bad_values.append(control_character)
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaises(module.AuditClientError) as raised:
                    module.normalize_audit_input(value)
                self.assertEqual(raised.exception.error_type, "input")

    def test_tc3_signature_matches_fixed_vector(self):
        module = self.require_module()
        config = {
            "api_host": "http://10.80.38.161",
            "secret_id": "AKIDEXAMPLE",
            "secret_key": "SECRETEXAMPLE",
            "region": "1",
            "service": "lke",
            "version": "2023-11-30",
        }
        body = (
            b'{"AppBizId":"2082072305231359424","Query":"test",'
            b'"RunEnv":1,"VisitorId":"visitor-1"}'
        )
        headers = module.build_signed_headers(
            config,
            "CreateWorkflowRun",
            body,
            timestamp=1700000000,
        )
        self.assertIn(
            "Signature="
            "bfbf0ed5100b0f135a48b11e7f44ada7c4e583b70479c2741c63b81bc96d3fd0",
            headers["Authorization"],
        )
        self.assertEqual(headers["X-TC-Action"], "CreateWorkflowRun")


class WorkflowContractTests(unittest.TestCase):
    def require_module(self):
        self.assertIsNotNone(MODULE)
        for name in (
            "MAX_RESPONSE_BYTES",
            "build_create_payload",
            "post_action",
            "run_audit_workflow",
        ):
            self.assertTrue(
                hasattr(MODULE, name),
                "run_adp_audit_workflow should expose " + name,
            )
        return MODULE

    def test_build_create_payload_uses_exact_whitelist_and_four_variables(self):
        module = self.require_module()
        normalized = module.normalize_audit_input(canonical_input())
        payload = module.build_create_payload(
            loaded_profile(),
            normalized,
            visitor_id="visitor-test-001",
        )
        self.assertEqual(
            set(payload),
            {"AppBizId", "RunEnv", "Query", "CustomVariables", "VisitorId"},
        )
        self.assertEqual(payload["Query"], "执行智能审核")
        self.assertEqual(payload["VisitorId"], "visitor-test-001")
        self.assertEqual(len(payload["CustomVariables"]), 4)
        variables = {
            item["Name"]: item["Value"]
            for item in payload["CustomVariables"]
        }
        self.assertEqual(
            set(variables),
            {
                "certification_list",
                "material_list",
                "auditId",
                "suspicion_type_options",
            },
        )
        self.assertEqual(
            json.loads(variables["certification_list"]),
            normalized["certification_list"],
        )
        self.assertEqual(
            json.loads(variables["material_list"]),
            normalized["material_list"],
        )
        self.assertNotIn(" ", variables["material_list"])
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(loaded_profile()["app_key"], serialized)
        self.assertNotIn(loaded_profile()["secret_key"], serialized)

    def test_build_create_payload_rejects_nan(self):
        module = self.require_module()
        normalized = module.normalize_audit_input(canonical_input())
        normalized["certification_list"]["score"] = float("nan")
        with self.assertRaises(module.AuditClientError) as raised:
            module.build_create_payload(
                loaded_profile(),
                normalized,
                visitor_id="visitor-test-001",
            )
        self.assertEqual(raised.exception.error_type, "input")

    def test_post_action_sends_compact_json_without_app_key(self):
        module = self.require_module()
        response = FakeHttpResponse(b'{"Response":{"RequestId":"req-test"}}')
        with mock.patch.object(
            module.urllib.request,
            "urlopen",
            return_value=response,
        ) as urlopen:
            data = module.post_action(
                loaded_profile(),
                "DescribeWorkflowRun",
                {"AppBizId": "app-test-001", "WorkflowRunId": "wfr-test"},
            )
        request = urlopen.call_args.args[0]
        self.assertEqual(
            json.loads(request.data),
            {"AppBizId": "app-test-001", "WorkflowRunId": "wfr-test"},
        )
        self.assertNotIn(b"APPKEY_TEST_ONLY", request.data)
        self.assertEqual(data["Response"]["RequestId"], "req-test")

    def test_post_action_enforces_response_size_limit(self):
        module = self.require_module()
        body = b"x" * (module.MAX_RESPONSE_BYTES + 1)
        with mock.patch.object(
            module.urllib.request,
            "urlopen",
            return_value=FakeHttpResponse(body),
        ):
            with self.assertRaises(module.AuditClientError) as raised:
                module.post_action(loaded_profile(), "DescribeWorkflowRun", {})
        self.assertEqual(raised.exception.error_type, "response")

    def test_post_action_classifies_http_auth_without_leaking_body(self):
        module = self.require_module()
        secret_body = b"server diagnostic SECRET_TEST_ONLY"
        error = urllib.error.HTTPError(
            "https://example.test",
            403,
            "forbidden",
            {"X-TC-RequestId": "req-auth-http"},
            io.BytesIO(secret_body),
        )
        with mock.patch.object(
            module.urllib.request,
            "urlopen",
            side_effect=error,
        ):
            with self.assertRaises(module.AuditClientError) as raised:
                module.post_action(loaded_profile(), "CreateWorkflowRun", {})
        self.assertEqual(raised.exception.error_type, "auth")
        self.assertEqual(raised.exception.request_id, "req-auth-http")
        self.assertNotIn("SECRET_TEST_ONLY", str(raised.exception))

    def test_post_action_closes_http_errors_and_drops_response_context(self):
        module = self.require_module()
        cases = ((403, "auth"), (500, "http"))
        for status, expected_type in cases:
            body = CloseTrackingBody(b"synthetic server error")
            http_error = urllib.error.HTTPError(
                "https://example.test",
                status,
                "synthetic failure",
                {"X-TC-RequestId": "req-http-close"},
                body,
            )
            with self.subTest(status=status):
                with mock.patch.object(
                    module.urllib.request,
                    "urlopen",
                    side_effect=http_error,
                ):
                    with self.assertRaises(module.AuditClientError) as raised:
                        module.post_action(
                            loaded_profile(),
                            "CreateWorkflowRun",
                            {},
                        )
                self.assertEqual(raised.exception.error_type, expected_type)
                self.assertTrue(body.close_called)
                self.assertIsNone(raised.exception.__context__)

    def test_post_action_uses_explicit_remaining_timeout(self):
        module = self.require_module()
        self.assertIn(
            "request_timeout_seconds",
            inspect.signature(module.post_action).parameters,
        )
        response = FakeHttpResponse(b'{"Response":{"RequestId":"req-test"}}')
        with mock.patch.object(
            module.urllib.request,
            "urlopen",
            return_value=response,
        ) as urlopen:
            module.post_action(
                loaded_profile(),
                "DescribeWorkflowRun",
                {"AppBizId": "app-test-001", "WorkflowRunId": "wfr-test"},
                request_timeout_seconds=2.5,
            )
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 2.5)

    def test_actions_outside_workflow_allowlist_are_rejected_before_network(self):
        module = self.require_module()
        with self.assertRaises(module.AuditClientError) as signed:
            module.build_signed_headers(
                loaded_profile(),
                "DeleteKnowledgeBase",
                b"{}",
                timestamp=1700000000,
            )
        self.assertEqual(signed.exception.error_type, "config")
        self.assertEqual(signed.exception.code, "unsupported_action")

        with mock.patch.object(module.urllib.request, "urlopen") as urlopen:
            with self.assertRaises(module.AuditClientError) as posted:
                module.post_action(
                    loaded_profile(),
                    "DeleteKnowledgeBase",
                    {},
                )
        self.assertEqual(posted.exception.error_type, "config")
        self.assertEqual(posted.exception.code, "unsupported_action")
        urlopen.assert_not_called()

    def test_workflow_creates_polls_and_builds_stable_result(self):
        module = self.require_module()
        calls = []
        responses = [
            {
                "Response": {
                    "WorkflowRunId": "wfr-test-001",
                    "RequestId": "req-create-001",
                }
            },
            {
                "Response": {
                    "WorkflowRun": {"State": 1, "Output": ""},
                    "RequestId": "req-pending-001",
                }
            },
            {
                "Response": {
                    "WorkflowRun": {
                        "State": 2,
                        "Output": successful_output(),
                    },
                    "RequestId": "req-describe-001",
                }
            },
        ]

        def fake_post(config, action, payload):
            calls.append((action, payload))
            return responses.pop(0)

        clock = FakeClock()
        result = module.run_audit_workflow(
            loaded_profile(),
            canonical_input(),
            post=fake_post,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            uuid_factory=lambda: "visitor-test-001",
            now_factory=lambda: "2026-01-02T03:04:05Z",
        )
        expected = json.loads(
            (FIXTURES / "valid-audit-result.json").read_text(encoding="utf-8")
        )
        self.assertEqual(result, expected)
        self.assertEqual([call[0] for call in calls], [
            "CreateWorkflowRun",
            "DescribeWorkflowRun",
            "DescribeWorkflowRun",
        ])
        self.assertEqual(
            set(calls[1][1]),
            {"AppBizId", "WorkflowRunId"},
        )
        self.assertNotIn("material_list", result)

    def test_workflow_rejects_success_response_without_request_id(self):
        module = self.require_module()
        response_sequences = (
            [
                {"Response": {"WorkflowRunId": "wfr-test"}},
                {
                    "Response": {
                        "WorkflowRun": {"State": 2, "Output": successful_output()},
                        "RequestId": "req-describe",
                    }
                },
            ],
            [
                {
                    "Response": {
                        "WorkflowRunId": "wfr-test",
                        "RequestId": "req-create",
                    }
                },
                {"Response": {"WorkflowRun": {"State": 2, "Output": successful_output()}}},
            ],
        )

        for responses in response_sequences:
            with self.subTest(responses=responses):
                queued = list(responses)
                with self.assertRaises(module.AuditClientError) as raised:
                    module.run_audit_workflow(
                        loaded_profile(),
                        canonical_input(),
                        post=lambda config, action, payload: queued.pop(0),
                    )
                self.assertEqual(raised.exception.error_type, "response")
                self.assertIsNone(raised.exception.request_id)

    def test_workflow_accepts_string_output_and_stringified_rule_results(self):
        module = self.require_module()
        output = successful_output()
        output["ruleResults"] = [
            json.dumps(output["ruleResults"][0], ensure_ascii=False),
        ]
        responses = [
            {"Response": {"WorkflowRunId": "wfr-test", "RequestId": "req-1"}},
            {
                "Response": {
                    "WorkflowRun": {
                        "State": 2,
                        "Output": json.dumps(output, ensure_ascii=False),
                    },
                    "RequestId": "req-2",
                }
            },
        ]
        result = module.run_audit_workflow(
            loaded_profile(),
            canonical_input(),
            post=lambda config, action, payload: responses.pop(0),
            uuid_factory=lambda: "visitor-test",
            now_factory=lambda: "2026-01-02T03:04:05Z",
        )
        self.assertEqual(result["ruleResults"][0]["ruleCode"], "SYN-R-001")

    def test_workflow_preserves_final_result_and_advice_whitespace(self):
        module = self.require_module()
        output = successful_output()
        output["finalResult"] = "  manual_review  "
        output["advice"] = "  合成测试建议：请核对材料完整性  "
        responses = [
            {"Response": {"WorkflowRunId": "wfr-test", "RequestId": "req-1"}},
            {
                "Response": {
                    "WorkflowRun": {"State": 2, "Output": output},
                    "RequestId": "req-2",
                }
            },
        ]

        result = module.run_audit_workflow(
            loaded_profile(),
            canonical_input(),
            post=lambda config, action, payload: responses.pop(0),
        )

        self.assertEqual(result["audit"]["finalResult"], output["finalResult"])
        self.assertEqual(result["audit"]["advice"], output["advice"])

    def test_workflow_accepts_rule_results_as_json_array_string(self):
        module = self.require_module()
        output = successful_output()
        output["ruleResults"] = json.dumps(
            output["ruleResults"],
            ensure_ascii=False,
        )
        responses = [
            {"Response": {"WorkflowRunId": "wfr-test", "RequestId": "req-1"}},
            {
                "Response": {
                    "WorkflowRun": {"State": 2, "Output": output},
                    "RequestId": "req-2",
                }
            },
        ]
        result = module.run_audit_workflow(
            loaded_profile(),
            canonical_input(),
            post=lambda config, action, payload: responses.pop(0),
        )
        self.assertIsInstance(result["ruleResults"], list)
        self.assertEqual(result["ruleResults"][0]["ruleResult"], "通过")

    def test_workflow_normalizes_missing_or_null_suspicion_list_to_empty_array(self):
        module = self.require_module()
        missing_rules = module._normalize_rule_results(
            successful_output()["ruleResults"],
            "req-normalize",
        )
        self.assertEqual(missing_rules[0]["suspicionList"], [])

        null_output = successful_output()["ruleResults"]
        null_output[0]["suspicionList"] = None
        null_rules = module._normalize_rule_results(null_output, "req-normalize")
        self.assertEqual(null_rules[0]["suspicionList"], [])

    def test_workflow_preserves_false_keyword_found_flag(self):
        module = self.require_module()
        rules = successful_output()["ruleResults"]
        rules[0]["ruleKeywordGuide"][0]["found"] = False

        normalized = module._normalize_rule_results(rules, "req-guide")

        guide = normalized[0]["ruleKeywordGuide"][0]
        self.assertEqual(guide["keywordCode"], "SYNTHETIC-EVIDENCE-KEYWORD")
        self.assertIs(guide["found"], False)

    def test_workflow_strips_uncontracted_rule_payload_fields(self):
        module = self.require_module()
        output = successful_output()
        rule = output["ruleResults"][0]
        rule["unexpectedRawPayload"] = "must-not-reach-result"
        guide = rule["ruleKeywordGuide"][0]
        guide["unexpectedGuidePayload"] = "must-not-reach-result"
        evidence = guide["results"][0]
        evidence["unexpectedEvidencePayload"] = "must-not-reach-result"
        rule["suspicionList"] = [
            {
                "suspicionType": "合成疑点",
                "detail": "合成疑点详情",
                "unexpectedSuspicionPayload": "must-not-reach-result",
                "sources": [
                    {
                        "materialId": "material-test-001",
                        "materialName": "合成测试材料",
                        "unexpectedSourcePayload": "must-not-reach-result",
                    }
                ],
            }
        ]
        responses = [
            {"Response": {"WorkflowRunId": "wfr-test", "RequestId": "req-1"}},
            {
                "Response": {
                    "WorkflowRun": {"State": 2, "Output": output},
                    "RequestId": "req-2",
                }
            },
        ]

        result = module.run_audit_workflow(
            loaded_profile(),
            canonical_input(),
            post=lambda config, action, payload: responses.pop(0),
        )

        normalized_rule = result["ruleResults"][0]
        self.assertEqual(
            set(normalized_rule),
            {
                "ruleCode",
                "ruleContent",
                "ruleResult",
                "reasoningContent",
                "ruleKeywordGuide",
                "suspicionList",
            },
        )
        self.assertEqual(
            set(normalized_rule["ruleKeywordGuide"][0]),
            {"keywordCode", "found", "results"},
        )
        self.assertEqual(
            set(normalized_rule["ruleKeywordGuide"][0]["results"][0]),
            {
                "materialId",
                "materialName",
                "materialSource",
                "rawText",
                "value",
            },
        )
        suspicion = normalized_rule["suspicionList"][0]
        self.assertEqual(
            set(suspicion),
            {"suspicionType", "detail", "sources"},
        )
        self.assertEqual(
            suspicion["sources"],
            [{"materialId": "material-test-001", "materialName": "合成测试材料"}],
        )
        self.assertNotIn("must-not-reach-result", json.dumps(result, ensure_ascii=False))

    def test_workflow_rejects_missing_or_wrongly_typed_rule_contract_fields(self):
        module = self.require_module()
        invalid_rules = []

        missing_rule_code = successful_output()["ruleResults"]
        missing_rule_code[0].pop("ruleCode")
        invalid_rules.append(missing_rule_code)

        wrong_guide_list = successful_output()["ruleResults"]
        wrong_guide_list[0]["ruleKeywordGuide"] = {}
        invalid_rules.append(wrong_guide_list)

        wrong_keyword_code = successful_output()["ruleResults"]
        wrong_keyword_code[0]["ruleKeywordGuide"][0]["keywordCode"] = 123
        invalid_rules.append(wrong_keyword_code)

        missing_found = successful_output()["ruleResults"]
        missing_found[0]["ruleKeywordGuide"][0].pop("found")
        invalid_rules.append(missing_found)

        missing_evidence_field = successful_output()["ruleResults"]
        missing_evidence_field[0]["ruleKeywordGuide"][0]["results"][0].pop(
            "rawText"
        )
        invalid_rules.append(missing_evidence_field)

        wrong_evidence_value = successful_output()["ruleResults"]
        wrong_evidence_value[0]["ruleKeywordGuide"][0]["results"][0][
            "value"
        ] = 7
        invalid_rules.append(wrong_evidence_value)

        secret = "PRIVATE-WORKFLOW-VALUE-MUST-NOT-LEAK"
        for rules in invalid_rules:
            rules[0]["privateUnexpectedValue"] = secret
            with self.subTest(rules=rules):
                with self.assertRaises(module.AuditClientError) as raised:
                    module._normalize_rule_results(rules, "req-contract")
                self.assertEqual(raised.exception.error_type, "response")
                self.assertEqual(raised.exception.request_id, "req-contract")
                self.assertNotIn(secret, str(raised.exception))

    def test_workflow_validates_suspicion_and_source_union_without_coercion(self):
        module = self.require_module()
        base = successful_output()["ruleResults"][0]

        valid_string_source = json.loads(json.dumps(base))
        valid_string_source["suspicionList"] = [
            {
                "suspicionType": "合成疑点",
                "detail": "合成疑点详情",
                "sources": ["material-test-001"],
            }
        ]
        normalized = module._normalize_rule_results(
            [valid_string_source],
            "req-source",
        )
        self.assertEqual(
            normalized[0]["suspicionList"][0]["sources"],
            ["material-test-001"],
        )

        valid_partial_object = json.loads(json.dumps(base))
        valid_partial_object["suspicionList"] = [
            {
                "suspicionType": "合成疑点",
                "detail": "合成疑点详情",
                "sources": [
                    {
                        "materialId": "material-test-001",
                        "extension": "不应保留的字符串扩展字段",
                    }
                ],
            }
        ]
        normalized_partial = module._normalize_rule_results(
            [valid_partial_object],
            "req-source",
        )
        self.assertEqual(
            normalized_partial[0]["suspicionList"][0]["sources"],
            [{"materialId": "material-test-001"}],
        )

        invalid_suspicions = (
            [None],
            [{"suspicionType": 1, "detail": "合成疑点详情"}],
            [{"suspicionType": "合成疑点", "detail": "合成疑点详情", "sources": {}}],
            [{"suspicionType": "合成疑点", "detail": "合成疑点详情", "sources": [{}]}],
            [{"suspicionType": "合成疑点", "detail": "合成疑点详情", "sources": [{"materialName": 3}]}],
            [{"suspicionType": "合成疑点", "detail": "合成疑点详情", "sources": [{"materialId": "material-test-001", "unexpected": 1}]}],
            [{"suspicionType": "合成疑点", "detail": "合成疑点详情", "sources": [{"materialId": "material-test-001", "unexpected": True}]}],
            [{"suspicionType": "合成疑点", "detail": "合成疑点详情", "sources": [{"materialId": "material-test-001", "unexpected": {"nested": "object"}}]}],
        )
        for suspicion_list in invalid_suspicions:
            rule = json.loads(json.dumps(base))
            rule["suspicionList"] = suspicion_list
            with self.subTest(suspicion_list=suspicion_list):
                with self.assertRaises(module.AuditClientError):
                    module._normalize_rule_results([rule], "req-source")

    def test_workflow_rejects_plain_or_single_object_rule_results_strings(self):
        module = self.require_module()
        bad_rule_results = [
            "合成测试普通文本规则",
            json.dumps(
                {"ruleCode": "SYN-R-001", "ruleResult": "通过"},
                ensure_ascii=False,
            ),
            ["合成测试普通文本规则"],
        ]
        for rule_results in bad_rule_results:
            output = successful_output()
            output["ruleResults"] = rule_results
            responses = [
                {"Response": {"WorkflowRunId": "wfr-test", "RequestId": "req-1"}},
                {
                    "Response": {
                        "WorkflowRun": {"State": 2, "Output": output},
                        "RequestId": "req-2",
                    }
                },
            ]
            with self.subTest(rule_results=rule_results):
                with self.assertRaises(module.AuditClientError) as raised:
                    module.run_audit_workflow(
                        loaded_profile(),
                        canonical_input(),
                        post=lambda config, action, payload: responses.pop(0),
                    )
                self.assertEqual(raised.exception.error_type, "response")

    def test_workflow_times_out_when_create_call_crosses_deadline(self):
        module = self.require_module()
        config = loaded_profile()
        config["timeout_seconds"] = 5
        clock = FakeClock()
        observed_timeouts = []

        def fake_post(
            config,
            action,
            payload,
            request_timeout_seconds=None,
        ):
            observed_timeouts.append(request_timeout_seconds)
            clock.value += 10
            return {"malformed": "must not be processed after deadline"}

        with self.assertRaises(module.AuditClientError) as raised:
            module.run_audit_workflow(
                config,
                canonical_input(),
                post=fake_post,
                monotonic=clock.monotonic,
            )
        self.assertEqual(raised.exception.error_type, "timeout")
        self.assertEqual(observed_timeouts, [5])

    def test_workflow_times_out_when_describe_call_crosses_deadline(self):
        module = self.require_module()
        config = loaded_profile()
        config["timeout_seconds"] = 5
        clock = FakeClock()
        observed_timeouts = []

        def fake_post(
            config,
            action,
            payload,
            request_timeout_seconds=None,
        ):
            observed_timeouts.append(request_timeout_seconds)
            if action == "CreateWorkflowRun":
                return {
                    "Response": {
                        "WorkflowRunId": "wfr-test",
                        "RequestId": "req-create",
                    }
                }
            clock.value += 10
            return {
                "Response": {
                    "WorkflowRun": {"State": 2, "Output": successful_output()},
                    "RequestId": "req-describe",
                }
            }

        with self.assertRaises(module.AuditClientError) as raised:
            module.run_audit_workflow(
                config,
                canonical_input(),
                post=fake_post,
                monotonic=clock.monotonic,
            )
        self.assertEqual(raised.exception.error_type, "timeout")
        self.assertEqual(observed_timeouts, [5, 5])

    def test_workflow_times_out_when_result_normalization_crosses_deadline(self):
        module = self.require_module()
        config = loaded_profile()
        config["timeout_seconds"] = 5
        clock = FakeClock()
        responses = [
            {"Response": {"WorkflowRunId": "wfr-test", "RequestId": "req-1"}},
            {
                "Response": {
                    "WorkflowRun": {
                        "State": 2,
                        "Output": successful_output(),
                    },
                    "RequestId": "req-2",
                }
            },
        ]

        def slow_now():
            clock.value += 10
            return "2026-01-02T03:04:05Z"

        with self.assertRaises(module.AuditClientError) as raised:
            module.run_audit_workflow(
                config,
                canonical_input(),
                post=lambda config, action, payload: responses.pop(0),
                monotonic=clock.monotonic,
                now_factory=slow_now,
            )
        self.assertEqual(raised.exception.error_type, "timeout")

    def test_workflow_rejects_missing_fields_and_mismatched_audit_id(self):
        module = self.require_module()
        bad_outputs = []
        for field in ("advice", "auditId", "ruleResults", "finalResult"):
            output = successful_output()
            del output[field]
            bad_outputs.append(output)
        mismatch = successful_output()
        mismatch["auditId"] = "different-audit"
        bad_outputs.append(mismatch)
        for output in bad_outputs:
            responses = [
                {"Response": {"WorkflowRunId": "wfr", "RequestId": "req-1"}},
                {
                    "Response": {
                        "WorkflowRun": {"State": 2, "Output": output},
                        "RequestId": "req-2",
                    }
                },
            ]
            with self.subTest(output=output):
                with self.assertRaises(module.AuditClientError) as raised:
                    module.run_audit_workflow(
                        loaded_profile(),
                        canonical_input(),
                        post=lambda config, action, payload: responses.pop(0),
                    )
                self.assertEqual(raised.exception.error_type, "response")


class CliContractTests(unittest.TestCase):
    def require_module(self):
        self.assertIsNotNone(MODULE)
        for name in ("main", "print_error", "write_result_atomic"):
            self.assertTrue(
                hasattr(MODULE, name),
                "run_adp_audit_workflow should expose " + name,
            )
        return MODULE

    def write_config(self, directory):
        path = pathlib.Path(directory) / "config.json"
        path.write_text(
            json.dumps(profile_config(), ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def test_atomic_writer_uses_replace_and_expected_filename(self):
        module = self.require_module()
        result = json.loads(
            (FIXTURES / "valid-audit-result.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            real_replace = os.replace
            replacements = []

            def recording_replace(source, destination):
                replacements.append((source, destination))
                return real_replace(source, destination)

            with mock.patch.object(
                module.os,
                "replace",
                side_effect=recording_replace,
            ):
                output_path = module.write_result_atomic(result, directory)
            self.assertEqual(
                output_path.name,
                "audit-test-001-智能审核结果.json",
            )
            self.assertEqual(len(replacements), 1)
            self.assertEqual(pathlib.Path(replacements[0][1]), output_path)
            self.assertFalse(pathlib.Path(replacements[0][0]).exists())
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                result,
            )

    def test_cli_reads_input_file_writes_result_and_prints_safe_envelope(self):
        module = self.require_module()
        result = json.loads(
            (FIXTURES / "valid-audit-result.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.write_config(directory)
            output_dir = pathlib.Path(directory) / "outputs"
            stdout = io.StringIO()
            with mock.patch.object(
                module,
                "run_audit_workflow",
                return_value=result,
            ) as run:
                exit_code = module.main(
                    [
                        "--config",
                        str(config_path),
                        "--input-file",
                        str(FIXTURES / "canonical-audit-input.json"),
                        "--output-dir",
                        str(output_dir),
                    ],
                    stdin=io.StringIO("unused"),
                    stdout=stdout,
                )
            self.assertEqual(exit_code, 0)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(
                envelope,
                {
                    "ok": True,
                    "auditId": "audit-test-001",
                    "resultPath": str(
                        (
                            output_dir
                            / "audit-test-001-智能审核结果.json"
                        ).resolve()
                    ),
                },
            )
            self.assertNotIn("仅用于自动化测试的虚构内容", stdout.getvalue())
            self.assertEqual(run.call_args.args[1]["auditId"], "audit-test-001")
            self.assertTrue(pathlib.Path(envelope["resultPath"]).exists())

    def test_cli_reads_jsonish_from_stdin(self):
        module = self.require_module()
        result = json.loads(
            (FIXTURES / "valid-audit-result.json").read_text(encoding="utf-8")
        )
        stdin_value = "```json\n" + json.dumps(canonical_input(), ensure_ascii=False) + "\n```"
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.write_config(directory)
            stdout = io.StringIO()
            with mock.patch.object(
                module,
                "run_audit_workflow",
                return_value=result,
            ) as run:
                exit_code = module.main(
                    [
                        "--config",
                        str(config_path),
                        "--input-stdin",
                        "--output-dir",
                        directory,
                    ],
                    stdin=io.StringIO(stdin_value),
                    stdout=stdout,
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(run.call_args.args[1]["auditId"], "audit-test-001")
            self.assertTrue(json.loads(stdout.getvalue())["ok"])

    def test_input_reader_enforces_file_size_before_reading(self):
        module = self.require_module()
        self.assertTrue(
            hasattr(module, "MAX_INPUT_BYTES"),
            "client should define MAX_INPUT_BYTES",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "input.json"
            with mock.patch.object(module, "MAX_INPUT_BYTES", 16):
                exact = '"' + ("a" * 14) + '"'
                path.write_text(exact, encoding="utf-8")
                args = module.argparse.Namespace(
                    input_stdin=False,
                    input_file=str(path),
                )
                self.assertEqual(module._read_input_text(args, None), exact)

                path.write_text('"' + ("a" * 15) + '"', encoding="utf-8")
                with mock.patch.object(
                    module.pathlib.Path,
                    "read_text",
                    side_effect=AssertionError("oversize file was read"),
                ) as read_text:
                    try:
                        module._read_input_text(args, None)
                    except module.AuditClientError as error:
                        self.assertEqual(error.error_type, "input")
                        self.assertEqual(error.code, "input_too_large")
                    except AssertionError as error:
                        self.fail(str(error))
                    else:
                        self.fail("oversize file was accepted")
                    read_text.assert_not_called()

    def test_input_reader_bounds_stdin_read_and_rejects_oversize(self):
        module = self.require_module()
        self.assertTrue(
            hasattr(module, "MAX_INPUT_BYTES"),
            "client should define MAX_INPUT_BYTES",
        )
        args = module.argparse.Namespace(input_stdin=True, input_file=None)
        with mock.patch.object(module, "MAX_INPUT_BYTES", 16):
            exact_stdin = RecordingStdin('"' + ("a" * 14) + '"')
            self.assertEqual(
                module._read_input_text(args, exact_stdin),
                exact_stdin.value,
            )
            self.assertEqual(exact_stdin.read_size, 17)

            over_stdin = RecordingStdin('"' + ("a" * 15) + '"')
            with self.assertRaises(module.AuditClientError) as raised:
                module._read_input_text(args, over_stdin)
            self.assertEqual(over_stdin.read_size, 17)
        self.assertEqual(raised.exception.error_type, "input")
        self.assertEqual(raised.exception.code, "input_too_large")

    def test_cli_rejects_missing_or_conflicting_input_mode_in_error_envelope(self):
        module = self.require_module()
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.write_config(directory)
            argument_sets = [
                ["--config", str(config_path), "--output-dir", directory],
                [
                    "--config",
                    str(config_path),
                    "--input-file",
                    str(FIXTURES / "canonical-audit-input.json"),
                    "--input-stdin",
                    "--output-dir",
                    directory,
                ],
            ]
            for arguments in argument_sets:
                stdout = io.StringIO()
                with self.subTest(arguments=arguments):
                    exit_code = module.main(
                        arguments,
                        stdin=io.StringIO(""),
                        stdout=stdout,
                    )
                    self.assertEqual(exit_code, 1)
                    envelope = json.loads(stdout.getvalue())
                    self.assertFalse(envelope["ok"])
                    self.assertEqual(envelope["error"]["type"], "config")

    def test_cli_prints_classified_error_code_without_secrets(self):
        module = self.require_module()
        output = io.StringIO()
        module.print_error(
            module.AuditClientError(
                "输入候选数量无效",
                error_type="input",
                code="multiple_certification_candidates",
                request_id="req-safe",
            ),
            stream=output,
        )
        envelope = json.loads(output.getvalue())
        self.assertEqual(envelope["error"]["type"], "input")
        self.assertEqual(
            envelope["error"]["code"],
            "multiple_certification_candidates",
        )
        self.assertEqual(envelope["error"]["requestId"], "req-safe")
        for secret in (
            "APPKEY_TEST_ONLY",
            "SECRET_TEST_ONLY",
            "Signature=",
        ):
            self.assertNotIn(secret, output.getvalue())

    def test_cli_unknown_exception_never_leaks_underlying_details(self):
        module = self.require_module()
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.write_config(directory)
            stdout = io.StringIO()
            sensitive = "SECRET_TEST_ONLY Signature=abc full-request-body"
            with mock.patch.object(
                module,
                "run_audit_workflow",
                side_effect=RuntimeError(sensitive),
            ):
                exit_code = module.main(
                    [
                        "--config",
                        str(config_path),
                        "--input-file",
                        str(FIXTURES / "canonical-audit-input.json"),
                        "--output-dir",
                        directory,
                    ],
                    stdout=stdout,
                )
            self.assertEqual(exit_code, 1)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["error"]["type"], "response")
            self.assertNotIn(sensitive, stdout.getvalue())
            self.assertNotIn("Signature=", stdout.getvalue())

    def test_workflow_classifies_api_auth_error(self):
        module = self.require_module()
        response = {
            "Response": {
                "Error": {
                    "Code": "AuthFailure.SignatureFailure",
                    "Message": "do not expose diagnostics",
                },
                "RequestId": "req-auth-api",
            }
        }
        with self.assertRaises(module.AuditClientError) as raised:
            module.run_audit_workflow(
                loaded_profile(),
                canonical_input(),
                post=lambda config, action, payload: response,
            )
        self.assertEqual(raised.exception.error_type, "auth")
        self.assertEqual(raised.exception.request_id, "req-auth-api")
        self.assertNotIn("diagnostics", str(raised.exception))

    def test_workflow_classifies_failed_states(self):
        module = self.require_module()
        for state in (3, 4, 5):
            responses = [
                {"Response": {"WorkflowRunId": "wfr", "RequestId": "req-1"}},
                {
                    "Response": {
                        "WorkflowRun": {"State": state, "Output": ""},
                        "RequestId": "req-failed",
                    }
                },
            ]
            with self.subTest(state=state):
                with self.assertRaises(module.AuditClientError) as raised:
                    module.run_audit_workflow(
                        loaded_profile(),
                        canonical_input(),
                        post=lambda config, action, payload: responses.pop(0),
                    )
                self.assertEqual(raised.exception.error_type, "workflow")
                self.assertEqual(raised.exception.request_id, "req-failed")

    def test_workflow_times_out_while_pending(self):
        module = self.require_module()
        config = loaded_profile()
        config["timeout_seconds"] = 0.2
        clock = FakeClock()

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
                    "WorkflowRun": {"State": 1, "Output": ""},
                    "RequestId": "req-pending",
                }
            }

        with self.assertRaises(module.AuditClientError) as raised:
            module.run_audit_workflow(
                config,
                canonical_input(),
                post=fake_post,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )
        self.assertEqual(raised.exception.error_type, "timeout")

    def test_workflow_rejects_malformed_envelopes(self):
        module = self.require_module()
        bad_responses = [None, {}, {"Response": []}, {"Response": {}}]
        for response in bad_responses:
            with self.subTest(response=response):
                with self.assertRaises(module.AuditClientError) as raised:
                    module.run_audit_workflow(
                        loaded_profile(),
                        canonical_input(),
                        post=lambda config, action, payload: response,
                    )
                self.assertEqual(raised.exception.error_type, "response")


if __name__ == "__main__":
    unittest.main()
