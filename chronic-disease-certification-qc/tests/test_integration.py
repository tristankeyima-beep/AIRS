import copy
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
SKILL = ROOT / "SKILL.md"
STRUCTURING_RULES = ROOT / "references" / "structuring-rules.md"
BRAIN_CLINICAL_SOURCE = (
    "临床出现相应的脑部神经系统症状及体征，二级及以上医疗机构诊断为脑梗死（脑栓塞），"
    "住院治疗后仍遗有神经症状及体征需继续治疗的。"
)
BRAIN_IMAGING_SOURCE = (
    "影像学检查提示脑梗死（脑栓塞）灶或颅内、颅外血管中重度狭窄。"
)
BRAIN_SOURCE = (
    "逻辑：且\n"
    "\n"
    "认定标准：\n"
    "临床出现相应的脑部神经系统症状及体征，二级及以上医疗机构诊断为脑梗死（脑栓塞），"
    "住院治疗后仍遗有神经症状及体征需继续治疗的。\n"
    "影像学检查提示脑梗死（脑栓塞）灶或颅内、颅外血管中重度狭窄。\n"
)
BRAIN_CLINICAL_GUIDES = [
    "临床是否出现相应的脑部神经系统症状及体征",
    "是否由二级及以上医疗机构诊断为脑梗死（脑栓塞）",
    "住院治疗后是否仍遗有神经症状及体征需继续治疗",
]
BRAIN_IMAGING_GUIDES = [
    "影像学检查是否提示脑梗死（脑栓塞）灶",
    "影像学检查是否提示颅内、颅外血管中重度狭窄",
]


