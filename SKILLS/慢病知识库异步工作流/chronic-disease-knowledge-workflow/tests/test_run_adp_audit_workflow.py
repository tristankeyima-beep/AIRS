import importlib.util
import json
import pathlib
import tempfile
import unittest


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


if __name__ == "__main__":
    unittest.main()
