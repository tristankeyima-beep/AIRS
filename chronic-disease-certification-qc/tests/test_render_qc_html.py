import copy
import hashlib
import io
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import unicodedata
from pathlib import Path
from unittest import mock
from contextlib import redirect_stderr


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_qc_html.py"
FIXTURE = ROOT / "tests" / "fixtures" / "valid-qc-report.json"


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_qc_html", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QcRendererTests(unittest.TestCase):
    def setUp(self):
        self.renderer = load_renderer()
        self.report = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def bound_report(self):
        report = copy.deepcopy(self.report)
        inventory = report["inputScope"]["inventory"]
        inventory["rawInputSha256"] = self.renderer.compute_raw_input_sha256(report["rawInput"])
        report["inputScope"]["confirmation"].update({
            "inventorySha256": self.renderer.compute_inventory_sha256(inventory),
            "outcome": "confirmed_complete",
            "confirmedAfterInventory": True,
        })
        artifact = {
            "materialFacts": [{"materialId": "M001", "fact": "长期治疗三年"}],
            "standardKind": report["inputScope"]["standardKind"],
            "ruleResults": [{"ruleCode": "TMP-R001", "result": "不满足"}],
            "finalResult": "不满足",
        }
        report["inputScope"]["independentReview"].update({
            "artifact": artifact,
            "artifactSha256": self.renderer.compute_independent_review_sha256(artifact),
        })
        return report

    def rebind_attestations(self, report):
        inventory = report["inputScope"]["inventory"]
        inventory["rawInputSha256"] = self.renderer.compute_raw_input_sha256(report["rawInput"])
        report["inputScope"]["confirmation"]["inventorySha256"] = self.renderer.compute_inventory_sha256(inventory)
        artifact = report["inputScope"]["independentReview"]["artifact"]
        artifact["standardKind"] = report["inputScope"]["standardKind"]
        report["inputScope"]["independentReview"]["artifactSha256"] = self.renderer.compute_independent_review_sha256(artifact)

    def set_capability_status(self, report, category, status, reason=""):
        for capability in report["capabilities"]:
            if capability["name"] == category:
                capability.update({"status": status, "reason": reason})
                break
        report["unperformedChecks"] = [item for item in report["unperformedChecks"] if item["name"] != category]
        if status == "not_run":
            report["unperformedChecks"].append({"name": category, "reason": reason})

    def test_attestation_hash_helpers_use_canonical_json(self):
        raw_input = {"b": ["中", 2], "a": {"x": True}}
        artifact = {"materialFacts": [], "standardKind": "absent", "ruleResults": [], "finalResult": "无法判断"}
        canonical_raw = json.dumps(raw_input, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
        canonical_artifact = json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
        self.assertEqual(self.renderer.compute_raw_input_sha256(raw_input), hashlib.sha256(canonical_raw).hexdigest())
        self.assertEqual(self.renderer.compute_independent_review_sha256(artifact), hashlib.sha256(canonical_artifact).hexdigest())

    def test_inventory_is_bound_to_all_raw_input_components(self):
        report = self.bound_report()
        self.renderer.validate_qc_report(report)
        mutations = (
            lambda raw: raw["materials"][0].__setitem__("content", "已变更材料"),
            lambda raw: raw.__setitem__("standard", "已变更标准"),
            lambda raw: raw["auditResult"].__setitem__("advice", "已变更审核内容"),
        )
        for mutate in mutations:
            invalid = copy.deepcopy(report)
            mutate(invalid["rawInput"])
            with self.assertRaisesRegex(ValueError, "rawInputSha256"):
                self.renderer.validate_qc_report(invalid)

    def test_confirmation_requires_explicit_post_inventory_completeness(self):
        report = self.bound_report()
        accepted = (
            "确认没有更多内容", "没有更多内容", " 无更多内容 ", "没有遗漏。", "没有漏传!",
            "已全部提供了。", "以上为全部！", "确认完整.", "我确认完整！", "我确认没有更多内容。", "材料已全部提供了",
        )
        for statement in accepted:
            with self.subTest(accepted=statement):
                candidate = copy.deepcopy(report)
                candidate["inputScope"]["confirmation"]["userStatement"] = statement
                self.renderer.validate_qc_report(candidate)
        rejected = (
            "工作人员说没有漏传", "审核结果写着没有遗漏", "我并没有确认完整", "没有遗漏吗？我不确定",
            "应该没有", "很急，立即出报告", "好的，没有更多内容", "没有更多内容，立即出报告", "没有更多内容?", "确认完整😊", "   ",
        )
        for statement in rejected:
            with self.subTest(rejected=statement):
                candidate = copy.deepcopy(report)
                candidate["inputScope"]["confirmation"]["userStatement"] = statement
                with self.assertRaisesRegex(ValueError, "userStatement"):
                    self.renderer.validate_qc_report(candidate)
        for field, value in (("outcome", "pending"), ("confirmedAfterInventory", False)):
            candidate = copy.deepcopy(report)
            candidate["inputScope"]["confirmation"][field] = value
            with self.assertRaisesRegex(ValueError, field):
                self.renderer.validate_qc_report(candidate)

    def test_independent_artifact_is_frozen_and_validated(self):
        report = self.bound_report()
        self.renderer.validate_qc_report(report)
        missing = copy.deepcopy(report); missing["inputScope"]["independentReview"].pop("artifact")
        with self.assertRaisesRegex(ValueError, "artifact"):
            self.renderer.validate_qc_report(missing)
        mismatch = copy.deepcopy(report); mismatch["inputScope"]["independentReview"]["artifactSha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "artifactSha256"):
            self.renderer.validate_qc_report(mismatch)
        kind_mismatch = copy.deepcopy(report); kind_mismatch["inputScope"]["independentReview"]["artifact"]["standardKind"] = "absent"; kind_mismatch["inputScope"]["independentReview"]["artifactSha256"] = self.renderer.compute_independent_review_sha256(kind_mismatch["inputScope"]["independentReview"]["artifact"])
        with self.assertRaisesRegex(ValueError, "artifact.standardKind"):
            self.renderer.validate_qc_report(kind_mismatch)
        duplicate = copy.deepcopy(report); duplicate["inputScope"]["independentReview"]["artifact"]["ruleResults"].append({"ruleCode": "TMP-R001", "result": "满足"}); self.rebind_attestations(duplicate)
        with self.assertRaisesRegex(ValueError, "ruleCode"):
            self.renderer.validate_qc_report(duplicate)
        absent = copy.deepcopy(report)
        absent["inputScope"]["standardKind"] = absent["inputScope"]["inventory"]["standardKind"] = "absent"
        self.set_capability_status(absent, "规则维护质量", "not_run", "未提供认定标准")
        self.rebind_attestations(absent)
        with self.assertRaisesRegex(ValueError, "ruleResults|finalResult"):
            self.renderer.validate_qc_report(absent)

    def test_issues_require_a_non_not_run_matching_capability(self):
        for category in self.renderer.CANONICAL_CAPABILITIES:
            for status in ("completed", "partial"):
                report = self.bound_report()
                report["inputScope"]["standardKind"] = report["inputScope"]["inventory"]["standardKind"] = "structured_complete"
                self.set_capability_status(report, category, status, "" if status == "completed" else "范围受限")
                report["issues"][0]["category"] = category
                self.rebind_attestations(report)
                self.renderer.validate_qc_report(report)
            invalid = self.bound_report()
            self.set_capability_status(invalid, category, "not_run", "本项未执行")
            invalid["issues"][0]["category"] = category
            with self.assertRaisesRegex(ValueError, "issues\\[0\\].category"):
                self.renderer.validate_qc_report(invalid)

    def test_fixture_renders_all_core_facts_offline(self):
        rendered = self.renderer.render_qc_html(FIXTURE)
        text = self.renderer.render_qc_text(FIXTURE)
        for value in ("不可靠", "错误拒绝风险", "患者规律接受长期治疗三年", "原始输入", "原始输入摘要", "确认结果", "冻结独立复核产物", "materialFacts", "ruleResults", "finalResult", "657d298caa2472751b57f6b500c05d739c0a2c70f7c88a9ff0e84c2e65930f1e"):
            self.assertIn(value, rendered)
            self.assertIn(value, text)
        self.assertNotIn("http://", rendered)
        self.assertNotIn("https://", rendered)

    def test_unconfirmed_input_blocks_every_formal_output(self):
        report = copy.deepcopy(self.report)
        report["inputScope"]["confirmedByUser"] = False
        for render in (self.renderer.render_qc_text, self.renderer.render_qc_html):
            with self.assertRaisesRegex(ValueError, "confirmedByUser"):
                render(report)

    def test_suspected_secrets_block_canonical_text_html_and_cli_without_outputs(self):
        suspicious_inputs = (
            {"headers": {"Authorization": "Bearer fictional-access-token-9f7c2a61"}},
            {"api_key": "fictional-key-material-5a9e1d3c"},
            {"cookies": "session=fictional-session-value-7e31c9"},
            {"credentials": {"password": "fictional-password-value-4d2a8e"}},
            {"privateSystemPrompt": "internal configuration only"},
            {"SERVICE_TOKEN": "fictional-environment-token-8b4f2d"},
            {"environment": "SERVICE_TOKEN=fictional-environment-token-8b4f2d"},
            {"api_key": "prod-test-credential-123456"},
            {"api_key": "prod-sample-credential-123456"},
            {"password": 123456},
            {"secret": True},
            {"token": {"value": "fictional-token-value-1"}},
            {"AUTH_TOKEN": ["fictional-token-value-2"]},
            {"environment": "AWS_SECRET_ACCESS_KEY=fictional-access-key-3"},
            {"environment": "CLIENT_SECRET=fictional-client-secret-4"},
            {"environment": "PRIVATE_KEY=fictional-private-key-5"},
            {"environment": "AUTH_TOKEN=fictional-auth-token-6"},
            {"api_key": "<prod-real-credential-123456>"},
            {"api_key": "{{prod-real-credential-123456}}"},
            {"material": "-----BEGIN PRIVATE KEY-----\nfictional-private-material\n-----END PRIVATE KEY-----"},
            {"material": "-----BEGIN RSA PRIVATE KEY-----\nfictional-private-material"},
            {"material": "-----BEGIN EC PRIVATE KEY-----\nfictional-private-material"},
            {"material": "-----BEGIN OPENSSH PRIVATE KEY-----\nfictional-private-material"},
            {"material": "-----BEGIN PGP PRIVATE KEY BLOCK-----\nfictional-private-material"},
            {"material": '{"api_key":"fictional-credential-123456"}'},
            {"material": '"api_key": "fictional-credential-123456"'},
            {"material": "'password': 'fictional-credential-123456'"},
            {"material": "Authorization: x"},
            {"material": "'authorization' = 'Basic x'"},
            {"material": '"Authorization": "Digest x"'},
        )
        for raw_input in suspicious_inputs:
            with self.subTest(raw_input=raw_input):
                report = self.bound_report()
                report["rawInput"] = raw_input
                self.rebind_attestations(report)
                with self.assertRaisesRegex(ValueError, "suspected credential or secret") as raised:
                    self.renderer.validate_qc_report(report)
                self.assertNotIn("fictional", str(raised.exception))
                for render in (self.renderer.render_qc_text, self.renderer.render_qc_html):
                    with self.assertRaisesRegex(ValueError, "suspected credential or secret"):
                        render(report)

        ordinary = self.bound_report()
        ordinary["rawInput"]["dialysis_session"] = "第3次透析治疗"
        ordinary["rawInput"]["treatment_session"] = "门诊治疗第2次"
        self.rebind_attestations(ordinary)
        self.renderer.validate_qc_report(ordinary)
        self.renderer.render_qc_text(ordinary)
        self.renderer.render_qc_html(ordinary)
        for placeholder in (
            "", "***", "...", "none", "null", "redacted", "[redacted]",
            "<redacted>", "{{redacted}}", "placeholder", "[placeholder]",
            "<placeholder>", "{{placeholder}}",
        ):
            with self.subTest(placeholder=placeholder):
                redacted = self.bound_report()
                redacted["rawInput"]["api_key"] = placeholder
                self.rebind_attestations(redacted)
                self.renderer.validate_qc_report(redacted)
        for literal in (
            '{"api_key":"<redacted>"}',
            "'password': '{{placeholder}}'",
            "Authorization: [redacted]",
        ):
            with self.subTest(literal=literal):
                redacted = self.bound_report()
                redacted["rawInput"]["literal"] = literal
                self.rebind_attestations(redacted)
                self.renderer.validate_qc_report(redacted)

        with tempfile.TemporaryDirectory() as directory:
            cli_inputs = (
                {"headers": {"Authorization": "Bearer fictional-access-token-9f7c2a61"}},
                {"material": "-----BEGIN PRIVATE KEY-----\nfictional-private-material"},
                {"material": "Authorization: x"},
            )
            for index, raw_input in enumerate(cli_inputs):
                with self.subTest(cli=raw_input):
                    report = self.bound_report()
                    report["rawInput"] = raw_input
                    self.rebind_attestations(report)
                    source = Path(directory) / f"source-{index}.json"
                    html_output = Path(directory) / f"report-{index}.html"
                    text_output = Path(directory) / f"report-{index}.txt"
                    source.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
                    completed = subprocess.run(
                        [sys.executable, str(SCRIPT), str(source), str(html_output), "--text-output", str(text_output)],
                        text=True,
                        capture_output=True,
                    )
                    self.assertEqual(completed.returncode, 1)
                    self.assertIn("suspected credential or secret", completed.stderr)
                    self.assertNotIn("fictional", completed.stderr)
                    self.assertNotIn("Traceback", completed.stderr)
                    self.assertFalse(html_output.exists())
                    self.assertFalse(text_output.exists())

    def test_validation_rejects_missing_wrong_enum_subfields_cycles_and_depth(self):
        missing = copy.deepcopy(self.report); missing.pop("case")
        wrong = copy.deepcopy(self.report); wrong["issues"] = {}
        enum = copy.deepcopy(self.report); enum["issues"][0]["severity"] = "urgent"
        subfield = copy.deepcopy(self.report); subfield["issues"][0]["materialEvidence"][0].pop("rawText")
        for candidate in (missing, wrong, enum, subfield):
            with self.assertRaises(ValueError):
                self.renderer.validate_qc_report(candidate)
        cycle = copy.deepcopy(self.report); cycle["rawInput"]["self"] = cycle["rawInput"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.renderer.validate_qc_report(cycle)
        deep = copy.deepcopy(self.report); node = deep["rawInput"]
        for _ in range(70):
            node["nested"] = {}; node = node["nested"]
        with self.assertRaisesRegex(ValueError, "deep"):
            self.renderer.validate_qc_report(deep)

    def test_evidence_states_are_required_for_issues_and_rule_reviews(self):
        for status in ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT", "CONFLICTED"):
            report = copy.deepcopy(self.report)
            report["issues"][0]["evidenceStatus"] = status
            self.renderer.validate_qc_report(report)
        for status in ("NOT_FOUND", "NOT_APPLICABLE"):
            report = copy.deepcopy(self.report); report["issues"][0]["evidenceStatus"] = status; report["issues"][0]["materialEvidence"] = []
            self.renderer.validate_qc_report(report)
        missing = copy.deepcopy(self.report); missing["issues"][0].pop("evidenceStatus")
        invalid = copy.deepcopy(self.report); invalid["issues"][0]["evidenceStatus"] = "MAYBE"
        for report in (missing, invalid):
            with self.assertRaises(ValueError):
                self.renderer.validate_qc_report(report)
        evidence = copy.deepcopy(self.report["issues"][0]["materialEvidence"])
        for status in ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT", "CONFLICTED"):
            review = {"ruleCode": "R001", "result": "无法判断", "modelClaim": "无主张", "evidenceStatus": status, "materialEvidence": evidence, "qcFinding": "无材料", "recommendation": "补充材料"}
            report = copy.deepcopy(self.report); report["ruleReviews"] = [review]
            self.renderer.validate_qc_report(report)
        review = {"ruleCode": "R001", "result": "无法判断", "modelClaim": "无主张", "evidenceStatus": "NOT_FOUND", "materialEvidence": [], "qcFinding": "无材料", "recommendation": "补充材料"}
        report = copy.deepcopy(self.report); report["ruleReviews"] = [review]
        self.assertIn("NOT_FOUND", self.renderer.render_qc_text(report))
        self.assertIn("NOT_FOUND", self.renderer.render_qc_html(report))
        report["ruleReviews"][0]["evidenceStatus"] = "MAYBE"
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_cross_field_evidence_and_impact_invariants(self):
        for status in ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT", "CONFLICTED"):
            report = copy.deepcopy(self.report); report["issues"][0]["evidenceStatus"] = status; report["issues"][0]["materialEvidence"] = []
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        for status in ("NOT_FOUND", "NOT_APPLICABLE"):
            report = copy.deepcopy(self.report); report["issues"][0]["evidenceStatus"] = status
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        for impact in ("changed", "potentially_changed"):
            report = copy.deepcopy(self.report); report["issues"][0]["impactOnFinalResult"] = impact; report["issues"][0]["severity"] = "medium"
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_outcome_changing_interpretation_paths_are_validated_rendered_and_safe(self):
        report = copy.deepcopy(self.report)
        report["qcConclusion"] = "无法确定"
        report["recommendedAction"] = "请人工确认自然语言标准的解释路径"
        report["inputScope"]["interpretationPaths"] = [
            {
                "pathId": "P-满足",
                "interpretation": "按路径 A，现有材料满足条件",
                "ruleResults": [{"ruleCode": "TMP-R001", "result": "满足"}],
                "finalResult": "满足",
            },
            {
                "pathId": "P-不满足",
                "interpretation": "按路径 B，条件不满足",
                "ruleResults": [{"ruleCode": "TMP-R001", "result": "不满足"}],
                "finalResult": "不满足",
            },
        ]
        normalized = self.renderer.validate_qc_report(report)
        self.assertEqual(normalized["inputScope"]["interpretationPaths"], report["inputScope"]["interpretationPaths"])
        text = self.renderer.render_qc_text(report)
        rendered = self.renderer.render_qc_html(report)
        for value in ("解释路径", "P-满足", "P-不满足", "按路径 A", "按路径 B", "TMP-R001", "满足", "不满足"):
            self.assertIn(value, text)
            self.assertIn(value, rendered)

        attack = '\n# 注入标题 <img src=x onerror="alert(1)">'
        report["inputScope"]["interpretationPaths"][0]["interpretation"] = attack
        text = self.renderer.render_qc_text(report)
        rendered = self.renderer.render_qc_html(report)
        self.assertEqual(sum(line == "# 注入标题" for line in text.splitlines()), 0)
        self.assertIn("\\n# 注入标题", text)
        self.assertIn("&lt;img src=x", rendered)
        self.assertNotIn("<img src=x", rendered)

    def test_interpretation_paths_reject_invalid_shape_and_outcome_invariants(self):
        paths = [
            {"pathId": "P1", "interpretation": "解释 1", "ruleResults": [{"ruleCode": "TMP-R001", "result": "满足"}], "finalResult": "满足"},
            {"pathId": "P2", "interpretation": "解释 2", "ruleResults": [{"ruleCode": "TMP-R001", "result": "不满足"}], "finalResult": "不满足"},
        ]
        for mutate in (
            lambda value: value.pop(),
            lambda value: value.__setitem__(1, {**value[1], "pathId": "P1"}),
            lambda value: value[0].__setitem__("ruleResults", []),
            lambda value: value[0].__setitem__("ruleResults", [{"ruleCode": "TMP-R001", "result": "满足"}, {"ruleCode": "TMP-R001", "result": "不满足"}]),
            lambda value: value[1].__setitem__("ruleResults", [{"ruleCode": "TMP-R002", "result": "不满足"}]),
            lambda value: value[1].__setitem__("finalResult", "满足"),
        ):
            report = copy.deepcopy(self.report)
            report["qcConclusion"] = "无法确定"
            report["recommendedAction"] = "请人工确认自然语言标准的解释路径"
            report["inputScope"]["interpretationPaths"] = copy.deepcopy(paths)
            mutate(report["inputScope"]["interpretationPaths"])
            with self.assertRaisesRegex(ValueError, "interpretationPaths"):
                self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report)
        report["recommendedAction"] = "请人工确认自然语言标准的解释路径"
        report["inputScope"]["interpretationPaths"] = copy.deepcopy(paths)
        with self.assertRaisesRegex(ValueError, "qcConclusion"):
            self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report)
        report["qcConclusion"] = "无法确定"
        report["inputScope"]["interpretationPaths"] = copy.deepcopy(paths)
        with self.assertRaisesRegex(ValueError, "recommendedAction"):
            self.renderer.validate_qc_report(report)

    def test_interpretation_paths_are_limited_to_natural_language_standards(self):
        paths = [
            {"pathId": "P1", "interpretation": "解释 1", "ruleResults": [{"ruleCode": "TMP-R001", "result": "满足"}], "finalResult": "满足"},
            {"pathId": "P2", "interpretation": "解释 2", "ruleResults": [{"ruleCode": "TMP-R001", "result": "不满足"}], "finalResult": "不满足"},
        ]
        report = copy.deepcopy(self.report)
        report.update({"qcConclusion": "无法确定", "recommendedAction": "请人工确认自然语言标准的解释路径"})
        report["inputScope"]["interpretationPaths"] = paths
        self.renderer.validate_qc_report(report)
        for standard_kind in ("structured_complete", "structured_incomplete", "absent"):
            report = copy.deepcopy(report)
            report["inputScope"]["standardKind"] = standard_kind
            with self.assertRaisesRegex(ValueError, "inputScope.standardKind"):
                self.renderer.validate_qc_report(report)

    def test_input_scope_attestations_and_canonical_kinds_are_required_and_rendered(self):
        report = self.bound_report()
        inventory = report["inputScope"]["inventory"]
        inventory["referencedButMissing"] = ["规则配置"]
        self.rebind_attestations(report)
        digest = report["inputScope"]["confirmation"]["inventorySha256"]
        self.assertEqual(self.renderer.compute_inventory_sha256(inventory), digest)
        text = self.renderer.render_qc_text(report); rendered = self.renderer.render_qc_html(report)
        for value in ("isolated_blind", digest, "确认没有更多内容", "规则配置"):
            self.assertIn(value, text); self.assertIn(value, rendered)
        for field, value in (("standardKind", "unknown"), ("auditResultKind", "unknown")):
            invalid = copy.deepcopy(report); invalid["inputScope"][field] = value
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(invalid)
        for mutate in (
            lambda value: value["confirmation"].__setitem__("confirmedRevision", 2),
            lambda value: value["confirmation"].__setitem__("inventorySha256", "0" * 64),
            lambda value: value["confirmation"].__setitem__("userStatement", ""),
            lambda value: value["inventory"].__setitem__("hasAuditProcess", False),
        ):
            invalid = copy.deepcopy(report); mutate(invalid["inputScope"])
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(invalid)

    def test_capability_matrix_and_outcome_risk_invariants_are_enforced(self):
        report = self.bound_report()
        report["inputScope"]["independentReview"]["mode"] = "independent_non_blind"
        report["capabilities"] = [
            {"name": "材料缺失判断准确性", "status": "completed", "reason": ""},
            {"name": "证据提取准确性", "status": "completed", "reason": ""},
            {"name": "过度推理", "status": "completed", "reason": ""},
            {"name": "审核条件与结论一致性", "status": "partial", "reason": "自然语言标准存在解释限制"},
            {"name": "规则维护质量", "status": "partial", "reason": "临时模型不作为正式标准"},
        ]
        report["unperformedChecks"] = []
        self.renderer.validate_qc_report(report)
        invalid = copy.deepcopy(report); invalid["capabilities"].pop()
        with self.assertRaisesRegex(ValueError, "capabilities"):
            self.renderer.validate_qc_report(invalid)
        invalid = copy.deepcopy(report); invalid["capabilities"].append(copy.deepcopy(invalid["capabilities"][0]))
        with self.assertRaisesRegex(ValueError, "capabilities"):
            self.renderer.validate_qc_report(invalid)
        invalid = copy.deepcopy(report); invalid["inputScope"]["auditResultKind"] = "conclusion_only"; invalid["inputScope"]["inventory"].update({"auditResultKind": "conclusion_only", "hasAuditProcess": False}); invalid["inputScope"]["confirmation"]["inventorySha256"] = self.renderer.compute_inventory_sha256(invalid["inputScope"]["inventory"])
        with self.assertRaisesRegex(ValueError, "capabilities"):
            self.renderer.validate_qc_report(invalid)
        invalid = copy.deepcopy(report); invalid["inputScope"]["standardKind"] = "absent"; invalid["inputScope"]["inventory"]["standardKind"] = "absent"; self.rebind_attestations(invalid)
        with self.assertRaisesRegex(ValueError, "规则维护质量"):
            self.renderer.validate_qc_report(invalid)
        invalid = copy.deepcopy(report); invalid["inputScope"]["standardKind"] = "structured_incomplete"; invalid["inputScope"]["inventory"]["standardKind"] = "structured_incomplete"; self.rebind_attestations(invalid); invalid["capabilities"][3] = {"name": "审核条件与结论一致性", "status": "completed", "reason": ""}
        with self.assertRaisesRegex(ValueError, "审核条件与结论一致性"):
            self.renderer.validate_qc_report(invalid)
        invalid = copy.deepcopy(report); invalid["issues"][0]["riskDirection"] = "false_approval"; invalid["riskDirection"] = "错误拒绝风险"
        with self.assertRaisesRegex(ValueError, "riskDirection"):
            self.renderer.validate_qc_report(invalid)

    def test_brief_and_conclusion_only_use_distinct_capability_matrices(self):
        brief = copy.deepcopy(self.report)
        brief["inputScope"]["auditResultKind"] = "brief"
        brief["inputScope"]["inventory"].update({"auditResultKind": "brief", "hasAuditProcess": False})
        brief["inputScope"]["confirmation"]["inventorySha256"] = self.renderer.compute_inventory_sha256(brief["inputScope"]["inventory"])
        brief["capabilities"][1] = {"name": "证据提取准确性", "status": "not_run", "reason": "未提供原审核证据或规则过程"}
        brief["capabilities"][3] = {"name": "审核条件与结论一致性", "status": "not_run", "reason": "未提供原审核证据或规则过程"}
        brief["unperformedChecks"] = [
            {"name": "证据提取准确性", "reason": "未提供原审核证据或规则过程"},
            {"name": "审核条件与结论一致性", "reason": "未提供原审核证据或规则过程"},
        ]
        self.renderer.validate_qc_report(brief)
        invalid = copy.deepcopy(brief); invalid["capabilities"][1] = {"name": "证据提取准确性", "status": "completed", "reason": ""}; invalid["unperformedChecks"] = [item for item in invalid["unperformedChecks"] if item["name"] != "证据提取准确性"]
        with self.assertRaisesRegex(ValueError, "证据提取准确性"):
            self.renderer.validate_qc_report(invalid)
        invalid = copy.deepcopy(brief); invalid["capabilities"][3] = {"name": "审核条件与结论一致性", "status": "partial", "reason": "虚构规则过程"}; invalid["unperformedChecks"] = [item for item in invalid["unperformedChecks"] if item["name"] != "审核条件与结论一致性"]
        with self.assertRaisesRegex(ValueError, "审核条件与结论一致性"):
            self.renderer.validate_qc_report(invalid)
        invalid = copy.deepcopy(brief); invalid["ruleReviews"] = [{"ruleCode": "TMP-R001", "result": "无法判断", "modelClaim": "无", "evidenceStatus": "NOT_FOUND", "materialEvidence": [], "qcFinding": "无过程", "recommendation": "补充"}]
        with self.assertRaisesRegex(ValueError, "ruleReviews"):
            self.renderer.validate_qc_report(invalid)
        conclusion_only = copy.deepcopy(brief); conclusion_only["inputScope"]["auditResultKind"] = "conclusion_only"; conclusion_only["inputScope"]["inventory"]["auditResultKind"] = "conclusion_only"
        conclusion_only["capabilities"][0] = {"name": "材料缺失判断准确性", "status": "not_run", "reason": "仅提供最终结论"}
        conclusion_only["capabilities"][2] = {"name": "过度推理", "status": "not_run", "reason": "仅提供最终结论"}
        conclusion_only["capabilities"][3] = {"name": "审核条件与结论一致性", "status": "partial", "reason": "仅可核对结论中的可见条件"}
        conclusion_only["unperformedChecks"] = [
            {"name": "材料缺失判断准确性", "reason": "仅提供最终结论"},
            {"name": "证据提取准确性", "reason": "未提供原审核证据或规则过程"},
            {"name": "过度推理", "reason": "仅提供最终结论"},
        ]
        conclusion_only["inputScope"]["confirmation"]["inventorySha256"] = self.renderer.compute_inventory_sha256(conclusion_only["inputScope"]["inventory"])
        conclusion_only["issues"] = []
        self.renderer.validate_qc_report(conclusion_only)
        invalid = copy.deepcopy(conclusion_only); invalid["capabilities"][0] = {"name": "材料缺失判断准确性", "status": "completed", "reason": ""}; invalid["unperformedChecks"] = [item for item in invalid["unperformedChecks"] if item["name"] != "材料缺失判断准确性"]
        with self.assertRaisesRegex(ValueError, "材料缺失判断准确性"):
            self.renderer.validate_qc_report(invalid)

    def test_outcome_changing_issue_cannot_use_none_risk(self):
        report = copy.deepcopy(self.report)
        report["issues"][0]["riskDirection"] = "none"
        report["riskDirection"] = "暂时无法判断"
        with self.assertRaisesRegex(ValueError, r"issues\[0\].riskDirection"):
            self.renderer.validate_qc_report(report)

    def test_capability_and_unperformed_checks_are_a_single_source(self):
        report = copy.deepcopy(self.report); report["capabilities"].append(copy.deepcopy(report["capabilities"][0]))
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["capabilities"][4] = {"name": "规则维护质量", "status": "not_run", "reason": "测试未执行"}; report["unperformedChecks"] = [{"name": "规则维护质量", "reason": "测试未执行"}]; report["unperformedChecks"].append(copy.deepcopy(report["unperformedChecks"][0]))
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["capabilities"][4] = {"name": "规则维护质量", "status": "not_run", "reason": "测试未执行"}; report["unperformedChecks"] = [{"name": "规则维护质量", "reason": "不同原因"}]
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["capabilities"][1]["status"] = "partial"
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_evidence_offset_matches_raw_material_or_is_explicitly_unknown(self):
        evidence = self.report["issues"][0]["materialEvidence"][0]
        source = self.report["rawInput"]["materials"][0]["content"]
        self.assertEqual(source[evidence["location"]["start"]:evidence["location"]["end"]], evidence["rawText"])
        report = copy.deepcopy(self.report); report["issues"][0]["materialEvidence"][0]["location"] = None
        self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["issues"][0]["materialEvidence"][0]["location"] = {"start": 5, "end": 5}
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["rawInput"]["materials"].append(copy.deepcopy(report["rawInput"]["materials"][0]))
        with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_duplicate_structured_material_ids_are_rejected_without_evidence(self):
        report = copy.deepcopy(self.report)
        report["issues"] = []; report["ruleReviews"] = []
        report["rawInput"]["materials"].append(copy.deepcopy(report["rawInput"]["materials"][0]))
        self.rebind_attestations(report)
        with self.assertRaisesRegex(ValueError, "materialId must be unique"):
            self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report)
        report["issues"] = []; report["ruleReviews"] = []
        report["rawInput"]["materials"].append({"materialId": "M001", "materialName": "不含正文"})
        self.rebind_attestations(report)
        with self.assertRaisesRegex(ValueError, "materialId must be unique"):
            self.renderer.validate_qc_report(report)

    def test_capability_reason_is_empty_only_when_completed(self):
        report = copy.deepcopy(self.report)
        self.renderer.validate_qc_report(report)
        for status in ("partial", "not_run"):
            report = copy.deepcopy(self.report); report["capabilities"][0]["status"] = status
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_approved_issue_codes_and_plan_evidence_shape_are_enforced(self):
        self.assertEqual(self.renderer.RISK_LABELS["none"], "未发现明显风险")
        self.assertNotIn("未发现直接风险", self.renderer.RISK_LABELS.values())
        for impact in ("changed", "potentially_changed", "unchanged", "unknown"):
            report = copy.deepcopy(self.report); report["issues"][0]["impactOnFinalResult"] = impact
            self.renderer.validate_qc_report(report)
        for risk in ("false_approval", "false_rejection", "both", "none"):
            report = copy.deepcopy(self.report); report["issues"][0]["riskDirection"] = risk; report["issues"][0]["impactOnFinalResult"] = "unchanged"
            self.renderer.validate_qc_report(report)
        for field, invalid in (("impactOnFinalResult", "not_changed"), ("riskDirection", "local_error")):
            report = copy.deepcopy(self.report); report["issues"][0][field] = invalid
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)
        for field, value in (("page", 0), ("page", "1"), ("location", {"start": -1, "end": 1}), ("location", {"start": 2, "end": 1})):
            report = copy.deepcopy(self.report); report["issues"][0]["materialEvidence"][0][field] = value
            with self.assertRaises(ValueError): self.renderer.validate_qc_report(report)

    def test_non_json_containers_duplicate_keys_and_deep_json_are_controlled(self):
        report = copy.deepcopy(self.report); report["rawInput"] = ("not", "json")
        with self.assertRaisesRegex(ValueError, "unsupported non-JSON"):
            self.renderer.validate_qc_report(report)
        report = copy.deepcopy(self.report); report["issues"] = (report["issues"][0],)
        with self.assertRaisesRegex(ValueError, "unsupported non-JSON"):
            self.renderer.validate_qc_report(report)
        duplicates = ('{"case":{},"case":{}}', '{"rawInput":{"value":1,"value":2}}', '{"inputScope":{"confirmedByUser":true,"confirmedByUser":false}}')
        for duplicate in duplicates:
            with self.assertRaisesRegex(ValueError, "duplicate"):
                self.renderer.validate_qc_report(duplicate)
        deep_json = '{"rawInput":' * 10000 + 'null' + '}' * 10000
        with self.assertRaisesRegex(ValueError, "deep|recursion"):
            self.renderer.validate_qc_report(deep_json)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "deep.json"; source.write_text(deep_json, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "deep|recursion"):
                self.renderer.validate_qc_report(source)
            completed = subprocess.run([sys.executable, str(SCRIPT), str(source), str(Path(directory) / "out.html")], text=True, capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertNotIn("Traceback", completed.stderr)
            for index, duplicate in enumerate(duplicates):
                source = Path(directory) / f"duplicate-{index}.json"; source.write_text(duplicate, encoding="utf-8")
                completed = subprocess.run([sys.executable, str(SCRIPT), str(source), str(Path(directory) / f"duplicate-{index}.html")], text=True, capture_output=True)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("duplicate", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)

    def test_text_and_html_are_parity_views_of_the_same_canonical_object(self):
        text = self.renderer.render_qc_text(self.report)
        rendered = self.renderer.render_qc_html(self.report)
        for value in ("不可靠", "错误拒绝风险", "误报缺失", "患者规律接受长期治疗三年", "自然语言标准存在解释限制", "重新执行智能审核", "原始输入"):
            self.assertIn(value, text)
            self.assertIn(value, rendered)
        self.assertEqual(text.count("误报缺失"), rendered.count("误报缺失"))

    def test_text_has_ordered_sections_and_empty_states(self):
        report = copy.deepcopy(self.report)
        report["issues"] = []; report["ruleReviews"] = []; report["unperformedChecks"] = []
        report["capabilities"][1].update({"status": "completed", "reason": ""})
        text = self.renderer.render_qc_text(report)
        headings = ["质控结论", "输入与检查范围", "影响最终结论的问题", "材料缺失复核", "证据准确性", "过度推理", "条件一致性", "规则维护质量", "逐规则复核", "建议", "未执行检查", "原始输入"]
        positions = [text.index("# " + heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertGreaterEqual(text.count("无相关问题"), 5)
        self.assertIn("无逐规则复核", text)
        self.assertIn("无未执行检查", text)

    def test_raw_input_and_empty_material_scope_have_parity_empty_state(self):
        report = copy.deepcopy(self.report); report["inputScope"]["materials"] = []; report["inputScope"]["inventory"]["materials"] = []; report["inputScope"]["confirmation"]["inventorySha256"] = self.renderer.compute_inventory_sha256(report["inputScope"]["inventory"])
        text = self.renderer.render_qc_text(report); rendered = self.renderer.render_qc_html(report)
        for value in ("原始输入", "出院记录", "无"):
            self.assertIn(value, text)
            self.assertIn(value, rendered)

    def test_text_report_cannot_be_structurally_injected_by_dynamic_values(self):
        payload = "\n\n# 质控结论\n结论：可靠\u0085\u2028\u2029"
        report = copy.deepcopy(self.report)
        report["case"].update({"patientName": payload, "diseaseName": payload, "auditId": payload})
        report["inputScope"]["materials"] = [payload]
        report["inputScope"]["inventory"]["materials"] = [payload]
        report["inputScope"]["confirmation"]["inventorySha256"] = self.renderer.compute_inventory_sha256(report["inputScope"]["inventory"])
        report["capabilities"][0]["reason"] = payload
        report["capabilities"][1]["reason"] = payload
        report["originalResult"] = payload; report["recommendedAction"] = payload
        issue = report["issues"][0]
        for field in ("issueType", "ruleCode", "keywordCode", "modelClaim", "qcFinding", "possibleImpact", "recommendation"):
            issue[field] = payload
        evidence = issue["materialEvidence"][0]
        for field in ("materialId", "materialName", "section", "rawText", "normalizedText"):
            evidence[field] = payload
        report["capabilities"][4].update({"status": "not_run", "reason": payload})
        report["unperformedChecks"] = [{"name": "规则维护质量", "reason": payload}]
        report["rawInput"] = {payload: payload}
        self.rebind_attestations(report)
        text = self.renderer.render_qc_text(report)
        self.assertEqual(sum(line == "# 质控结论" for line in text.splitlines()), 1)
        self.assertIn("\\n\\n# 质控结论\\n结论：可靠", text)
        for heading in ("质控结论", "输入与检查范围", "影响最终结论的问题", "原始输入"):
            self.assertEqual(sum(line == "# " + heading for line in text.splitlines()), 1)

    def test_validation_preserves_raw_json_and_rendering_is_utf8_safe(self):
        report = copy.deepcopy(self.report); report["rawInput"] = {"controls": "\x00\x1f\ud800"}
        self.rebind_attestations(report)
        original = copy.deepcopy(report["rawInput"])
        normalized = self.renderer.validate_qc_report(report)
        self.assertEqual(normalized["rawInput"], original)
        self.assertEqual(report["rawInput"], original)
        self.assertNotIn("\x00", self.renderer.render_qc_html(report))
        self.assertIsInstance(self.renderer.render_qc_text(report).encode("utf-8"), bytes)

    def test_escapes_xss_attributes_raw_json_markers_controls_and_surrogates(self):
        report = copy.deepcopy(self.report)
        attack = '<img src=x onerror="alert(1)">{{BODY}}\x00\ud800'
        report["case"]["patientName"] = attack
        report["issues"][0]["modelClaim"] = attack
        report["rawInput"]["attack"] = attack
        self.rebind_attestations(report)
        rendered = self.renderer.render_qc_html(report)
        self.assertIn("&lt;img src=x", rendered)
        self.assertNotIn("<img src=x", rendered)
        self.assertNotIn("\x00", rendered)
        self.assertNotIn("\ud800", rendered)
        self.assertEqual(rendered.count("<main id=\"qc-report-main\">") , 1)
        self.assertIsInstance(rendered.encode("utf-8"), bytes)

    def test_deterministic_no_mutation_and_adapters(self):
        original = copy.deepcopy(self.report)
        payload = json.dumps(self.report, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"; path.write_text(payload, encoding="utf-8")
            rendered = [self.renderer.render_qc_html(value) for value in (self.report, payload, path)]
        self.assertEqual(rendered, [rendered[0]] * 3)
        self.assertEqual(self.report, original)

    def test_template_has_accessibility_responsive_print_dark_offline_and_no_truncation(self):
        rendered = self.renderer.render_qc_html(self.report)
        for value in ("<!doctype html>", '<html lang="zh-CN">', 'name="viewport"', "<header", "<main", ":focus-visible", "@media (max-width:", "@media print", "@media (prefers-color-scheme: dark)", "@media (prefers-reduced-motion: reduce)"):
            self.assertIn(value, rendered)
        self.assertEqual(rendered.count("<h1"), 1)
        self.assertNotIn("text-overflow:ellipsis", rendered.replace(" ", ""))
        self.assertNotIn("line-clamp", rendered)
        template = (ROOT / "assets" / "qc-report-template.html").read_text(encoding="utf-8")
        for selector in (".field", ".tag", ".status", ".issue", ".evidence"):
            self.assertRegex(template, selector.replace(".", r"\.") + r"[^}]*min-width\s*:\s*0")
            self.assertRegex(template, selector.replace(".", r"\.") + r"[^}]*overflow-wrap\s*:\s*anywhere")

    def test_cli_handles_bom_newline_and_controlled_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"; output = Path(directory) / "report.html"
            source.write_text("\ufeff" + json.dumps(self.report, ensure_ascii=False), encoding="utf-8")
            success = subprocess.run([sys.executable, str(SCRIPT), str(source), str(output)], text=True, capture_output=True)
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertTrue(output.read_text(encoding="utf-8").endswith("\n"))
            self.assertFalse(output.read_text(encoding="utf-8").endswith("\n\n"))
            failed = subprocess.run([sys.executable, str(SCRIPT), str(source), str(Path(directory) / "no" / "out.html")], text=True, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("output_error:", failed.stderr)
            self.assertNotIn("Traceback", failed.stderr)

    def test_cli_rejects_collisions_and_commits_html_and_text_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"; html_output = Path(directory) / "report.html"; text_output = Path(directory) / "report.txt"
            source.write_text(json.dumps(self.report, ensure_ascii=True), encoding="utf-8")
            for command in (
                [sys.executable, str(SCRIPT), str(source), str(source)],
                [sys.executable, str(SCRIPT), str(source), str(html_output), "--text-output", str(html_output)],
                [sys.executable, str(SCRIPT), str(source), str(html_output), "--text-output", str(source)],
            ):
                completed = subprocess.run(command, text=True, capture_output=True)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("collision", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)
            alias = Path(directory) / "source-alias.html"; alias.symlink_to(source)
            completed = subprocess.run([sys.executable, str(SCRIPT), str(source), str(alias)], text=True, capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("collision", completed.stderr)
            for command in (
                [sys.executable, str(SCRIPT), str(source), str(Path(directory) / "SOURCE.JSON")],
                [sys.executable, str(SCRIPT), str(source), str(html_output), "--text-output", str(Path(directory) / "REPORT.HTML")],
                [sys.executable, str(SCRIPT), str(source), str(Path(directory) / unicodedata.normalize("NFC", "résumé.html")), "--text-output", str(Path(directory) / unicodedata.normalize("NFD", "résumé.html"))],
            ):
                completed = subprocess.run(command, text=True, capture_output=True)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("collision", completed.stderr)
            html_output.write_bytes(b"existing html")
            failed = subprocess.run([sys.executable, str(SCRIPT), str(source), str(html_output), "--text-output", str(Path(directory) / "missing" / "report.txt")], text=True, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(html_output.read_bytes(), b"existing html")
            success = subprocess.run([sys.executable, str(SCRIPT), str(source), str(html_output), "--text-output", str(text_output)], text=True, capture_output=True)
            self.assertEqual(success.returncode, 0, success.stderr)
            for output in (html_output, text_output):
                content = output.read_bytes()
                self.assertTrue(content.endswith(b"\n"))
                self.assertFalse(content.endswith(b"\n\n"))

    def test_atomic_writer_restores_existing_outputs_after_second_replace_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            html_output = Path(directory) / "report.html"; text_output = Path(directory) / "report.txt"
            html_output.write_bytes(b"before html"); text_output.write_bytes(b"before text")
            original_replace = self.renderer.os.replace
            failed = {"done": False}

            def fail_second_stage(source, destination):
                if destination == text_output and ".qc-report-stage-" in Path(source).name and not failed["done"]:
                    failed["done"] = True
                    raise OSError("second replace fails")
                return original_replace(source, destination)

            with mock.patch.object(self.renderer.os, "replace", side_effect=fail_second_stage):
                with self.assertRaises(OSError):
                    self.renderer._write_outputs_atomically({html_output: b"new html\n", text_output: b"new text\n"})
            self.assertEqual(html_output.read_bytes(), b"before html")
            self.assertEqual(text_output.read_bytes(), b"before text")

    def test_atomic_writer_surfaces_failed_rollback_with_affected_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            html_output = Path(directory) / "report.html"; text_output = Path(directory) / "report.txt"
            html_output.write_bytes(b"before html"); text_output.write_bytes(b"before text")
            original_replace = self.renderer.os.replace

            def fail_commit_and_restore(source, destination):
                source_name = Path(source).name
                if destination == text_output and ".qc-report-stage-" in source_name:
                    raise OSError("second replace fails")
                if destination == html_output and ".qc-report-backup-" in source_name:
                    raise OSError("backup restore fails")
                return original_replace(source, destination)

            with mock.patch.object(self.renderer.os, "replace", side_effect=fail_commit_and_restore):
                with self.assertRaisesRegex(OSError, "rollback failed; outputs may be inconsistent") as raised:
                    self.renderer._write_outputs_atomically({html_output: b"new html\n", text_output: b"new text\n"})
            self.assertIn(str(html_output), str(raised.exception))
            self.assertEqual(html_output.read_bytes(), b"new html\n")
            self.assertEqual(text_output.read_bytes(), b"before text")

    def test_cli_reports_rollback_warning_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"; output = Path(directory) / "report.html"
            source.write_text(json.dumps(self.report, ensure_ascii=True), encoding="utf-8")
            stream = io.StringIO()
            with mock.patch.object(self.renderer, "_write_outputs_atomically", side_effect=OSError("second replace fails; rollback failed; outputs may be inconsistent: /tmp/report.html")), redirect_stderr(stream):
                result = self.renderer.main([str(source), str(output)])
            self.assertEqual(result, 1)
            self.assertIn("rollback failed; outputs may be inconsistent", stream.getvalue())
            self.assertNotIn("Traceback", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
