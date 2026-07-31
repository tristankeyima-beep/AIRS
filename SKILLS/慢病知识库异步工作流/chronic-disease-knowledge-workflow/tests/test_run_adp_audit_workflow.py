import importlib.util
import io
import json
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

    def test_load_config_rejects_missing_app_key_without_leaking_secret(self):
        module = self.require_module()
        config = profile_config()
        secret = config["profiles"]["cloud"]["secret_key"]
        config["profiles"]["cloud"]["app_key"] = ""
        with self.assertRaises(module.AuditClientError) as raised:
            module.load_config(self.write_config(config))
        self.assertEqual(raised.exception.error_type, "config")
        self.assertNotIn(secret, str(raised.exception))

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

    def test_workflow_accepts_string_output_and_stringified_rule_results(self):
        module = self.require_module()
        output = successful_output()
        output["ruleResults"] = [
            json.dumps(output["ruleResults"][0], ensure_ascii=False),
            "合成测试文本规则",
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
        self.assertEqual(result["ruleResults"][0]["ruleName"], "合成测试规则")
        self.assertEqual(result["ruleResults"][1], "合成测试文本规则")

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
        self.assertEqual(result["ruleResults"][0]["result"], "pass")

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
