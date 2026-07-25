import importlib.util
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "acceptance-cases.json"
BUILDER = ROOT / "build_acceptance_html.py"
QC_RENDERER_PATH = (
    ROOT.parent
    / "chronic-disease-certification-qc"
    / "scripts"
    / "render_qc_html.py"
)

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
PLAIN_TEXT_CASES = {
    "M1-001",
    "M1-002",
    "M1-003",
    "SAFE-001",
    "SAFE-004",
}
JSON_CASE_KEYS = {
    "M1-004": {"synthetic", "revision", "status", "proposal"},
    "M1-005": {
        "synthetic",
        "diseaseName",
        "diseaseCode",
        "version",
        "rules",
        "extractionGuides",
        "enums",
        "logic",
    },
    "M1-006": {
        "synthetic",
        "diseaseName",
        "diseaseCode",
        "version",
        "rules",
        "extractionGuides",
        "enums",
        "logic",
    },
    "M1-009": {"synthetic", "diseaseName", "rules", "extractionGuides"},
    "M1-010": {"synthetic", "diseaseName", "rules", "logic"},
    "M2-008": {"synthetic", "standard", "conditionResults", "finalRecommendation"},
    "M2-015": {"synthetic", "materials", "standard", "auditResult"},
    "GATE-002": {"synthetic", "before", "supplement", "after"},
    "GATE-003": {"synthetic", "invalidStatements"},
    "GATE-004": {"synthetic", "userStatement"},
    "GATE-005": {"synthetic", "tempRoot", "stages", "cleanup"},
    "GATE-006": {
        "synthetic",
        "visibilityHistory",
        "reviewMode",
        "disclosure",
    },
    "SAFE-002": {"synthetic", "rawInput"},
    "SAFE-003": {"synthetic", "tempRoot", "networkPolicy", "files", "cleanup"},
    "SAFE-005": {
        "synthetic",
        "tempRoot",
        "fixtures",
        "failureInjection",
        "cleanup",
    },
    "SAFE-006": {"synthetic", "generator", "viewports", "assertions"},
}
BUNDLE_CASE_FILES = {
    "M1-011": {"cycle.json", "depth.json"},
    "M1-012": {"source-a.txt", "source-b.txt"},
    "M2-001": {"materials.txt", "standard.txt", "audit-result.json"},
    "M2-002": {"materials.txt", "standard.txt", "audit-result.json"},
    "M2-003": {"materials.txt", "standard.txt", "audit-result.json"},
    "M2-004": {"materials.txt", "standard.txt", "audit-result.json"},
    "M2-005": {"materials.txt", "standard.txt", "audit-result.json"},
    "M2-006": {"materials.txt", "standard.txt", "audit-result.json"},
    "M2-007": {"materials.txt", "standard.txt", "audit-result.json"},
    "M2-009": {"materials.txt", "standard.txt", "audit-result.json"},
    "M2-010": {"materials.txt", "standard.txt", "audit-result.json"},
    "M2-011": {"materials.txt", "standard.json", "audit-result.json"},
    "M2-012": {"materials.txt", "standard.txt", "audit-result.json"},
    "M2-013": {"materials.txt", "audit-result.json"},
    "M2-014": {"materials.txt", "standard.txt", "audit-result.json"},
    "M2-016": {
        "inventory.json",
        "material-01.txt",
        "material-03.txt",
        "audit-result.json",
    },
    "GATE-001": {"materials.txt", "audit-result.json"},
}
BUNDLE_JSON_REQUIRED_KEYS = {
    ("M1-011", "cycle.json"): {"synthetic", "rootNode", "nodes"},
    ("M1-011", "depth.json"): {"synthetic", "maxDepth", "logic"},
    ("M2-001", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "claims",
        "finalRecommendation",
    },
    ("M2-002", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "claims",
        "finalRecommendation",
    },
    ("M2-003", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "claims",
        "finalRecommendation",
    },
    ("M2-004", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "claims",
        "finalRecommendation",
    },
    ("M2-005", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "claims",
        "finalRecommendation",
    },
    ("M2-006", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "claims",
        "finalRecommendation",
    },
    ("M2-007", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "claims",
        "finalRecommendation",
    },
    ("M2-009", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "conditionResults",
        "finalRecommendation",
    },
    ("M2-010", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "conditionResults",
        "rejectionReason",
        "finalRecommendation",
    },
    ("M2-011", "standard.json"): {
        "synthetic",
        "diseaseName",
        "rules",
        "extractionItems",
        "extractionGuides",
    },
    ("M2-011", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "conditionResults",
        "finalRecommendation",
    },
    ("M2-012", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "conditionResults",
        "finalRecommendation",
    },
    ("M2-013", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "auditResultKind",
        "finalRecommendation",
    },
    ("M2-014", "audit-result.json"): {
        "synthetic",
        "originalResult",
        "auditResultKind",
        "visibleClaims",
        "finalRecommendation",
    },
    ("M2-016", "inventory.json"): {
        "synthetic",
        "revision",
        "files",
        "standardKind",
        "referencedButMissing",
    },
    ("M2-016", "audit-result.json"): {
        "synthetic",
        "auditResultKind",
        "visibleClaims",
        "finalRecommendation",
        "references",
    },
    ("GATE-001", "audit-result.json"): {
        "synthetic",
        "auditResultKind",
        "finalRecommendation",
    },
}
SPECIAL_FORMAT_CASES = {
    "M1-007": "重复键 JSON",
    "M1-008": "包装样本 bundle",
}
EXPECTED_INPUT_FORMATS = {
    **{case_id: "UTF-8 纯文本" for case_id in PLAIN_TEXT_CASES},
    **{case_id: "JSON" for case_id in JSON_CASE_KEYS},
    **{case_id: "多文件 bundle" for case_id in BUNDLE_CASE_FILES},
    **SPECIAL_FORMAT_CASES,
}
VAGUE_INPUT_PHRASES = (
    "样本一为",
    "样本二为",
    "分别构造为",
    "均已提供",
    "仅存放在本地",
    "生成大量测试条件",
)


