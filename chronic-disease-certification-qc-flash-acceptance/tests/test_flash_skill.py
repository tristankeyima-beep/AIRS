import copy
import json
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "chronic-disease-certification-qc-flash"
ACCEPTANCE_ROOT = REPO_ROOT / "chronic-disease-certification-qc-flash-acceptance"
MODE1_REQUIRED_KEYS = {
    "schemaVersion",
    "mode",
    "meta",
    "sourceDocuments",
    "analysisRecord",
    "rules",
    "logic",
    "confirmation",
}
MODE2_REQUIRED_KEYS = {
    "schemaVersion",
    "mode",
    "meta",
    "inputProfile",
    "sourceDocuments",
    "analysisRecord",
    "baseReview",
    "auditComparison",
    "dimensions",
    "issues",
    "recommendations",
    "confirmation",
}
MODE2_DIMENSIONS = [
    "材料缺失判断准确性",
    "证据提取准确性",
    "过度推理",
    "审核条件与结论一致性",
    "规则维护质量",
]


def read(path):
    return path.read_text(encoding="utf-8")


def embedded_html(template_path, fixture_path):
    template = read(template_path)
    data = json.loads(read(fixture_path))
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    payload = (
        payload.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return template.replace("__FLASH_DATA_JSON__", payload)


def parse_frontmatter(markdown):
    match = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", markdown, re.DOTALL)
    if not match:
        raise AssertionError("SKILL.md must start with YAML frontmatter")

    metadata = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            raise AssertionError(f"invalid frontmatter line: {line}")
        metadata[key.strip()] = value.strip().strip("\"'")
    return metadata


def parse_openai_interface(yaml_text):
    lines = yaml_text.splitlines()
    if not lines or lines[0] != "interface:":
        raise AssertionError("openai.yaml must start with interface:")

    interface = {}
    for line in lines[1:]:
        match = re.fullmatch(r'  ([a-z_]+): "([^"]*)"', line)
        if not match:
            raise AssertionError(f"invalid interface line: {line}")
        key, value = match.groups()
        if key in interface:
            raise AssertionError(f"duplicate interface key: {key}")
        interface[key] = value

    expected_keys = {
        "display_name",
        "short_description",
        "default_prompt",
    }
    if set(interface) != expected_keys:
        raise AssertionError(
            f"interface keys must be exactly {sorted(expected_keys)}"
        )
    return interface


def assert_nonempty_string(test_case, value, path):
    test_case.assertIsInstance(value, str, path)
    test_case.assertTrue(value.strip(), path)


def assert_valid_mode1_fixture(test_case, fixture):
    test_case.assertIsInstance(fixture, dict)
    test_case.assertEqual(MODE1_REQUIRED_KEYS, set(fixture))
    test_case.assertEqual("flash-1.0", fixture["schemaVersion"])
    test_case.assertEqual("certification", fixture["mode"])

    meta = fixture["meta"]
    test_case.assertEqual(
        {"diseaseName", "diseaseCode", "version", "description"},
        set(meta),
    )
    for field in ("diseaseName", "diseaseCode", "version", "description"):
        test_case.assertIsInstance(meta[field], str, f"meta.{field}")
    for field in ("diseaseName", "version", "description"):
        test_case.assertTrue(meta[field].strip(), f"meta.{field}")

    sources = fixture["sourceDocuments"]
    test_case.assertIsInstance(sources, list)
    test_case.assertTrue(sources, "sourceDocuments")
    source_contents = []
    for index, source in enumerate(sources):
        path = f"sourceDocuments[{index}]"
        test_case.assertIsInstance(source, dict, path)
        test_case.assertEqual({"name", "type", "content"}, set(source), path)
        assert_nonempty_string(test_case, source["name"], f"{path}.name")
        test_case.assertEqual("standard", source["type"], f"{path}.type")
        assert_nonempty_string(test_case, source["content"], f"{path}.content")
        source_contents.append(source["content"])

    analysis = fixture["analysisRecord"]
    test_case.assertEqual(
        {
            "inputSummary",
            "interpretations",
            "evidenceFindings",
            "uncertainties",
            "preliminaryConclusion",
        },
        set(analysis),
    )
    list_fields = (
        "inputSummary",
        "interpretations",
        "evidenceFindings",
        "uncertainties",
    )
    for field in list_fields:
        test_case.assertIsInstance(analysis[field], list, f"analysisRecord.{field}")
        if field != "uncertainties":
            test_case.assertTrue(analysis[field], f"analysisRecord.{field}")
        for index, value in enumerate(analysis[field]):
            assert_nonempty_string(
                test_case,
                value,
                f"analysisRecord.{field}[{index}]",
            )
    assert_nonempty_string(
        test_case,
        analysis["preliminaryConclusion"],
        "analysisRecord.preliminaryConclusion",
    )

    rules = fixture["rules"]
    test_case.assertIsInstance(rules, list)
    test_case.assertTrue(rules, "rules")
    rule_ids = []
    extraction_ids = []
    for rule_index, rule in enumerate(rules):
        path = f"rules[{rule_index}]"
        test_case.assertIsInstance(rule, dict, path)
        test_case.assertEqual(
            {"id", "content", "sourceQuote", "extractionItems"},
            set(rule),
            path,
        )
        assert_nonempty_string(test_case, rule["id"], f"{path}.id")
        assert_nonempty_string(test_case, rule["content"], f"{path}.content")
        assert_nonempty_string(
            test_case,
            rule["sourceQuote"],
            f"{path}.sourceQuote",
        )
        test_case.assertTrue(
            any(rule["sourceQuote"] in content for content in source_contents),
            f"{path}.sourceQuote must occur verbatim in sourceDocuments",
        )
        rule_ids.append(rule["id"])

        items = rule["extractionItems"]
        test_case.assertIsInstance(items, list, f"{path}.extractionItems")
        test_case.assertTrue(items, f"{path}.extractionItems")
        for item_index, item in enumerate(items):
            item_path = f"{path}.extractionItems[{item_index}]"
            test_case.assertIsInstance(item, dict, item_path)
            test_case.assertEqual(
                {
                    "id",
                    "name",
                    "dataType",
                    "expectedEvidence",
                    "negativeEvidence",
                    "unknownWhen",
                    "preferredSource",
                },
                set(item),
                item_path,
            )
            for field in (
                "id",
                "name",
                "dataType",
                "expectedEvidence",
                "negativeEvidence",
                "unknownWhen",
                "preferredSource",
            ):
                assert_nonempty_string(
                    test_case,
                    item[field],
                    f"{item_path}.{field}",
                )
            test_case.assertIn(item["dataType"], {"enum", "text"})
            extraction_ids.append(item["id"])

    test_case.assertEqual(
        [f"R{index:03d}" for index in range(1, len(rule_ids) + 1)],
        rule_ids,
    )
    test_case.assertEqual(
        [f"K{index:03d}" for index in range(1, len(extraction_ids) + 1)],
        extraction_ids,
    )

    references = []

    def collect_logic(node, path="logic"):
        test_case.assertIsInstance(node, dict, path)
        test_case.assertIn(node.get("type"), {"group", "rule"}, path)
        if node["type"] == "group":
            test_case.assertEqual({"type", "operator", "children"}, set(node), path)
            test_case.assertIn(node["operator"], {"AND", "OR"}, path)
            test_case.assertIsInstance(node["children"], list, f"{path}.children")
            test_case.assertTrue(node["children"], f"{path}.children")
            for index, child in enumerate(node["children"]):
                collect_logic(child, f"{path}.children[{index}]")
            return

        test_case.assertEqual({"type", "ruleId"}, set(node), path)
        assert_nonempty_string(test_case, node["ruleId"], f"{path}.ruleId")
        references.append(node["ruleId"])

    collect_logic(fixture["logic"])
    test_case.assertEqual(set(rule_ids), set(references))
    test_case.assertEqual(
        Counter({rule_id: 1 for rule_id in rule_ids}),
        Counter(references),
    )

    confirmation = fixture["confirmation"]
    test_case.assertEqual(
        {"confirmed", "summaryShown", "userResponse"},
        set(confirmation),
    )
    test_case.assertIs(type(confirmation["confirmed"]), bool)
    test_case.assertTrue(confirmation["confirmed"])
    assert_nonempty_string(
        test_case,
        confirmation["summaryShown"],
        "confirmation.summaryShown",
    )
    assert_nonempty_string(
        test_case,
        confirmation["userResponse"],
        "confirmation.userResponse",
    )


def assert_string_array(test_case, value, path, allow_empty=True):
    test_case.assertIsInstance(value, list, path)
    if not allow_empty:
        test_case.assertTrue(value, path)
    for index, item in enumerate(value):
        assert_nonempty_string(test_case, item, f"{path}[{index}]")


def assert_valid_mode2(test_case, fixture):
    test_case.assertIsInstance(fixture, dict)
    test_case.assertEqual(MODE2_REQUIRED_KEYS, set(fixture))
    test_case.assertEqual("flash-1.0", fixture["schemaVersion"])
    test_case.assertEqual("qc", fixture["mode"])

    meta = fixture["meta"]
    test_case.assertEqual(
        {"reportTitle", "diseaseName", "generatedAt"},
        set(meta),
    )
    for field in ("reportTitle", "diseaseName", "generatedAt"):
        assert_nonempty_string(test_case, meta[field], f"meta.{field}")

    profile = fixture["inputProfile"]
    test_case.assertEqual(
        {"standardKind", "auditDetail", "materialsConfirmedComplete"},
        set(profile),
    )
    test_case.assertIn(
        profile["standardKind"],
        {"structured", "natural_language", "absent"},
    )
    test_case.assertIn(
        profile["auditDetail"],
        {"detailed", "brief", "conclusion_only"},
    )
    test_case.assertIs(
        profile["materialsConfirmedComplete"],
        True,
        "formal Mode 2 output requires confirmed-complete materials",
    )

    sources = fixture["sourceDocuments"]
    test_case.assertIsInstance(sources, list)
    test_case.assertTrue(sources, "sourceDocuments")
    for index, source in enumerate(sources):
        path = f"sourceDocuments[{index}]"
        test_case.assertIsInstance(source, dict, path)
        test_case.assertEqual({"name", "type", "content"}, set(source), path)
        assert_nonempty_string(test_case, source["name"], f"{path}.name")
        test_case.assertIn(
            source["type"],
            {"patient_material", "standard", "audit_result"},
            f"{path}.type",
        )
        assert_nonempty_string(test_case, source["content"], f"{path}.content")

    analysis = fixture["analysisRecord"]
    test_case.assertEqual(
        {
            "inputSummary",
            "interpretations",
            "evidenceFindings",
            "uncertainties",
            "preliminaryConclusion",
        },
        set(analysis),
    )
    for field in (
        "inputSummary",
        "interpretations",
        "evidenceFindings",
        "uncertainties",
    ):
        assert_string_array(
            test_case,
            analysis[field],
            f"analysisRecord.{field}",
        )
    assert_nonempty_string(
        test_case,
        analysis["preliminaryConclusion"],
        "analysisRecord.preliminaryConclusion",
    )

    base_review = fixture["baseReview"]
    test_case.assertEqual(
        {"method", "materialFacts", "ruleJudgments", "preliminaryResult"},
        set(base_review),
    )
    test_case.assertEqual("two_stage_non_blind", base_review["method"])
    assert_string_array(
        test_case,
        base_review["materialFacts"],
        "baseReview.materialFacts",
    )
    judgments = base_review["ruleJudgments"]
    test_case.assertIsInstance(judgments, list, "baseReview.ruleJudgments")
    for index, judgment in enumerate(judgments):
        path = f"baseReview.ruleJudgments[{index}]"
        test_case.assertIsInstance(judgment, dict, path)
        test_case.assertEqual(
            {"ruleId", "result", "evidence", "reason"},
            set(judgment),
            path,
        )
        assert_nonempty_string(test_case, judgment["ruleId"], f"{path}.ruleId")
        test_case.assertIn(
            judgment["result"],
            {"met", "not_met", "unknown"},
            f"{path}.result",
        )
        assert_string_array(
            test_case,
            judgment["evidence"],
            f"{path}.evidence",
        )
        assert_nonempty_string(test_case, judgment["reason"], f"{path}.reason")
    test_case.assertIn(
        base_review["preliminaryResult"],
        {"meets", "does_not_meet", "uncertain"},
    )

    comparison = fixture["auditComparison"]
    test_case.assertEqual(
        {"originalConclusion", "qcConclusion", "risk", "summary"},
        set(comparison),
    )
    assert_nonempty_string(
        test_case,
        comparison["originalConclusion"],
        "auditComparison.originalConclusion",
    )
    test_case.assertIn(
        comparison["qcConclusion"],
        {"reliable", "problematic", "uncertain"},
    )
    test_case.assertIn(
        comparison["risk"],
        {"none", "false_approval", "false_rejection", "both", "unknown"},
    )
    assert_nonempty_string(
        test_case,
        comparison["summary"],
        "auditComparison.summary",
    )

    dimensions = fixture["dimensions"]
    test_case.assertIsInstance(dimensions, list)
    test_case.assertEqual(len(MODE2_DIMENSIONS), len(dimensions))
    test_case.assertEqual(
        MODE2_DIMENSIONS,
        [dimension.get("name") for dimension in dimensions],
    )
    dimension_statuses = {}
    for index, dimension in enumerate(dimensions):
        path = f"dimensions[{index}]"
        test_case.assertIsInstance(dimension, dict, path)
        test_case.assertEqual(
            {"name", "status", "summary", "notCheckedReason"},
            set(dimension),
            path,
        )
        test_case.assertIn(
            dimension["status"],
            {"passed", "issue", "not_checked"},
            f"{path}.status",
        )
        assert_nonempty_string(test_case, dimension["summary"], f"{path}.summary")
        test_case.assertIsInstance(
            dimension["notCheckedReason"],
            str,
            f"{path}.notCheckedReason",
        )
        if dimension["status"] == "not_checked":
            test_case.assertTrue(
                dimension["notCheckedReason"].strip(),
                f"{path}.notCheckedReason",
            )
        else:
            test_case.assertEqual(
                "",
                dimension["notCheckedReason"],
                f"{path}.notCheckedReason",
            )
        dimension_statuses[dimension["name"]] = dimension["status"]

    issues = fixture["issues"]
    test_case.assertIsInstance(issues, list)
    for index, issue in enumerate(issues, start=1):
        path = f"issues[{index - 1}]"
        test_case.assertIsInstance(issue, dict, path)
        test_case.assertEqual(
            {
                "id",
                "dimension",
                "severity",
                "auditClaim",
                "actualEvidence",
                "sourceReference",
                "impact",
                "recommendation",
            },
            set(issue),
            path,
        )
        for field in (
            "id",
            "dimension",
            "severity",
            "auditClaim",
            "actualEvidence",
            "sourceReference",
            "impact",
            "recommendation",
        ):
            assert_nonempty_string(test_case, issue[field], f"{path}.{field}")
        test_case.assertEqual(f"I{index:03d}", issue["id"], f"{path}.id")
        test_case.assertIn(issue["dimension"], MODE2_DIMENSIONS, f"{path}.dimension")
        test_case.assertEqual(
            "issue",
            dimension_statuses[issue["dimension"]],
            f"{path}.dimension must identify an issue dimension",
        )
        test_case.assertIn(
            issue["severity"],
            {"high", "medium", "low"},
            f"{path}.severity",
        )

    assert_string_array(
        test_case,
        fixture["recommendations"],
        "recommendations",
    )

    confirmation = fixture["confirmation"]
    test_case.assertEqual(
        {"confirmed", "inventoryShown", "userResponse"},
        set(confirmation),
    )
    test_case.assertIs(confirmation["confirmed"], True)
    assert_string_array(
        test_case,
        confirmation["inventoryShown"],
        "confirmation.inventoryShown",
        allow_empty=False,
    )
    assert_nonempty_string(
        test_case,
        confirmation["userResponse"],
        "confirmation.userResponse",
    )

    if profile["standardKind"] == "absent":
        test_case.assertEqual([], judgments)
        test_case.assertEqual("uncertain", base_review["preliminaryResult"])
        rule_dimension = dimensions[MODE2_DIMENSIONS.index("规则维护质量")]
        test_case.assertEqual("not_checked", rule_dimension["status"])

    if profile["standardKind"] == "natural_language":
        for judgment in judgments:
            test_case.assertRegex(judgment["ruleId"], r"^TMP-R\d{3}$")

    if profile["auditDetail"] == "conclusion_only":
        for name in ("证据提取准确性", "审核条件与结论一致性"):
            dimension = dimensions[MODE2_DIMENSIONS.index(name)]
            test_case.assertEqual("not_checked", dimension["status"])


class OpenAIYamlParserTests(unittest.TestCase):
    def test_rejects_malformed_missing_and_misplaced_interface_fields(self):
        invalid_documents = (
            (
                "interface:\n"
                ' display_name: "门诊慢特病认定与质控 Flash"\n'
            ),
            (
                "interface:\n"
                '  display_name: "门诊慢特病认定与质控 Flash"\n'
            ),
            (
                'display_name: "门诊慢特病认定与质控 Flash"\n'
                "interface:\n"
            ),
        )

        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(AssertionError):
                    parse_openai_interface(document)


class FlashSkillStaticStructureTests(unittest.TestCase):
    def test_runtime_layout_has_only_declared_resources(self):
        expected = {
            "SKILL.md",
            "agents/openai.yaml",
            "references/mode1-contract.md",
            "references/mode2-contract.md",
            "references/output-checklist.md",
            "assets/certification-template.html",
            "assets/qc-report-template.html",
        }
        actual = {
            path.relative_to(SKILL_ROOT).as_posix()
            for path in SKILL_ROOT.rglob("*")
            if path.is_file()
        }

        self.assertEqual(expected, actual)
        self.assertFalse((SKILL_ROOT / "scripts").exists())
        self.assertFalse((SKILL_ROOT / "tests").exists())

    def test_skill_metadata_and_ui(self):
        metadata = parse_frontmatter(read(SKILL_ROOT / "SKILL.md"))

        self.assertEqual({"name", "description"}, set(metadata))
        self.assertEqual(
            "chronic-disease-certification-qc-flash", metadata["name"]
        )
        for phrase in ("轻量", "认定标准", "审核"):
            self.assertIn(phrase, metadata["description"])

        ui = parse_openai_interface(
            read(SKILL_ROOT / "agents" / "openai.yaml")
        )
        self.assertEqual(
            {
                "display_name": "门诊慢特病认定与质控 Flash",
                "short_description": (
                    "轻量生成门诊慢特病认定标准并复核患者材料与智能审核结果"
                ),
                "default_prompt": (
                    "使用 $chronic-disease-certification-qc-flash "
                    "生成门诊慢特病认定标准，或复核患者材料与智能审核结果。"
                ),
            },
            ui,
        )
        self.assertGreaterEqual(len(ui["short_description"]), 25)
        self.assertLessEqual(len(ui["short_description"]), 64)
        self.assertIn(
            "$chronic-disease-certification-qc-flash",
            ui["default_prompt"],
        )

    def test_html_templates_have_single_json_data_slot(self):
        templates = (
            "certification-template.html",
            "qc-report-template.html",
        )

        for filename in templates:
            with self.subTest(template=filename):
                html = read(SKILL_ROOT / "assets" / filename)
                self.assertTrue(html.strip())
                self.assertRegex(html, r"(?i)<!doctype html>")
                self.assertRegex(html, r"(?i)<html(?:\s|>)")
                self.assertEqual(1, html.count("__FLASH_DATA_JSON__"))
                self.assertIn('id="flash-data"', html)
                self.assertIn('type="application/json"', html)

    def test_no_placeholder_markers_in_runtime_docs(self):
        forbidden = ("TO" + "DO", "T" + "BD")
        runtime_files = (
            path for path in SKILL_ROOT.rglob("*") if path.is_file()
        )

        for path in runtime_files:
            content = read(path).upper()
            for marker in forbidden:
                self.assertNotIn(marker, content, path.relative_to(REPO_ROOT))


class Mode1FixtureContractTests(unittest.TestCase):
    def setUp(self):
        fixture_path = ACCEPTANCE_ROOT / "fixtures" / "valid-mode1.json"
        self.fixture = json.loads(read(fixture_path))

    def test_valid_mode1_fixture_has_canonical_contract(self):
        assert_valid_mode1_fixture(self, self.fixture)

    def test_rejects_invalid_nested_mode1_mutations(self):
        mutations = {}

        extra_meta = copy.deepcopy(self.fixture)
        extra_meta["meta"]["extra"] = "not allowed"
        mutations["extra nested key"] = extra_meta

        missing_rule_key = copy.deepcopy(self.fixture)
        del missing_rule_key["rules"][0]["content"]
        mutations["missing nested key"] = missing_rule_key

        empty_rules = copy.deepcopy(self.fixture)
        empty_rules["rules"] = []
        mutations["empty rules"] = empty_rules

        empty_extraction = copy.deepcopy(self.fixture)
        empty_extraction["rules"][0]["extractionItems"] = []
        mutations["empty extractionItems"] = empty_extraction

        wrong_analysis_type = copy.deepcopy(self.fixture)
        wrong_analysis_type["analysisRecord"]["inputSummary"] = "not an array"
        mutations["wrong analysis type"] = wrong_analysis_type

        wrong_analysis_item_type = copy.deepcopy(self.fixture)
        wrong_analysis_item_type["analysisRecord"]["interpretations"] = [1]
        mutations["wrong analysis item type"] = wrong_analysis_item_type

        unfaithful_quote = copy.deepcopy(self.fixture)
        unfaithful_quote["rules"][0]["sourceQuote"] = "来源中没有这句话"
        mutations["quote absent from sources"] = unfaithful_quote

        empty_confirmation_summary = copy.deepcopy(self.fixture)
        empty_confirmation_summary["confirmation"]["summaryShown"] = ""
        mutations["empty confirmation summary"] = empty_confirmation_summary

        empty_confirmation_response = copy.deepcopy(self.fixture)
        empty_confirmation_response["confirmation"]["userResponse"] = ""
        mutations["empty confirmation response"] = empty_confirmation_response

        for name, mutation in mutations.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_valid_mode1_fixture(self, mutation)


class Mode1DocumentationTests(unittest.TestCase):
    def test_skill_declares_gated_mode1_workflow(self):
        skill = read(SKILL_ROOT / "SKILL.md")
        section_match = re.search(
            r"^## 模式 1：生成结构化认定标准\s*$"
            r"(?P<body>.*?)(?=^## |\Z)",
            skill,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(section_match, "missing exact Mode 1 heading")
        section = section_match.group("body")

        markers = (
            "references/mode1-contract.md",
            "references/output-checklist.md",
            "assets/certification-template.html",
            "阻断性歧义",
            "待确认摘要",
            "用户确认",
            "分析草稿",
            "正式 JSON",
            "安全写入",
            "JSON 和 HTML",
        )
        for marker in markers:
            self.assertIn(marker, section)
        self.assertNotIn("references/mode2-contract.md", section)
        self.assertLess(section.index("阻断性歧义"), section.index("用户确认"))
        self.assertLess(section.index("用户确认"), section.index("正式 JSON"))
        self.assertIn("已序列化并通过校验的 JSON 文本", section)
        self.assertIn("只替换该序列化文本", section)
        self.assertLess(
            section.index("已序列化并通过校验的 JSON 文本"),
            section.index("只替换该序列化文本"),
        )

    def test_mode1_contract_documents_complete_flash_schema(self):
        contract = read(SKILL_ROOT / "references" / "mode1-contract.md")

        for field in MODE1_REQUIRED_KEYS:
            self.assertIn(field, contract)
        for marker in (
            "R001",
            "K001",
            "enum",
            "text",
            "group",
            "rule",
            "AND",
            "OR",
            "sourceDocuments",
            "analysisRecord",
            "`name`、`type`、`content`",
            '"type": "standard"',
            "`id`、`content`、`sourceQuote`、`extractionItems`",
            (
                "`id`、`name`、`dataType`、`expectedEvidence`、"
                "`negativeEvidence`、`unknownWhen`、`preferredSource`"
            ),
            "`confirmed`、`summaryShown`、`userResponse`",
            "均为字符串",
            "不得为空",
            "逐字子串",
            "阻断性歧义",
            "<病种>-认定标准-flash-<版本>.json",
            "<病种>-认定标准-flash-<版本>.html",
        ):
            self.assertIn(marker, contract)
        self.assertRegex(contract, r"阻断性歧义.{0,80}(?:未解决|未消除).{0,80}(?:不得|禁止)")

    def test_mode1_contract_example_matches_canonical_fixture(self):
        contract = read(SKILL_ROOT / "references" / "mode1-contract.md")
        match = re.search(r"```json\s*(\{.*?\})\s*```", contract, re.DOTALL)
        self.assertIsNotNone(match, "Mode 1 contract must contain a JSON example")
        contract_example = json.loads(match.group(1))
        fixture = json.loads(
            read(ACCEPTANCE_ROOT / "fixtures" / "valid-mode1.json")
        )

        self.assertEqual(fixture, contract_example)
        assert_valid_mode1_fixture(self, contract_example)


class Mode2FixtureContractTests(unittest.TestCase):
    def setUp(self):
        fixture_path = ACCEPTANCE_ROOT / "fixtures" / "valid-mode2.json"
        self.fixture = json.loads(read(fixture_path))

    def test_valid_mode2_fixture_has_canonical_contract(self):
        assert_valid_mode2(self, self.fixture)
        self.assertEqual(
            ["issue", "passed", "passed", "issue", "passed"],
            [dimension["status"] for dimension in self.fixture["dimensions"]],
        )
        self.assertEqual(
            [
                {
                    "name": "患者材料",
                    "type": "patient_material",
                    "content": "患者材料明确记载证据 A。",
                },
                {
                    "name": "认定标准",
                    "type": "standard",
                    "content": "认定标准要求满足证据 A。",
                },
                {
                    "name": "原审核结果",
                    "type": "audit_result",
                    "content": "原审核认定证据 A 缺失，结论为不通过。",
                },
            ],
            self.fixture["sourceDocuments"],
        )

    def test_rejects_invalid_nested_mode2_mutations(self):
        mutations = {}

        extra_meta = copy.deepcopy(self.fixture)
        extra_meta["meta"]["extra"] = "not allowed"
        mutations["extra nested key"] = extra_meta

        missing_comparison_key = copy.deepcopy(self.fixture)
        del missing_comparison_key["auditComparison"]["summary"]
        mutations["missing nested key"] = missing_comparison_key

        wrong_enum = copy.deepcopy(self.fixture)
        wrong_enum["auditComparison"]["risk"] = "maybe"
        mutations["wrong enum"] = wrong_enum

        duplicate_dimension = copy.deepcopy(self.fixture)
        duplicate_dimension["dimensions"][1]["name"] = MODE2_DIMENSIONS[0]
        mutations["duplicate dimension"] = duplicate_dimension

        missing_dimension = copy.deepcopy(self.fixture)
        missing_dimension["dimensions"].pop()
        mutations["missing dimension"] = missing_dimension

        missing_not_checked_reason = copy.deepcopy(self.fixture)
        missing_not_checked_reason["dimensions"][2]["status"] = "not_checked"
        mutations["not_checked missing reason"] = missing_not_checked_reason

        issue_bad_dimension = copy.deepcopy(self.fixture)
        issue_bad_dimension["issues"][0]["dimension"] = "不存在的维度"
        mutations["issue bad dimension"] = issue_bad_dimension

        issue_bad_severity = copy.deepcopy(self.fixture)
        issue_bad_severity["issues"][0]["severity"] = "critical"
        mutations["issue bad severity"] = issue_bad_severity

        issue_bad_id = copy.deepcopy(self.fixture)
        issue_bad_id["issues"][0]["id"] = "I009"
        mutations["issue bad ID"] = issue_bad_id

        invalid_method = copy.deepcopy(self.fixture)
        invalid_method["baseReview"]["method"] = "strict_blind"
        mutations["invalid method"] = invalid_method

        wrong_analysis_type = copy.deepcopy(self.fixture)
        wrong_analysis_type["analysisRecord"]["evidenceFindings"] = "证据 A"
        mutations["wrong analysis type"] = wrong_analysis_type

        empty_confirmation_inventory = copy.deepcopy(self.fixture)
        empty_confirmation_inventory["confirmation"]["inventoryShown"] = []
        mutations["empty confirmation inventory"] = empty_confirmation_inventory

        for name, mutation in mutations.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, mutation)

    def test_rejects_conclusion_only_output_that_claims_detailed_checks(self):
        mutation = copy.deepcopy(self.fixture)
        mutation["inputProfile"]["auditDetail"] = "conclusion_only"

        with self.assertRaises(AssertionError):
            assert_valid_mode2(self, mutation)


class Mode2DocumentationTests(unittest.TestCase):
    def test_skill_declares_gated_two_stage_mode2_workflow(self):
        skill = read(SKILL_ROOT / "SKILL.md")
        section_match = re.search(
            r"^## 模式 2：生成智能审核质控报告\s*$"
            r"(?P<body>.*?)(?=^## |\Z)",
            skill,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(section_match, "missing exact Mode 2 heading")
        section = section_match.group("body")

        markers = (
            "references/mode2-contract.md",
            "references/output-checklist.md",
            "assets/qc-report-template.html",
            "是否遗漏任何内容",
            "用户确认",
            "baseReview",
            "auditComparison",
            "two_stage_non_blind",
            "五个质控维度",
            "JSON 和 HTML",
        )
        for marker in markers:
            self.assertIn(marker, section)
        self.assertNotIn("references/mode1-contract.md", section)
        self.assertLess(section.index("用户确认"), section.index("baseReview"))
        self.assertLess(section.index("baseReview"), section.index("auditComparison"))
        self.assertIn("已序列化并通过校验的 JSON 文本", section)
        self.assertIn("只替换该序列化文本", section)

        steps = re.findall(r"(?m)^(\d+)\. ", section)
        self.assertEqual([str(index) for index in range(1, 12)], steps)

    def test_mode2_contract_documents_complete_flash_schema(self):
        contract = read(SKILL_ROOT / "references" / "mode2-contract.md")

        for field in MODE2_REQUIRED_KEYS:
            self.assertIn(field, contract)
        for marker in (
            "reportTitle",
            "diseaseName",
            "generatedAt",
            "standardKind",
            "structured",
            "natural_language",
            "absent",
            "auditDetail",
            "detailed",
            "brief",
            "conclusion_only",
            "materialsConfirmedComplete",
            "patient_material",
            "standard",
            "audit_result",
            "two_stage_non_blind",
            "met",
            "not_met",
            "unknown",
            "meets",
            "does_not_meet",
            "uncertain",
            "reliable",
            "problematic",
            "false_approval",
            "false_rejection",
            "both",
            "not_checked",
            "high",
            "medium",
            "low",
            "I001",
            "TMP-R001",
            "完整原文",
            "不得编造",
            "<病种>-审核质控-flash-<日期>.json",
            "<病种>-审核质控-flash-<日期>.html",
        ):
            self.assertIn(marker, contract)
        for dimension in MODE2_DIMENSIONS:
            self.assertIn(dimension, contract)

    def test_mode2_contract_example_matches_canonical_fixture(self):
        contract = read(SKILL_ROOT / "references" / "mode2-contract.md")
        match = re.search(r"```json\s*(\{.*?\})\s*```", contract, re.DOTALL)
        self.assertIsNotNone(match, "Mode 2 contract must contain a JSON example")
        contract_example = json.loads(match.group(1))
        fixture = json.loads(
            read(ACCEPTANCE_ROOT / "fixtures" / "valid-mode2.json")
        )

        self.assertEqual(fixture, contract_example)
        assert_valid_mode2(self, contract_example)


class FlashCertificationTemplateTests(unittest.TestCase):
    def setUp(self):
        self.template_path = (
            SKILL_ROOT / "assets" / "certification-template.html"
        )
        self.fixture_path = ACCEPTANCE_ROOT / "fixtures" / "valid-mode1.json"
        self.template = read(self.template_path)

    def assert_embedded_fixture_has_error_contract(
        self,
        fixture,
        condition,
        message,
    ):
        with tempfile.TemporaryDirectory() as directory:
            fixture_path = Path(directory) / "invalid.json"
            fixture_path.write_text(
                json.dumps(fixture, ensure_ascii=False),
                encoding="utf-8",
            )
            html = embedded_html(self.template_path, fixture_path)

        match = re.search(
            r'<script id="flash-data" type="application/json">'
            r"(?P<payload>.*?)</script>",
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        self.assertEqual(fixture, json.loads(match.group("payload")))
        self.assertIn(condition, self.template)
        self.assertIn(f'throw new Error("{message}")', self.template)
        self.assertIn("error.message", self.template)

    def test_template_has_one_safe_data_slot_and_offline_renderer(self):
        self.assertEqual(1, self.template.count("__FLASH_DATA_JSON__"))
        script_tags = re.findall(
            r"<script\b[^>]*>",
            self.template,
            re.IGNORECASE,
        )
        self.assertEqual(2, len(script_tags))
        data_slots = [
            tag
            for tag in script_tags
            if re.search(r'\bid="flash-data"', tag)
            and re.search(r'\btype="application/json"', tag)
        ]
        self.assertEqual(1, len(data_slots))
        self.assertIn(
            '<script id="flash-data" type="application/json">'
            "__FLASH_DATA_JSON__</script>",
            self.template,
        )

        for forbidden in ("innerHTML", "document.write"):
            self.assertNotIn(forbidden, self.template)
        self.assertNotRegex(self.template, r"\beval\s*\(")
        for required in (
            "textContent",
            "JSON.parse",
            "IntersectionObserver",
            "prefers-reduced-motion",
        ):
            self.assertIn(required, self.template)
        self.assertNotRegex(
            self.template,
            r"https?://|<script\b[^>]*\bsrc\s*=|<link\b[^>]*\bhref\s*=",
        )

    def test_template_has_exact_navigation_and_sections(self):
        navigation = (
            ("overview", "概览"),
            ("logic", "逻辑关系"),
            ("rules", "认定规则"),
            ("extractions", "提取项"),
            ("analysis", "分析记录"),
            ("sources", "原始材料"),
            ("confirmation", "确认记录"),
        )
        for section_id, label in navigation:
            self.assertIn(
                f'<a href="#{section_id}">{label}</a>',
                self.template,
            )
            self.assertEqual(
                1,
                len(
                    re.findall(
                        rf'<section\b[^>]*\bid="{section_id}"[^>]*>',
                        self.template,
                    )
                ),
            )

    def test_template_exposes_accessible_landmarks_and_focus(self):
        self.assertRegex(
            self.template,
            r'<a\b[^>]*class="skip-link"[^>]*href="#main"[^>]*>',
        )
        self.assertRegex(self.template, r'<main\b[^>]*\bid="main"[^>]*>')
        self.assertRegex(
            self.template,
            r'<nav\b[^>]*\bid="page-navigation"[^>]*'
            r'\baria-label="页面导航"[^>]*>',
        )
        self.assertRegex(
            self.template,
            r'<button\b[^>]*class="nav-toggle"[^>]*'
            r'\btype="button"[^>]*\baria-expanded="false"[^>]*'
            r'\baria-controls="page-navigation"[^>]*>',
        )
        self.assertEqual(
            1,
            len(re.findall(r"<h1\b", self.template, re.IGNORECASE)),
        )
        self.assertIn(":focus-visible", self.template)
        self.assertIn(
            'link.setAttribute("aria-current", "location")',
            self.template,
        )
        self.assertIn('link.removeAttribute("aria-current")', self.template)

    def test_renderer_declares_complete_mode1_fields_and_labels(self):
        mappings = (
            'enum: "枚举"',
            'text: "文本"',
            'AND: "且"',
            'OR: "或"',
            'group: "逻辑组"',
            'rule: "规则"',
            'true: "已确认"',
            'false: "未确认"',
        )
        for mapping in mappings:
            self.assertIn(mapping, self.template)

        for field in (
            "id",
            "name",
            "dataType",
            "expectedEvidence",
            "negativeEvidence",
            "unknownWhen",
            "preferredSource",
            "inputSummary",
            "interpretations",
            "evidenceFindings",
            "uncertainties",
            "preliminaryConclusion",
            "sourceQuote",
            "summaryShown",
            "userResponse",
        ):
            self.assertIn(field, self.template)
        self.assertIn("引用的规则不存在", self.template)
        self.assertIn('node("p", "无")', self.template)

    def test_template_embeds_exact_mode1_fixture(self):
        fixture = json.loads(read(self.fixture_path))
        html = embedded_html(self.template_path, self.fixture_path)

        self.assertNotIn("__FLASH_DATA_JSON__", html)
        self.assertIn("测试病种甲", html)
        self.assertIn("R001", html)
        match = re.search(
            r'<script id="flash-data" type="application/json">'
            r"(?P<payload>.*?)</script>",
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        self.assertEqual(fixture, json.loads(match.group("payload")))

    def test_hostile_source_content_cannot_break_out_of_data_slot(self):
        hostile = (
            "</script><script>"
            "document.body.textContent='owned'"
            "</script>"
        )
        fixture = json.loads(read(self.fixture_path))
        fixture["sourceDocuments"][0]["content"] = hostile
        with tempfile.TemporaryDirectory() as directory:
            hostile_fixture_path = Path(directory) / "hostile.json"
            hostile_fixture_path.write_text(
                json.dumps(fixture, ensure_ascii=False),
                encoding="utf-8",
            )
            hostile_html = embedded_html(
                self.template_path,
                hostile_fixture_path,
            )

        self.assertNotIn(hostile, hostile_html)
        self.assertIn("\\u003c/script", hostile_html)
        script_tags = re.findall(
            r"<script\b[^>]*>",
            hostile_html,
            re.IGNORECASE,
        )
        executable_scripts = [
            tag
            for tag in script_tags
            if 'type="application/json"' not in tag
        ]
        self.assertEqual(2, len(script_tags))
        self.assertEqual(1, len(executable_scripts))

    def test_empty_rules_raise_visible_chinese_contract_error(self):
        fixture = json.loads(read(self.fixture_path))
        fixture["rules"] = []
        fixture["logic"] = {
            "type": "group",
            "operator": "AND",
            "children": [],
        }

        self.assert_embedded_fixture_has_error_contract(
            fixture,
            "if (!data.rules.length)",
            "未提供认定规则",
        )

    def test_empty_extraction_items_raise_visible_chinese_contract_error(self):
        fixture = json.loads(read(self.fixture_path))
        for rule in fixture["rules"]:
            rule["extractionItems"] = []

        self.assert_embedded_fixture_has_error_contract(
            fixture,
            "data.rules.some(rule =>",
            "未提供提取项",
        )

    def test_empty_sources_raise_visible_chinese_contract_error(self):
        fixture = json.loads(read(self.fixture_path))
        fixture["sourceDocuments"] = []

        self.assert_embedded_fixture_has_error_contract(
            fixture,
            "if (!data.sourceDocuments.length)",
            "未提供原始材料",
        )

    def test_print_reveals_content_of_closed_source_documents(self):
        self.assertIn(
            "details:not([open]) > :not(summary)",
            self.template,
        )
        self.assertRegex(
            self.template,
            r"details:not\(\[open\]\) > :not\(summary\)\s*\{\s*"
            r"display:\s*block\s*!important;",
        )

    def test_navigation_uses_one_helper_and_final_anchor_fallback(self):
        set_active = self.template.index("const setActive = target =>")
        at_bottom = self.template.index(
            "const isAtDocumentBottom = () =>"
        )
        observer = self.template.index("new IntersectionObserver")
        scroll_handler = self.template.index(
            'window.addEventListener("scroll"'
        )

        self.assertLess(set_active, at_bottom)
        self.assertLess(at_bottom, observer)
        self.assertLess(observer, scroll_handler)
        self.assertIn("setActive(entry.target)", self.template)
        self.assertIn("setActive(link)", self.template)
        self.assertIn("document.documentElement.scrollHeight", self.template)
        self.assertIn("window.innerHeight", self.template)
        self.assertGreaterEqual(
            self.template.count('setActive("confirmation")'),
            2,
        )
        observer_body = self.template[observer:scroll_handler]
        self.assertLess(
            observer_body.index("if (isAtDocumentBottom())"),
            observer_body.index("const visible"),
        )


if __name__ == "__main__":
    unittest.main()
