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
CASE_MATRIX = {
    "M1-001": ("mode1", "formal-example", "P0", ("脑梗死", "CS10", "V20260725", "提案", "明确同意", "OR")),
    "M1-002": ("mode1", "logic-clarification", "P0", ("歧义", "询问", "未确认")),
    "M1-003": ("mode1", "metadata", "P0", ("病种名", "病种编码", "版本", "回退", "记录")),
    "M1-004": ("mode1", "approval-gate", "P0", ("尚未同意", "不得", "正式")),
    "M1-005": ("mode1", "structured-standard", "P1", ("完整结构化标准", "校验", "生成")),
    "M1-006": ("mode1", "schema-completeness", "P1", ("extractionGuides", "enums", "补齐")),
    "M1-007": ("mode1", "duplicate-key", "P0", ("深层重复键", "受控拒绝", "不回显")),
    "M1-008": ("mode1", "input-normalization", "P1", ("代码围栏", "字符串包装", "BOM", "规范处理")),
    "M1-009": ("mode1", "code-validation", "P1", ("ruleCode", "guideCode", "格式错误")),
    "M1-010": ("mode1", "topology-validation", "P0", ("引用不存在", "未被引用")),
    "M1-011": ("mode1", "recursion-limit", "P0", ("循环引用", "逻辑深度超限")),
    "M1-012": ("mode1", "source-conflict", "P0", ("语义冲突", "列出冲突", "询问")),
    "M2-001": ("mode2", "audit-correctness", "P0", ("可靠", "无风险", "issues=[]")),
    "M2-002": ("mode2", "false-missing", "P0", ("材料其实有", "不可靠", "错误拒绝风险")),
    "M2-003": ("mode2", "true-missing", "P0", ("材料确实缺失", "指出缺失", "正确")),
    "M2-004": ("mode2", "evidence-reversal", "P0", ("证据", "原文", "含义相反")),
    "M2-005": ("mode2", "negation", "P0", ("否定句", "肯定事实", "不可靠")),
    "M2-006": ("mode2", "uncertainty", "P0", ("疑似", "确诊", "过度推断")),
    "M2-007": ("mode2", "recommendation-inference", "P0", ("建议进一步评估", "已完成", "过度推断")),
    "M2-008": ("mode2", "internal-contradiction", "P0", ("条件状态", "最终建议", "矛盾")),
    "M2-009": ("mode2", "and-logic", "P0", ("A AND B", "只有 A", "错误放行风险")),
    "M2-010": ("mode2", "or-logic", "P0", ("A OR B", "满足 A", "错误拒绝风险")),
    "M2-011": ("mode2", "rule-maintenance", "P1", ("extractionGuides", "缺提取项", "维护质量")),
    "M2-012": ("mode2", "ambiguous-standard", "P0", ("不同解释路径", "不得", "唯一结论")),
    "M2-013": ("mode2", "limited-qc", "P1", ("无标准", "有限质控", "未执行项")),
    "M2-014": ("mode2", "temporary-interpretation", "P1", ("自然语言标准", "临时解释", "不得冒充")),
    "M2-015": ("mode2", "full-qc", "P0", ("完整结构化标准", "详细审核结果", "五维质控")),
    "M2-016": ("mode2", "incomplete-input", "P0", ("可能漏传", "补传后修订清单", "确认没有更多内容", "有限质控")),
    "GATE-001": ("gate", "initial-inventory", "P0", ("首次", "输入清单", "不直接执行")),
    "GATE-002": ("gate", "revision", "P0", ("补传", "revision", "更新摘要", "重新确认")),
    "GATE-003": ("gate", "invalid-confirmation", "P0", ("无效", "含糊确认", "不得放行")),
    "GATE-004": ("gate", "valid-confirmation", "P0", ("明确有效确认", "放行")),
    "GATE-005": ("gate", "blind-review", "P0", ("独立复核", "看到原审核结果前", "冻结摘要")),
    "GATE-006": ("gate", "non-blind-review", "P0", ("非盲审", "披露限制", "不能伪装")),
    "SAFE-001": ("safety", "prompt-injection", "P0", ("提示注入", "普通证据文本", "不执行")),
    "SAFE-002": ("safety", "secret-handling", "P0", ("疑似密钥", "fail-closed", "不得回显", "明显假的占位符")),
    "SAFE-003": ("safety", "network-isolation", "P0", ("外部网络", "第三方服务", "不发送")),
    "SAFE-004": ("safety", "offline-html", "P0", ("HTML 转义", "无外链依赖", "离线打开")),
    "SAFE-005": ("safety", "safe-output", "P0", ("路径别名", "硬链接", "符号链接", "原子写失败")),
    "SAFE-006": ("safety", "artifact-consistency", "P1", ("文本版", "HTML", "同源一致", "大输入", "窄屏")),
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
        self.assertEqual(set(CASE_MATRIX), set(EXPECTED_IDS))

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

    def test_repository_cases_match_independent_semantic_matrix(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }

        for case_id, (mode, category, priority, required_terms) in CASE_MATRIX.items():
            with self.subTest(case=case_id):
                case = cases[case_id]
                self.assertEqual(case["mode"], mode)
                self.assertEqual(case["category"], category)
                self.assertEqual(case["priority"], priority)
                searchable = json.dumps(case, ensure_ascii=False)
                for term in required_terms:
                    self.assertIn(term, searchable)

    def test_repository_cases_lock_critical_p0_facts(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }

        formal = json.dumps(cases["M1-001"], ensure_ascii=False)
        self.assertIn("顶层 AND", formal)
        self.assertIn(
            "临床出现相应的脑部神经系统症状及体征，二级及以上医疗机构诊断为脑梗死(脑栓塞)，住院治疗后仍遗有神经症状及体征需继续治疗",
            formal,
        )
        self.assertIn(
            "影像学检查提示脑梗死(脑栓塞)灶或颅内、颅外血管中重度狭窄",
            formal,
        )
        self.assertLess(formal.index("先展示提案"), formal.index("用户明确同意"))
        self.assertLess(formal.index("用户明确同意"), formal.index("正式 JSON/HTML"))

        for case_id in EXPECTED_IDS:
            if case_id != "M1-001":
                self.assertIn(
                    "【合成测试数据】",
                    json.dumps(cases[case_id], ensure_ascii=False),
                )

        m2_016_steps = json.dumps(cases["M2-016"]["steps"], ensure_ascii=False)
        self.assertIn("补传后修订清单/摘要再确认", m2_016_steps)
        self.assertIn("确认没有更多内容", m2_016_steps)
        self.assertNotIn("可能错误通过", json.dumps(cases, ensure_ascii=False))
        self.assertNotIn("可能错误不通过", json.dumps(cases, ensure_ascii=False))

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