def load(name):
    spec = importlib.util.spec_from_file_location(
        f"integration_{name}", SCRIPTS / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _OfflineHtmlInspector(HTMLParser):
    RESOURCE_TAGS = {"script", "link", "img", "iframe", "object", "embed", "source"}
    URL_ATTRIBUTES = {"src", "href", "action", "formaction", "poster", "data"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.resource_tags = []
        self.external_urls = []
        self.event_handlers = []
        self.style_blocks = []
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        lowered_tag = tag.casefold()
        if lowered_tag in self.RESOURCE_TAGS:
            self.resource_tags.append(lowered_tag)
        if lowered_tag == "style":
            self._in_style = True
        for name, value in attrs:
            lowered_name = name.casefold()
            value = value or ""
            if lowered_name.startswith("on"):
                self.event_handlers.append((lowered_tag, lowered_name))
            if lowered_name in self.URL_ATTRIBUTES:
                candidate = value.strip()
                if candidate.startswith("//") or re.match(
                    r"^[a-z][a-z0-9+.-]*:", candidate, flags=re.IGNORECASE
                ):
                    self.external_urls.append((lowered_tag, lowered_name, candidate))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.casefold() == "style":
            self._in_style = False

    def handle_endtag(self, tag):
        if tag.casefold() == "style":
            self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            self.style_blocks.append(data)


def assert_offline_html(testcase, rendered):
    inspector = _OfflineHtmlInspector()
    inspector.feed(rendered)
    testcase.assertEqual(inspector.resource_tags, [])
    testcase.assertEqual(inspector.external_urls, [])
    testcase.assertEqual(inspector.event_handlers, [])
    testcase.assertTrue(inspector.style_blocks, "offline HTML must retain inline CSS")
    css = "\n".join(inspector.style_blocks)
    testcase.assertIsNone(re.search(r"@import\b", css, flags=re.IGNORECASE))
    testcase.assertIsNone(re.search(r"url\s*\(", css, flags=re.IGNORECASE))


def has_single_trailing_newline(value):
    return value.endswith("\n") and not value.endswith("\n\n")


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inspector = load("inspect_standard")
        cls.validator = load("validate_certification")
        cls.certification_renderer = load("render_certification_html")
        cls.qc_renderer = load("render_qc_html")

    def _brain_draft(self):
        source_path = FIXTURES / "brain-infarction-standard.txt"
        source_lines = [
            line
            for line in source_path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith(("逻辑：", "认定标准："))
        ]
        self.assertEqual(len(source_lines), 2)
        clinical, imaging = source_lines

        def guide(content):
            return {
                "keywordCode": "",
                "dataType": "enum",
                "required": True,
                "keywordContent": content,
                "enumOptions": ["是", "否", "无法判断"],
            }

        common = {
            "ruleSource": source_path.name,
            "experience": "",
            "sourceMdFile": source_path.name,
            "sourceSection": "认定标准",
        }
        return {
            "ruleRepository": [
                {
                    **common,
                    "tempRuleId": "R001",
                    "ruleContent": clinical,
                    "sourceRuleContent": clinical,
                    "ruleKeywordGuide": [
                        guide("临床是否出现相应的脑部神经系统症状及体征"),
                        guide("是否由二级及以上医疗机构诊断为脑梗死（脑栓塞）"),
                        guide("住院治疗后是否仍遗有神经症状及体征需继续治疗"),
                    ],
                },
                {
                    **common,
                    "tempRuleId": "R002",
                    "ruleContent": imaging,
                    "sourceRuleContent": imaging,
                    "ruleKeywordGuide": [
                        guide("影像学检查是否提示脑梗死（脑栓塞）灶"),
                        guide("影像学检查是否提示颅内、颅外血管中重度狭窄"),
                    ],
                },
            ],
            "logicTopology": {
                "type": "GROUP",
                "operator": "AND",
                "children": [
                    {"type": "RULE_REF", "ruleCode": "R001"},
                    {"type": "RULE_REF", "ruleCode": "R002"},
                ],
            },
        }

    def _brain_meta(self):
        return {
            "version": "V20260724",
            "chronicDiseaseName": "脑梗死（脑栓塞）",
            "chronicDiseaseCode": "CS10",
            "createdAt": "2026-07-24",
            "description": "根据已确认来源结构化；V20260724 为生成日期，不是政策发布日期。",
            "sourceFile": "brain-infarction-standard.txt",
        }

    def test_brain_source_finalizes_validates_and_renders_without_semantic_loss(self):
        source_path = FIXTURES / "brain-infarction-standard.txt"
        source_text = source_path.read_text(encoding="utf-8")
        self.assertEqual(source_text, BRAIN_SOURCE)
        self.assertEqual(
            self.inspector.inspect_standard(source_path)["kind"], "natural_language"
        )

        draft = self._brain_draft()
        draft_before = copy.deepcopy(draft)
        formal = self.validator.finalize_certification(draft, self._brain_meta())
        self.assertEqual(draft, draft_before)
        self.assertEqual(
            set(formal), {"meta", "ruleRepository", "logicTopology"}
        )
        self.assertEqual(
            [rule["ruleCode"] for rule in formal["ruleRepository"]],
            ["10001", "10002"],
        )
        self.assertEqual(
            [
                [guide["keywordCode"] for guide in rule["ruleKeywordGuide"]]
                for rule in formal["ruleRepository"]
            ],
            [
                ["10001001", "10001002", "10001003"],
                ["10002001", "10002002"],
            ],
        )
        self.assertEqual(formal["logicTopology"]["operator"], "AND")
        references = [
            child["ruleCode"] for child in formal["logicTopology"]["children"]
        ]
        self.assertEqual(references, ["10001", "10002"])
        self.assertEqual(references, [rule["ruleCode"] for rule in formal["ruleRepository"]])

        clinical = formal["ruleRepository"][0]
        self.assertEqual(clinical["ruleContent"], BRAIN_CLINICAL_SOURCE)
        self.assertEqual(clinical["sourceRuleContent"], BRAIN_CLINICAL_SOURCE)
        self.assertEqual(
            [guide["keywordContent"] for guide in clinical["ruleKeywordGuide"]],
            BRAIN_CLINICAL_GUIDES,
        )
        imaging = formal["ruleRepository"][1]
        self.assertEqual(imaging["ruleContent"], BRAIN_IMAGING_SOURCE)
        self.assertEqual(imaging["sourceRuleContent"], BRAIN_IMAGING_SOURCE)
        self.assertIn("或", imaging["ruleContent"])
        self.assertEqual(
            [guide["keywordContent"] for guide in imaging["ruleKeywordGuide"]],
            BRAIN_IMAGING_GUIDES,
        )

        validation = self.validator.validate_certification(formal)
        self.assertTrue(validation["valid"], validation["errors"])
        rendered = self.certification_renderer.render_certification_html(formal)
        for literal in (BRAIN_CLINICAL_SOURCE, BRAIN_IMAGING_SOURCE):
            self.assertIn(literal, rendered)
        for rule in formal["ruleRepository"]:
            for guide in rule["ruleKeywordGuide"]:
                self.assertIn(guide["keywordContent"], rendered)
        for value in (
            "脑梗死（脑栓塞）",
            "CS10",
            "V20260724",
            "AND · 全部条件满足",
        ):
            self.assertIn(value, rendered)
        assert_offline_html(self, rendered)

    def test_ambiguous_standard_is_natural_language_and_contract_blocks_guessing(self):
        ambiguous_path = FIXTURES / "ambiguous-standard.txt"
        source = ambiguous_path.read_text(encoding="utf-8")
        self.assertEqual(
            self.inspector.inspect_standard(ambiguous_path)["kind"],
            "natural_language",
        )
        self.assertNotRegex(source, r"(^|[^A-Za-z])(AND|OR)([^A-Za-z]|$)")
        self.assertNotIn("且", source)
        self.assertNotIn("或", source)

        skill = SKILL.read_text(encoding="utf-8")
        structuring = STRUCTURING_RULES.read_text(encoding="utf-8")
        self.assertRegex(
            skill,
            r"AND/OR[\s\S]{0,180}(逐项向用户提问|询问用户)[\s\S]{0,100}不得猜测",
        )
        self.assertIn("用户明确同意前，不得生成正式 JSON 或 HTML", skill)
        self.assertRegex(
            structuring,
            r"AND/OR[\s\S]{0,160}必须逐项向用户提出[\s\S]{0,80}不得猜测",
        )
        self.assertIn("不得生成正式 JSON 或 HTML", structuring)

    def test_valid_certification_in_process_and_cli_use_one_source_offline(self):
        source = FIXTURES / "valid-certification.json"
        source_before = source.read_bytes()
        validation = self.validator.validate_certification(source)
        self.assertTrue(validation["valid"], validation["errors"])
        in_process = self.certification_renderer.render_certification_html(source)
        assert_offline_html(self, in_process)

        validator_cli = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_certification.py"), "validate", str(source)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(validator_cli.returncode, 0, validator_cli.stderr)
        cli_validation = json.loads(validator_cli.stdout)
        self.assertEqual(cli_validation["standard"], validation["standard"])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "certification.html"
            rendered_cli = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "render_certification_html.py"),
                    str(source),
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(rendered_cli.returncode, 0, rendered_cli.stderr)
            self.assertTrue(output.is_file())
            cli_html = output.read_text(encoding="utf-8")
            self.assertTrue(has_single_trailing_newline(cli_html))
            self.assertEqual(cli_html, in_process.rstrip("\n") + "\n")
            assert_offline_html(self, cli_html)
        self.assertEqual(source.read_bytes(), source_before)

    def test_qc_canonical_text_html_and_cli_preserve_the_same_findings(self):
        source = FIXTURES / "valid-qc-report.json"
        source_before = source.read_bytes()
        source_object = json.loads(source.read_text(encoding="utf-8"))
        source_object_before = copy.deepcopy(source_object)
        canonical = self.qc_renderer.validate_qc_report(source_object)
        self.assertEqual(source_object, source_object_before)
        self.assertTrue(canonical["inputScope"]["confirmedByUser"])
        self.assertEqual(
            canonical["inputScope"]["confirmation"]["confirmedRevision"],
            canonical["inputScope"]["inventory"]["revision"],
        )
        self.assertTrue(
            canonical["inputScope"]["confirmation"]["confirmedAfterInventory"]
        )
        self.assertTrue(
            canonical["inputScope"]["independentReview"]["completedBeforeComparison"]
        )

        text_report = self.qc_renderer.render_qc_text(canonical)
        html_report = self.qc_renderer.render_qc_html(canonical)
        key_values = [
            canonical["qcConclusion"],
            canonical["riskDirection"],
            canonical["originalResult"],
            canonical["inputScope"]["confirmation"]["userStatement"],
            canonical["inputScope"]["independentReview"]["artifactSha256"],
        ]
        for issue in canonical["issues"]:
            key_values.extend(
                [
                    issue["modelClaim"],
                    issue["qcFinding"],
                    issue["recommendation"],
                    *[evidence["rawText"] for evidence in issue["materialEvidence"]],
                ]
            )
        for value in key_values:
            self.assertIn(value, text_report)
            self.assertIn(value, html_report)
        assert_offline_html(self, html_report)

        injected = copy.deepcopy(canonical)
        injected["case"]["patientName"] = '<script src="//attacker.invalid/user.js">x</script>'
        injected_html = self.qc_renderer.render_qc_html(injected)
        self.assertIn("&lt;script src=", injected_html)
        assert_offline_html(self, injected_html)

        with tempfile.TemporaryDirectory() as directory:
            html_output = Path(directory) / "qc-report.html"
            text_output = Path(directory) / "qc-report.txt"
            cli = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "render_qc_html.py"),
                    str(source),
                    str(html_output),
                    "--text-output",
                    str(text_output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertTrue(html_output.is_file())
            self.assertTrue(text_output.is_file())
            cli_html = html_output.read_text(encoding="utf-8")
            cli_text = text_output.read_text(encoding="utf-8")
            self.assertTrue(has_single_trailing_newline(cli_html))
            self.assertTrue(has_single_trailing_newline(cli_text))
            self.assertEqual(cli_html, html_report.rstrip("\n") + "\n")
            self.assertEqual(cli_text, text_report.rstrip("\n") + "\n")
            assert_offline_html(self, cli_html)
        self.assertEqual(source.read_bytes(), source_before)

    def test_unconfirmed_qc_mutation_is_rejected_by_all_formal_outputs(self):
        report = json.loads(
            (FIXTURES / "valid-qc-report.json").read_text(encoding="utf-8")
        )
        report["inputScope"]["confirmedByUser"] = False
        for operation in (
            self.qc_renderer.validate_qc_report,
            self.qc_renderer.render_qc_text,
            self.qc_renderer.render_qc_html,
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "confirmedByUser"):
                    operation(report)

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            input_path = directory / "unconfirmed.json"
            html_output = directory / "must-not-exist.html"
            text_output = directory / "must-not-exist.txt"
            input_path.write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8"
            )
            cli = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "render_qc_html.py"),
                    str(input_path),
                    str(html_output),
                    "--text-output",
                    str(text_output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(cli.returncode, 0)
            self.assertFalse(html_output.exists())
            self.assertFalse(text_output.exists())


if __name__ == "__main__":
    unittest.main()