def parse_file_bundle(content):
    header = re.compile(r"^=== FILE: ([^=\r\n]+) ===$", re.MULTILINE)
    matches = list(header.finditer(content))
    if not matches or content[: matches[0].start()].strip():
        raise AssertionError("bundle must start with a file header")
    files = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[start:end].strip("\r\n")
        if not name or name in files or not body.strip():
            raise AssertionError("bundle file names must be unique and bodies non-empty")
        files[name] = body
    return files


def load_builder_module():
    if not BUILDER.is_file():
        raise AssertionError(f"missing builder: {BUILDER.name}")
    spec = importlib.util.spec_from_file_location("build_acceptance_html", BUILDER)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_qc_renderer_module():
    if not QC_RENDERER_PATH.is_file():
        raise AssertionError(f"missing renderer: {QC_RENDERER_PATH.name}")
    spec = importlib.util.spec_from_file_location(
        "acceptance_qc_renderer",
        QC_RENDERER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load QC renderer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER_MODULE = load_builder_module()
QC_RENDERER_MODULE = load_qc_renderer_module()


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

    def test_all_40_inputs_have_an_executable_format_contract(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        bundle_json_files = set()

        self.assertEqual(set(EXPECTED_INPUT_FORMATS), set(EXPECTED_IDS))
        for case_id in EXPECTED_IDS:
            with self.subTest(case=case_id):
                case = cases[case_id]
                self.assertEqual(len(case["inputs"]), 1)
                item = case["inputs"][0]
                self.assertEqual(item["format"], EXPECTED_INPUT_FORMATS[case_id])
                for phrase in VAGUE_INPUT_PHRASES:
                    self.assertNotIn(phrase, item["content"])

                if case_id in PLAIN_TEXT_CASES:
                    self.assertGreaterEqual(len(item["content"]), 30)
                    if case_id != "M1-001":
                        self.assertIn("【合成测试数据】", item["content"])
                elif case_id in JSON_CASE_KEYS:
                    payload = json.loads(item["content"])
                    self.assertEqual(set(payload), JSON_CASE_KEYS[case_id])
                    self.assertIs(payload["synthetic"], True)
                elif case_id in BUNDLE_CASE_FILES:
                    files = parse_file_bundle(item["content"])
                    self.assertEqual(set(files), BUNDLE_CASE_FILES[case_id])
                    for name, body in files.items():
                        if name.endswith(".json"):
                            payload = json.loads(body)
                            self.assertIs(payload["synthetic"], True)
                            bundle_json_files.add((case_id, name))
                            self.assertEqual(
                                set(payload),
                                BUNDLE_JSON_REQUIRED_KEYS[(case_id, name)],
                            )
                        else:
                            self.assertIn("【合成测试数据】", body)
        self.assertEqual(bundle_json_files, set(BUNDLE_JSON_REQUIRED_KEYS))

    def test_m1_005_is_a_complete_parseable_structured_standard(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        standard = json.loads(cases["M1-005"]["inputs"][0]["content"])

        self.assertEqual(standard["diseaseName"], "测试病种")
        self.assertEqual(standard["diseaseCode"], "TEST01")
        self.assertEqual(standard["version"], "V1")
        self.assertEqual(
            {rule["ruleCode"] for rule in standard["rules"]},
            {"R001", "R002"},
        )
        self.assertEqual(
            {guide["guideCode"] for guide in standard["extractionGuides"]},
            {"G001", "G002"},
        )
        self.assertEqual(standard["enums"][0]["enumCode"], "E_BOOL")
        self.assertEqual(standard["logic"]["operator"], "AND")
        self.assertEqual(
            {child["ruleCode"] for child in standard["logic"]["children"]},
            {"R001", "R002"},
        )

    def test_m1_007_contains_a_real_nested_duplicate_key(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        raw = cases["M1-007"]["inputs"][0]["content"]
        duplicate_keys = []

        def preserve_and_record_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    duplicate_keys.append(key)
                result[key] = value
            return result

        parsed = json.loads(raw, object_pairs_hook=preserve_and_record_duplicates)

        self.assertEqual(duplicate_keys, ["SENSITIVE_FIELD"])
        self.assertEqual(parsed["rules"][0]["guides"][0]["SENSITIVE_FIELD"], "two")
        self.assertIn('"SENSITIVE_FIELD": "one"', raw)
        self.assertIn('"SENSITIVE_FIELD": "two"', raw)

    def test_m1_008_contains_three_reproducible_wrapped_json_samples(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        files = parse_file_bundle(cases["M1-008"]["inputs"][0]["content"])

        self.assertEqual(
            set(files),
            {"fenced.txt", "string-wrapped.json", "bom.json"},
        )
        fenced = files["fenced.txt"]
        self.assertTrue(fenced.startswith("```json\n"))
        self.assertTrue(fenced.endswith("\n```"))
        fenced_payload = json.loads(fenced[len("```json\n") : -len("\n```")])
        wrapped_payload = json.loads(json.loads(files["string-wrapped.json"]))
        bom = files["bom.json"]
        self.assertTrue(bom.startswith("\ufeff"))
        bom_payload = json.loads(bom.lstrip("\ufeff"))
        for payload in (fenced_payload, wrapped_payload, bom_payload):
            self.assertEqual(
                payload,
                {
                    "synthetic": True,
                    "diseaseName": "测试病种",
                    "condition": "条件A",
                },
            )

    def test_operational_fixtures_use_synthetic_temp_roots_and_cleanup_steps(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }

        for case_id in ("GATE-005", "SAFE-003", "SAFE-005"):
            with self.subTest(case=case_id):
                fixture = json.loads(cases[case_id]["inputs"][0]["content"])
                self.assertTrue(
                    fixture["tempRoot"].startswith(
                        f"/tmp/chronic-qc-acceptance-{case_id.casefold()}"
                    )
                )
                self.assertIs(fixture["cleanup"]["removeTempRoot"], True)
                actions = [step["action"] for step in cases[case_id]["steps"]]
                self.assertTrue(any("创建" in action for action in actions))
                self.assertTrue(any("清理" in action for action in actions))

        safe_output = json.loads(cases["SAFE-005"]["inputs"][0]["content"])
        self.assertEqual(
            set(safe_output["fixtures"]),
            {
                "input",
                "existingHtml",
                "existingText",
                "pathAlias",
                "hardLink",
                "symbolicLink",
            },
        )
        self.assertEqual(
            safe_output["failureInjection"],
            {
                "operation": "replace_staged_text_output",
                "failOnCall": 2,
                "error": "synthetic replace failure",
            },
        )

        capacity = json.loads(cases["SAFE-006"]["inputs"][0]["content"])
        self.assertGreaterEqual(capacity["generator"]["recordCount"], 2000)
        self.assertEqual(
            {viewport["width"] for viewport in capacity["viewports"]},
            {320, 1440},
        )

    def test_safe_002_fixture_is_detected_without_using_a_real_secret(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        fixture = json.loads(cases["SAFE-002"]["inputs"][0]["content"])

        self.assertEqual(
            fixture["rawInput"]["api_key"],
            "FAKE_TEST_VALUE_12345",
        )
        self.assertTrue(
            QC_RENDERER_MODULE._contains_suspected_secret(
                fixture["rawInput"]
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
                "material": "【合成测试数据】测试病种材料\n条件A：满足。",
                "standard": "【合成测试数据】测试病种标准\nR001：满足条件A。",
                "original_result": "通过",
                "review": "独立复核确认条件A满足。",
                "comparison": "判定审核可靠、未发现明显风险、issues=[]。",
                "outcome": "正确质控结论=审核可靠；风险方向=未发现明显风险；issues=[]。",
                "must": {"可靠", "未发现明显风险", "issues=[]"},
                "must_not": {"错误放行风险", "错误拒绝风险"},
            },
            "M2-002": {
                "material": "【合成测试数据】测试病种材料\n第1段：一般说明。\n第2段：条件A明确满足。",
                "standard": "【合成测试数据】测试病种标准\nR001：满足条件A。",
                "original_result": "拒绝",
                "review": "确认材料其实有该证据。",
                "comparison": "判定审核不可靠并标注错误拒绝风险。",
                "outcome": "正确质控结论=审核不可靠；材料存在却被原审核报缺失；风险方向=错误拒绝风险。",
                "must": {"材料其实有", "不可靠", "错误拒绝风险"},
                "must_not": {"错误放行风险", "维持缺失结论"},
            },
            "M2-009": {
                "material": "【合成测试数据】测试病种材料\n条件A：满足。\n条件B：未提供。",
                "standard": "【合成测试数据】测试病种标准\nR001：A AND B。",
                "original_result": "通过",
                "review": "因 B 不满足而得到不通过。",
                "comparison": "标注错误放行风险。",
                "outcome": "正确质控结论=原审核不可靠；材料只有 A，不满足 A AND B；原审核通过造成错误放行风险。",
                "must": {"A AND B", "只有 A", "错误放行风险"},
                "must_not": {"错误拒绝风险", "A 单独足够"},
            },
            "M2-010": {
                "material": "【合成测试数据】测试病种材料\n条件A：满足。\n条件B：不满足。",
                "standard": "【合成测试数据】测试病种标准\nR001：A OR B。",
                "original_result": "拒绝",
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
                files = parse_file_bundle(case["inputs"][0]["content"])
                audit = json.loads(files["audit-result.json"])
                self.assertEqual(
                    files["materials.txt"],
                    semantic_fields["material"],
                )
                self.assertEqual(
                    files["standard.txt"],
                    semantic_fields["standard"],
                )
                self.assertEqual(audit["originalResult"], semantic_fields["original_result"])
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

        self.assertIn("未发现明显风险", QC_RENDERER_MODULE.ROOT_RISKS)
        self.assertEqual(
            cases["M2-001"]["mustContain"][1],
            "未发现明显风险",
        )

    def test_gate_002_uses_renderer_hashes_and_current_confirmation_fields(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        case = cases["GATE-002"]
        fixture = json.loads(case["inputs"][0]["content"])
        before = fixture["before"]
        after = fixture["after"]

        for phase in (before, after):
            raw_input = phase["rawInput"]
            inventory = phase["inputScope"]["inventory"]
            confirmation = phase["inputScope"]["confirmation"]
            canonical_raw = json.dumps(
                raw_input,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
            canonical_inventory = json.dumps(
                inventory,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
            self.assertEqual(
                inventory["rawInputSha256"],
                hashlib.sha256(canonical_raw).hexdigest(),
            )
            self.assertEqual(
                inventory["rawInputSha256"],
                QC_RENDERER_MODULE.compute_raw_input_sha256(raw_input),
            )
            self.assertEqual(
                confirmation["inventorySha256"],
                hashlib.sha256(canonical_inventory).hexdigest(),
            )
            self.assertEqual(
                confirmation["inventorySha256"],
                QC_RENDERER_MODULE.compute_inventory_sha256(inventory),
            )
            self.assertEqual(
                confirmation["confirmedRevision"],
                inventory["revision"],
            )
            self.assertIn(
                confirmation["userStatement"],
                QC_RENDERER_MODULE.CONFIRMATION_STATEMENTS,
            )

        self.assertEqual(
            after["inputScope"]["inventory"]["revision"],
            before["inputScope"]["inventory"]["revision"] + 1,
        )
        self.assertNotEqual(
            after["inputScope"]["inventory"]["rawInputSha256"],
            before["inputScope"]["inventory"]["rawInputSha256"],
        )
        self.assertNotEqual(
            after["inputScope"]["confirmation"]["inventorySha256"],
            before["inputScope"]["confirmation"]["inventorySha256"],
        )
        step_actions = [step["action"] for step in case["steps"]]
        step_expectations = [step["expected"] for step in case["steps"]]
        self.assertIn("补传后将 inputScope.inventory.revision 加 1，并重新分类、清点和询问。", step_actions)
        self.assertIn("旧 confirmation 失效；重算 rawInputSha256 与 inventorySha256。", step_expectations)
        self.assertIn("仅当当前 revision 与两个摘要均匹配新确认记录时执行。", step_expectations)
        self.assertIn("任一不一致不得执行并须再次询问。", step_expectations)

    def test_gate_confirmation_statements_follow_renderer_allowlist(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        accepted = json.loads(cases["GATE-004"]["inputs"][0]["content"])
        rejected = json.loads(cases["GATE-003"]["inputs"][0]["content"])

        self.assertEqual(accepted["userStatement"], "我确认完整")
        self.assertIn(
            accepted["userStatement"],
            QC_RENDERER_MODULE.CONFIRMATION_STATEMENTS,
        )
        self.assertTrue(
            QC_RENDERER_MODULE._valid_confirmation_statement(
                accepted["userStatement"]
            )
        )
        self.assertIn(
            "我确认 revision 2 清单完整，同意开始执行",
            rejected["invalidStatements"],
        )
        self.assertIn(
            "没有更多内容，立即出报告",
            rejected["invalidStatements"],
        )
        for statement in rejected["invalidStatements"]:
            self.assertFalse(
                QC_RENDERER_MODULE._valid_confirmation_statement(statement)
            )

    def test_m2_016_keeps_both_inventory_confirmation_branches(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
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
