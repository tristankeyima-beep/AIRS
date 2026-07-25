import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "acceptance-cases.json"
BUILDER = ROOT / "build_acceptance_html.py"

EXPECTED_GENERATED_FILE = "慢特病认定标准与审核质控-验收测试用例.html"
EXPECTED_METADATA = {
    "catalogVersion": "2026.07.25.1",
    "title": "门诊慢特病认定标准与智能审核质控验收测试用例",
    "description": "模式1、模式2、交互关口和安全产物的离线人工验收用例集",
    "generatedFile": EXPECTED_GENERATED_FILE,
}
SENSITIVE_DUPLICATE_KEY = "敏感业务字段_患者身份证号_DO_NOT_ECHO"
SENSITIVE_RECURSIVE_VALUE = "敏感业务内容_患者病历_DO_NOT_ECHO"
VALID_CATALOG = {**EXPECTED_METADATA, "cases": []}
CASE_FIELDS = {
    "id",
    "title",
    "mode",
    "category",
    "priority",
    "inputKinds",
    "objective",
    "preconditions",
    "inputs",
    "steps",
    "expectedOutcome",
    "mustContain",
    "mustNotContain",
    "acceptanceChecks",
    "notes",
}
INPUT_FIELDS = {"name", "format", "content"}
STEP_FIELDS = {"actor", "action", "expected"}
EXPECTED_IDS = (
    tuple(f"M1-{number:03d}" for number in range(1, 13))
    + tuple(f"M2-{number:03d}" for number in range(1, 17))
    + tuple(f"GATE-{number:03d}" for number in range(1, 7))
    + tuple(f"SAFE-{number:03d}" for number in range(1, 7))
)
CASE_CLASSIFICATION_MATRIX = {
    "M1-001": ("mode1", "formal-example", "P0"),
    "M1-002": ("mode1", "logic-clarification", "P0"),
    "M1-003": ("mode1", "metadata", "P0"),
    "M1-004": ("mode1", "approval-gate", "P0"),
    "M1-005": ("mode1", "structured-standard", "P1"),
    "M1-006": ("mode1", "schema-completeness", "P1"),
    "M1-007": ("mode1", "duplicate-key", "P0"),
    "M1-008": ("mode1", "input-normalization", "P1"),
    "M1-009": ("mode1", "code-validation", "P1"),
    "M1-010": ("mode1", "topology-validation", "P0"),
    "M1-011": ("mode1", "recursion-limit", "P0"),
    "M1-012": ("mode1", "source-conflict", "P0"),
    "M2-001": ("mode2", "audit-correctness", "P0"),
    "M2-002": ("mode2", "false-missing", "P0"),
    "M2-003": ("mode2", "true-missing", "P0"),
    "M2-004": ("mode2", "evidence-reversal", "P0"),
    "M2-005": ("mode2", "negation", "P0"),
    "M2-006": ("mode2", "uncertainty", "P0"),
    "M2-007": ("mode2", "recommendation-inference", "P0"),
    "M2-008": ("mode2", "internal-contradiction", "P0"),
    "M2-009": ("mode2", "and-logic", "P0"),
    "M2-010": ("mode2", "or-logic", "P0"),
    "M2-011": ("mode2", "rule-maintenance", "P1"),
    "M2-012": ("mode2", "ambiguous-standard", "P0"),
    "M2-013": ("mode2", "limited-qc", "P1"),
    "M2-014": ("mode2", "temporary-interpretation", "P1"),
    "M2-015": ("mode2", "full-qc", "P0"),
    "M2-016": ("mode2", "incomplete-input", "P0"),
    "GATE-001": ("gate", "initial-inventory", "P0"),
    "GATE-002": ("gate", "revision", "P0"),
    "GATE-003": ("gate", "invalid-confirmation", "P0"),
    "GATE-004": ("gate", "valid-confirmation", "P0"),
    "GATE-005": ("gate", "blind-review", "P0"),
    "GATE-006": ("gate", "non-blind-review", "P0"),
    "SAFE-001": ("safety", "prompt-injection", "P0"),
    "SAFE-002": ("safety", "secret-handling", "P0"),
    "SAFE-003": ("safety", "network-isolation", "P0"),
    "SAFE-004": ("safety", "offline-html", "P0"),
    "SAFE-005": ("safety", "safe-output", "P0"),
    "SAFE-006": ("safety", "artifact-consistency", "P1"),
}


def load_builder_module():
    if not BUILDER.is_file():
        raise AssertionError(f"missing builder: {BUILDER.name}")
    spec = importlib.util.spec_from_file_location("build_acceptance_html", BUILDER)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER_MODULE = load_builder_module()


class AcceptanceCatalogTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self._temp_dir.name)

    def tearDown(self):
        self._temp_dir.cleanup()

    def write_catalog(self, value):
        path = self.temp_path / "catalog.json"
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def run_cli(self, catalog=None):
        command = [sys.executable, str(BUILDER)]
        if catalog is not None:
            command.extend(["--catalog", str(catalog)])
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_repository_catalog_locks_metadata_and_list_contract(self):
        loaded = BUILDER_MODULE.load_catalog(CATALOG)

        self.assertEqual(
            {field: loaded[field] for field in EXPECTED_METADATA},
            EXPECTED_METADATA,
        )
        self.assertIsInstance(loaded["cases"], list)

    def test_repository_catalog_has_exact_ordered_case_ids(self):
        cases = BUILDER_MODULE.load_catalog(CATALOG)["cases"]

        self.assertEqual(len(cases), 40)
        self.assertEqual(tuple(case["id"] for case in cases), EXPECTED_IDS)
        self.assertEqual(set(CASE_CLASSIFICATION_MATRIX), set(EXPECTED_IDS))

    def test_repository_cases_have_exact_fields_and_value_types(self):
        cases = BUILDER_MODULE.load_catalog(CATALOG)["cases"]

        for case in cases:
            with self.subTest(case=case.get("id")):
                self.assertEqual(set(case), CASE_FIELDS)
                self.assertIn(case["mode"], {"mode1", "mode2", "gate", "safety"})
                self.assertIn(case["priority"], {"P0", "P1", "P2"})
                for field in (
                    "id",
                    "title",
                    "category",
                    "objective",
                    "expectedOutcome",
                    "notes",
                ):
                    self.assertIsInstance(case[field], str)
                    self.assertTrue(case[field].strip(), field)
                for field in (
                    "inputKinds",
                    "preconditions",
                    "inputs",
                    "steps",
                    "mustContain",
                    "mustNotContain",
                    "acceptanceChecks",
                ):
                    self.assertIsInstance(case[field], list)
                    self.assertTrue(case[field], field)
                for field in (
                    "inputKinds",
                    "preconditions",
                    "mustContain",
                    "mustNotContain",
                    "acceptanceChecks",
                ):
                    self.assertTrue(
                        all(isinstance(item, str) and item.strip() for item in case[field])
                    )
                for item in case["inputs"]:
                    self.assertEqual(set(item), INPUT_FIELDS)
                    self.assertTrue(
                        all(
                            isinstance(item[field], str) and item[field].strip()
                            for field in INPUT_FIELDS
                        )
                    )
                for step in case["steps"]:
                    self.assertEqual(set(step), STEP_FIELDS)
                    self.assertTrue(
                        all(
                            isinstance(step[field], str) and step[field].strip()
                            for field in STEP_FIELDS
                        )
                    )

    def test_repository_cases_match_independent_classification_matrix(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }

        for case_id, expected_fields in CASE_CLASSIFICATION_MATRIX.items():
            with self.subTest(case=case_id):
                case = cases[case_id]
                self.assertEqual(
                    (case["mode"], case["category"], case["priority"]),
                    expected_fields,
                )

    def test_m1_001_preserves_logic_and_confirmation_gate_by_field(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        case = cases["M1-001"]

        self.assertEqual(
            case["inputs"][0]["content"],
            "病种名脑梗死；病种编码 CS10；版本 V20260725。顶层 AND："
            "第一条“临床出现相应的脑部神经系统症状及体征，二级及以上医疗机构"
            "诊断为脑梗死(脑栓塞)，住院治疗后仍遗有神经症状及体征需继续治疗”；"
            "第二条“影像学检查提示脑梗死(脑栓塞)灶或颅内、颅外血管中重度狭窄”，"
            "第二条内部必须保留 OR。",
        )
        self.assertEqual(
            [step["actor"] for step in case["steps"]],
            ["系统", "用户", "系统"],
        )
        self.assertEqual(
            case["steps"][0],
            {
                "actor": "系统",
                "action": "解析来源并先展示提案，说明顶层 AND、第二条内部 OR 和元数据。",
                "expected": "仅展示可审阅提案，不生成正式产物。",
            },
        )
        self.assertEqual(
            case["steps"][1]["action"],
            "审阅提案后给出用户明确同意。",
        )
        self.assertEqual(
            case["steps"][2]["action"],
            "在有效确认后生成正式 JSON/HTML。",
        )
        self.assertEqual(
            case["mustNotContain"],
            ["未确认即生成", "第二条改为 AND"],
        )

    def test_critical_mode2_cases_lock_fact_verdict_qc_and_risk_relations(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        expected = {
            "M2-001": {
                "input": "【合成测试数据】测试病种标准为条件A；材料明确满足条件A；审核通过并引用对应原文。",
                "review": "独立复核确认条件A满足。",
                "comparison": "判定审核可靠、无风险、issues=[]。",
                "outcome": "正确质控结论=审核可靠；风险方向=无风险；issues=[]。",
                "must": {"可靠", "无风险", "issues=[]"},
                "must_not": {"错误放行风险", "错误拒绝风险"},
            },
            "M2-002": {
                "input": "【合成测试数据】标准要求条件A；材料第2段明确记载条件A；审核却声称缺少条件A并拒绝。",
                "review": "确认材料其实有该证据。",
                "comparison": "判定审核不可靠并标注错误拒绝风险。",
                "outcome": "正确质控结论=审核不可靠；材料存在却被原审核报缺失；风险方向=错误拒绝风险。",
                "must": {"材料其实有", "不可靠", "错误拒绝风险"},
                "must_not": {"错误放行风险", "维持缺失结论"},
            },
            "M2-009": {
                "input": "【合成测试数据】测试病种标准为 A AND B；材料只有 A，没有 B；审核却通过。",
                "review": "因 B 不满足而得到不通过。",
                "comparison": "标注错误放行风险。",
                "outcome": "正确质控结论=原审核不可靠；材料只有 A，不满足 A AND B；原审核通过造成错误放行风险。",
                "must": {"A AND B", "只有 A", "错误放行风险"},
                "must_not": {"错误拒绝风险", "A 单独足够"},
            },
            "M2-010": {
                "input": "【合成测试数据】测试病种标准为 A OR B；材料满足 A、不满足 B；审核因 B 不满足而拒绝。",
                "review": "因满足 A 而得到通过。",
                "comparison": "标注错误拒绝风险。",
                "outcome": "正确质控结论=原审核不可靠；材料满足 A，已满足 A OR B；原审核拒绝造成错误拒绝风险。",
                "must": {"A OR B", "满足 A", "错误拒绝风险"},
                "must_not": {"错误放行风险", "必须同时满足 B"},
            },
        }

        for case_id, semantic_fields in expected.items():
            with self.subTest(case=case_id):
                case = cases[case_id]
                self.assertEqual(
                    case["inputs"][0]["content"],
                    semantic_fields["input"],
                )
                self.assertEqual(
                    case["steps"][0]["expected"],
                    semantic_fields["review"],
                )
                self.assertEqual(
                    case["steps"][1]["expected"],
                    semantic_fields["comparison"],
                )
                self.assertEqual(
                    case["expectedOutcome"],
                    semantic_fields["outcome"],
                )
                self.assertTrue(
                    semantic_fields["must"].issubset(case["mustContain"])
                )
                self.assertTrue(
                    semantic_fields["must_not"].issubset(case["mustNotContain"])
                )

    def test_gate_002_binds_revision_hash_and_rechecks_before_execution(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        case = cases["GATE-002"]

        self.assertEqual(
            case["inputs"][0]["content"],
            "【合成测试数据】补传前清单 catalogRevision=1、"
            "catalogHash=sha256(TEST_CATALOG_R1)；用户补传测试标准文件。",
        )
        self.assertEqual(
            case["steps"][1],
            {
                "actor": "系统",
                "action": "修订输入清单并将 catalogRevision 递增至 2；按确定性序列化结果"
                "计算新的 catalogHash；更新摘要并请求重新确认。",
                "expected": "新 catalogHash 与补传前不同，关口保持关闭。",
            },
        )
        self.assertEqual(
            case["steps"][2],
            {
                "actor": "用户",
                "action": "确认 catalogRevision=2 和对应 catalogHash 的清单与摘要。",
                "expected": "确认记录同时绑定 catalogRevision=2 与 catalogHash。",
            },
        )
        self.assertEqual(
            case["steps"][3],
            {
                "actor": "系统",
                "action": "执行前比较当前输入的 catalogRevision/catalogHash 与确认记录。",
                "expected": "两者全部一致才执行；任一不一致不得执行并须重新确认。",
            },
        )
        self.assertEqual(
            case["expectedOutcome"],
            "补传后的清单、确定性摘要哈希与确认记录形成闭环：catalogRevision 和 "
            "catalogHash 匹配才执行，不匹配则重新确认。",
        )
        self.assertEqual(
            case["acceptanceChecks"],
            [
                "确认补传后 catalogRevision 递增且新的确定性 catalogHash 随清单变化",
                "确认记录同时绑定 catalogRevision 与 catalogHash",
                "执行前校验当前 revision/hash 与确认记录；不一致时拒绝执行并重新确认",
            ],
        )

    def test_repository_cases_mark_synthetic_data_and_required_branches(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        for case_id in EXPECTED_IDS:
            if case_id != "M1-001":
                for item in cases[case_id]["inputs"]:
                    self.assertIn("【合成测试数据】", item["content"])

        branch_actions = [
            step["action"]
            for step in cases["M2-016"]["steps"]
        ]
        branch_expected = [
            step["expected"]
            for step in cases["M2-016"]["steps"]
        ]
        self.assertIn("分支一：补传材料02。", branch_actions)
        self.assertIn("分支二：明确“确认没有更多内容”。", branch_actions)
        self.assertIn(
            "系统执行“补传后修订清单/摘要再确认”，递增 revision 后仍不直接质控。",
            branch_expected,
        )
        raw = CATALOG.read_text(encoding="utf-8")
        self.assertNotIn("可能错误通过", raw)
        self.assertNotIn("可能错误不通过", raw)

    def test_repository_catalog_is_deterministically_formatted(self):
        raw = CATALOG.read_text(encoding="utf-8")
        loaded = json.loads(raw)

        self.assertEqual(raw, json.dumps(loaded, ensure_ascii=False, indent=2) + "\n")

    def test_repository_catalog_has_no_forbidden_platform_name(self):
        forbidden = "".join(chr(code) for code in (100, 105, 102, 121))
        raw = CATALOG.read_text(encoding="utf-8").casefold()

        self.assertNotIn(forbidden, raw)

    def test_valid_root_contract(self):
        loaded = BUILDER_MODULE.load_catalog(
            self.write_catalog(VALID_CATALOG)
        )

        self.assertEqual(loaded, VALID_CATALOG)
        self.assertEqual(set(loaded), BUILDER_MODULE.ROOT_FIELDS)
        self.assertIsInstance(loaded["cases"], list)

    def test_duplicate_key_is_rejected_at_any_depth(self):
        path = self.temp_path / "catalog.json"
        path.write_text(
            """
            {
              "catalogVersion": "2026.07.25.1",
              "title": "title",
              "description": "description",
              "generatedFile": "慢特病认定标准与审核质控-验收测试用例.html",
              "cases": [
                {
                  "steps": [
                    {
                      "__SENSITIVE_DUPLICATE_KEY__": "one",
                      "__SENSITIVE_DUPLICATE_KEY__": "two"
                    }
                  ]
                }
              ]
            }
            """.replace(
                "__SENSITIVE_DUPLICATE_KEY__",
                SENSITIVE_DUPLICATE_KEY,
            ),
            encoding="utf-8",
        )

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(path)

        self.assertEqual(str(caught.exception), "duplicate_json_key")
        self.assertNotIn(SENSITIVE_DUPLICATE_KEY, str(caught.exception))

    def test_root_fields_must_be_exact(self):
        values = []
        with_unknown = dict(VALID_CATALOG)
        with_unknown["unexpected"] = "private-business-content"
        values.append(("unknown-field", with_unknown))
        without_title = dict(VALID_CATALOG)
        without_title.pop("title")
        values.append(("missing-field", without_title))

        for label, value in values:
            with self.subTest(label=label):
                with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                    BUILDER_MODULE.load_catalog(self.write_catalog(value))
                self.assertNotIn(
                    "private-business-content",
                    str(caught.exception),
                )

    def test_cases_must_be_an_array(self):
        value = dict(
            VALID_CATALOG,
            cases={"content": "private-business-content"},
        )

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(self.write_catalog(value))

        self.assertNotIn("private-business-content", str(caught.exception))

    def test_catalog_version_must_use_ascii_contract(self):
        versions = [
            "",
            "2026.7.25.1",
            "v2026.07.25.1",
            "2026.07.25",
            "２０２６.０７.２５.１",
        ]
        for version in versions:
            with self.subTest(version=version):
                value = dict(VALID_CATALOG, catalogVersion=version)
                with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                    BUILDER_MODULE.load_catalog(self.write_catalog(value))
                if version:
                    self.assertNotIn(version, str(caught.exception))

    def test_generated_file_must_match_contract(self):
        wrong_name = "private-business-content.html"
        value = dict(VALID_CATALOG, generatedFile=wrong_name)

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(self.write_catalog(value))

        self.assertNotIn(wrong_name, str(caught.exception))

    def test_required_text_fields_must_be_non_empty_strings(self):
        invalid_values = {
            "title": "",
            "description": [],
            "generatedFile": "",
        }
        for field, invalid_value in invalid_values.items():
            with self.subTest(field=field):
                value = dict(VALID_CATALOG)
                value[field] = invalid_value
                with self.assertRaises(BUILDER_MODULE.CatalogError):
                    BUILDER_MODULE.load_catalog(self.write_catalog(value))

    def test_invalid_utf8_is_a_controlled_error(self):
        path = self.temp_path / "catalog.json"
        path.write_bytes(b"\xff\xfeprivate-business-content")

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(path)

        self.assertNotIn(
            "private-business-content",
            str(caught.exception),
        )

    def test_invalid_json_is_a_controlled_error_without_echo(self):
        path = self.temp_path / "catalog.json"
        path.write_text(
            '{"title": "private-business-content"',
            encoding="utf-8",
        )

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(path)

        self.assertEqual(str(caught.exception), "catalog_json_error")
        self.assertNotIn(
            "private-business-content",
            str(caught.exception),
        )

    def test_deeply_nested_json_is_a_controlled_error_without_echo(self):
        path = self.temp_path / "catalog.json"
        nested = (
            "[" * 10_000
            + json.dumps(SENSITIVE_RECURSIVE_VALUE, ensure_ascii=False)
            + "]" * 10_000
        )
        path.write_text(nested, encoding="utf-8")

        try:
            BUILDER_MODULE.load_catalog(path)
        except BUILDER_MODULE.CatalogError as error:
            caught = error
        except RecursionError:
            self.fail("deeply nested JSON leaked RecursionError")
        else:
            self.fail("deeply nested JSON was accepted")

        self.assertEqual(str(caught), "catalog_json_error")
        self.assertNotIn(SENSITIVE_RECURSIVE_VALUE, str(caught))

    def test_missing_file_is_a_controlled_error(self):
        missing = self.temp_path / "private-business-content.json"

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(missing)

        self.assertNotIn(
            "private-business-content",
            str(caught.exception),
        )

    def test_cli_success(self):
        result = self.run_cli(CATALOG)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "catalog_valid")
        self.assertEqual(result.stderr, "")

    def test_cli_catalog_error_is_generic_and_has_no_traceback(self):
        invalid = self.temp_path / "private-business-content.json"
        invalid.write_text("private-business-content", encoding="utf-8")

        result = self.run_cli(invalid)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "catalog_error")
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("private-business-content", result.stderr)

    def test_cli_duplicate_key_error_does_not_echo_sensitive_key(self):
        invalid = self.temp_path / "duplicate.json"
        invalid.write_text(
            """
            {
              "catalogVersion": "2026.07.25.1",
              "title": "title",
              "description": "description",
              "generatedFile": "慢特病认定标准与审核质控-验收测试用例.html",
              "cases": [
                {
                  "__SENSITIVE_DUPLICATE_KEY__": "one",
                  "__SENSITIVE_DUPLICATE_KEY__": "two"
                }
              ]
            }
            """.replace(
                "__SENSITIVE_DUPLICATE_KEY__",
                SENSITIVE_DUPLICATE_KEY,
            ),
            encoding="utf-8",
        )

        result = self.run_cli(invalid)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "catalog_error")
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn(SENSITIVE_DUPLICATE_KEY, result.stdout)
        self.assertNotIn(SENSITIVE_DUPLICATE_KEY, result.stderr)

    def test_cli_deeply_nested_json_is_generic_without_traceback(self):
        invalid = self.temp_path / "recursive.json"
        nested = (
            "[" * 10_000
            + json.dumps(SENSITIVE_RECURSIVE_VALUE, ensure_ascii=False)
            + "]" * 10_000
        )
        invalid.write_text(nested, encoding="utf-8")

        result = self.run_cli(invalid)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "catalog_error")
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn(SENSITIVE_RECURSIVE_VALUE, result.stdout)
        self.assertNotIn(SENSITIVE_RECURSIVE_VALUE, result.stderr)

    def test_cli_argument_error_exits_two_without_traceback(self):
        result = self.run_cli()

        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
