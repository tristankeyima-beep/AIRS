import errno
import io
import importlib.util
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "acceptance-cases.json"
BUILDER = ROOT / "build_acceptance_html.py"
QC_RENDERER_PATH = (
    ROOT.parent
    / "chronic-disease-certification-qc"
    / "scripts"
    / "render_qc_html.py"
)
CERT_VALIDATOR_PATH = (
    ROOT.parent
    / "chronic-disease-certification-qc"
    / "scripts"
    / "validate_certification.py"
)
STANDARD_INSPECTOR_PATH = (
    ROOT.parent
    / "chronic-disease-certification-qc"
    / "scripts"
    / "inspect_standard.py"
)

EXPECTED_GENERATED_FILE = "慢特病认定标准与审核质控-验收测试用例.html"
REPOSITORY_OUTPUT = ROOT / EXPECTED_GENERATED_FILE
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
    "M1-005": {"meta", "ruleRepository", "logicTopology"},
    "M1-006": {"meta", "ruleRepository", "logicTopology"},
    "M1-009": {"meta", "ruleRepository", "logicTopology"},
    "M1-010": {"meta", "ruleRepository", "logicTopology"},
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
    "SAFE-005": {"input.json", "report.html", "report.txt", "harness.py"},
    "SAFE-006": {"report.json", "viewports.json", "harness.py"},
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
    ("SAFE-005", "input.json"): {
        "meta",
        "ruleRepository",
        "logicTopology",
    },
    ("SAFE-006", "report.json"): {
        "case",
        "inputScope",
        "capabilities",
        "originalResult",
        "qcConclusion",
        "riskDirection",
        "recommendedAction",
        "issues",
        "ruleReviews",
        "unperformedChecks",
        "rawInput",
    },
    ("SAFE-006", "viewports.json"): {"synthetic", "viewports"},
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


class AcceptanceArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.articles = []
        self._current = None
        self._article_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = [(name, value or "") for name, value in attrs]
        classes = dict(attributes).get("class", "").split()
        is_case = tag == "article" and "acceptance-case" in classes
        if is_case and self._current is None:
            self._current = {"text": [], "attributes": [], "tags": []}
            self._article_depth = 1
        elif tag == "article" and self._current is not None:
            self._article_depth += 1
        if self._current is not None:
            self._current["tags"].append(tag)
            self._current["attributes"].extend(
                value
                for pair in attributes
                for value in pair
            )

    def handle_endtag(self, tag):
        if tag != "article" or self._current is None:
            return
        self._article_depth -= 1
        if self._article_depth == 0:
            self.articles.append(self._current)
            self._current = None

    def handle_data(self, data):
        if self._current is not None:
            self._current["text"].append(data)


class AcceptanceConsoleParser(HTMLParser):
    CONTROL_TAGS = {"button", "input", "select", "textarea"}

    def __init__(self):
        super().__init__()
        self.ids = []
        self.tag_counts = {}
        self.controls = []
        self.label_targets = set()
        self.external_resources = []

    def handle_starttag(self, tag, attrs):
        attributes = dict((name, value or "") for name, value in attrs)
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1
        if attributes.get("id"):
            self.ids.append(attributes["id"])
        if tag in self.CONTROL_TAGS:
            self.controls.append((tag, attributes))
        if tag == "label" and attributes.get("for"):
            self.label_targets.add(attributes["for"])
        if tag in {"link", "script", "img", "iframe"}:
            resource = attributes.get("href") or attributes.get("src")
            if resource:
                self.external_resources.append(resource)


class OfflineSafetyParser(HTMLParser):
    PROHIBITED_TAGS = {
        "link",
        "img",
        "iframe",
        "object",
        "embed",
        "source",
        "video",
        "audio",
        "track",
        "base",
    }
    PROHIBITED_ATTRIBUTES = {
        "action",
        "background",
        "data",
        "formaction",
        "ping",
        "poster",
        "src",
        "srcdoc",
        "srcset",
        "xlink:href",
        "xml:base",
    }

    def __init__(self):
        super().__init__()
        self.violations = []
        self.scripts = []
        self.styles = []
        self.csp_contents = []
        self._current_script = None
        self._current_style = None

    @staticmethod
    def _normalize_name(name):
        return name.strip().casefold().replace("|", ":")

    @staticmethod
    def _normalize_css(css):
        normalized = css
        for _ in range(3):
            previous = normalized
            normalized = re.sub(
                r"\\(?:\r\n|[\n\r\f])",
                "",
                normalized,
            )

            def decode_hex(match):
                codepoint = int(match.group(1), 16)
                if codepoint == 0 or codepoint > 0x10FFFF:
                    return "\ufffd"
                return chr(codepoint)

            normalized = re.sub(
                r"\\([0-9a-fA-F]{1,6})[ \t\r\n\f]?",
                decode_hex,
                normalized,
            )
            normalized = re.sub(
                r"\\([^0-9a-fA-F\r\n\f])",
                r"\1",
                normalized,
            )
            normalized = re.sub(r"/\*.*?\*/", "", normalized, flags=re.DOTALL)
            if normalized == previous:
                break
        return normalized.casefold()

    def _inspect_css(self, css, context):
        normalized = self._normalize_css(css)
        if re.search(r"@import\b", normalized):
            self.violations.append(f"css-import:{context}")
        if re.search(r"url\s*\(", normalized):
            self.violations.append(f"css-url:{context}")

    def handle_starttag(self, tag, attrs):
        tag = self._normalize_name(tag)
        attributes = {
            self._normalize_name(name): value or ""
            for name, value in attrs
        }
        if tag in self.PROHIBITED_TAGS:
            self.violations.append(f"prohibited-tag:{tag}")
        for name, value in attributes.items():
            if name.startswith("on"):
                self.violations.append(f"event-attribute:{name}")
            if name in self.PROHIBITED_ATTRIBUTES:
                self.violations.append(f"resource-attribute:{name}")
            if name == "style":
                self._inspect_css(value, "attribute")
            if name == "href" and not value.startswith("#"):
                self.violations.append("external-href")
        if (
            tag == "meta"
            and attributes.get("http-equiv", "").strip().casefold() == "refresh"
        ):
            self.violations.append("meta-refresh")
        if (
            tag == "meta"
            and attributes.get("http-equiv", "").strip().casefold()
            == "content-security-policy"
        ):
            self.csp_contents.append(attributes.get("content", ""))
        if tag == "script":
            self._current_script = {
                "attributes": attributes,
                "text": [],
            }
            self.scripts.append(self._current_script)
        elif tag == "style":
            self._current_style = []
            self.styles.append(self._current_style)

    def handle_endtag(self, tag):
        tag = self._normalize_name(tag)
        if tag == "script":
            self._current_script = None
        elif tag == "style":
            if self._current_style is not None:
                self._inspect_css("".join(self._current_style), "block")
            self._current_style = None

    def handle_data(self, data):
        if self._current_script is not None:
            self._current_script["text"].append(data)
        if self._current_style is not None:
            self._current_style.append(data)

    @property
    def catalog_json(self):
        matches = [
            "".join(script["text"])
            for script in self.scripts
            if script["attributes"].get("id") == "catalog-data"
        ]
        if len(matches) != 1:
            raise AssertionError("expected exactly one catalog-data script")
        return matches[0]

    @property
    def runtime_script(self):
        matches = [
            "".join(script["text"])
            for script in self.scripts
            if not script["attributes"]
        ]
        if len(matches) != 1:
            raise AssertionError("expected exactly one runtime script")
        return matches[0]


def assert_static_acceptance_articles(testcase, rendered, cases):
    parser = AcceptanceArticleParser()
    parser.feed(rendered)
    parser.close()
    testcase.assertEqual(len(parser.articles), len(cases))
    for article, case in zip(parser.articles, cases):
        own_content = "\n".join(article["text"] + article["attributes"])
        for field in ("id", "title", "mode", "priority"):
            testcase.assertIn(case[field], own_content)


def parse_offline_html(rendered):
    parser = OfflineSafetyParser()
    parser.feed(rendered)
    parser.close()
    return parser


def assert_runtime_navigation_contract(testcase, script):
    # CSP is defense in depth; it does not replace explicit navigation-sink gates.
    navigation_patterns = {
        "bare-open": r"(?<![\w$.])open\s*\(",
        "window-open": r"\bwindow\s*\.\s*open\s*\(",
        "bare-location-assignment": r"(?<![\w$.])location\s*=",
        "scoped-location-assignment": (
            r"\b(?:window|document|globalThis)\s*\.\s*location\s*="
        ),
        "location-href": (
            r"\b(?:(?:window|document|globalThis)\s*\.\s*)?"
            r"location\s*\.\s*href\s*="
        ),
        "location-method": (
            r"\b(?:(?:window|document|globalThis)\s*\.\s*)?"
            r"location\s*\.\s*(?:assign|replace|reload)\s*\("
        ),
        "href-set-attribute": (
            r"\.\s*setAttribute\s*\(\s*[\"']href[\"']\s*,"
        ),
    }
    for label, pattern in navigation_patterns.items():
        testcase.assertIsNone(
            re.search(pattern, script, flags=re.IGNORECASE),
            label,
        )

    export_match = re.search(
        r"(function exportResults\(\) \{.*?\n\})\n\n"
        r"async function importResults",
        script,
        flags=re.DOTALL,
    )
    testcase.assertIsNotNone(export_match)
    export_function = export_match.group(1)
    ordered_export_fragments = (
        'const blob = new Blob([serialized], { type: "application/json;charset=utf-8" });',
        'const link = createElement("a");',
        "const objectUrl = URL.createObjectURL(blob);",
        "link.href = objectUrl;",
        'link.download = "慢特病Skill验收结果-" + stamp + ".json";',
        "link.click();",
        "URL.revokeObjectURL(objectUrl);",
    )
    positions = []
    for fragment in ordered_export_fragments:
        testcase.assertEqual(export_function.count(fragment), 1, fragment)
        positions.append(export_function.index(fragment))
    testcase.assertEqual(positions, sorted(positions))

    testcase.assertEqual(
        len(
            re.findall(
                r"\bcreateElement\s*\(\s*[\"']a[\"']\s*\)",
                script,
                flags=re.IGNORECASE,
            )
        ),
        1,
    )
    testcase.assertEqual(
        len(re.findall(r"\.\s*href\s*=", script, flags=re.IGNORECASE)),
        1,
    )
    testcase.assertEqual(
        len(
            re.findall(
                r"\blink\s*\.\s*href\s*=\s*objectUrl\s*;",
                export_function,
            )
        ),
        1,
    )
    testcase.assertEqual(script.count("URL.createObjectURL(blob)"), 1)
    testcase.assertEqual(script.count("URL.revokeObjectURL(objectUrl)"), 1)

    testcase.assertEqual(
        len(re.findall(r"\.\s*click\s*\(\s*\)", script)),
        2,
    )
    testcase.assertEqual(
        len(re.findall(r"\blink\s*\.\s*click\s*\(\s*\)", export_function)),
        1,
    )
    testcase.assertEqual(
        len(
            re.findall(
                r"document\s*\.\s*getElementById\s*\(\s*"
                r"[\"']result-file[\"']\s*\)\s*\.\s*click\s*\(\s*\)",
                script,
            )
        ),
        1,
    )


def assert_runtime_offline_contract(testcase, script):
    prohibited_patterns = {
        "resource-element": (
            r'document\s*\.\s*createElement\s*\(\s*["\']'
            r"(?:img|iframe|script|link|object|embed|source|video|audio|track|base|form)"
            r'["\']\s*\)'
        ),
        "image-constructor": r"\bnew\s+Image\s*\(",
        "audio-constructor": r"\bnew\s+Audio\s*\(",
        "resource-property": (
            r"\.\s*(?:src|srcset|srcdoc|poster|data|background|ping|action|formAction)"
            r"\s*="
        ),
        "resource-set-attribute": (
            r"\.\s*setAttribute\s*\(\s*[\"']"
            r"(?:href|src|srcset|srcdoc|poster|data|background|ping|action|formaction|"
            r"xlink:href|xml:base)"
            r"[\"']"
        ),
        "window-open": r"\bwindow\s*\.\s*open\s*\(",
        "location-method": r"\blocation\s*\.\s*(?:assign|replace)\s*\(",
        "location-href": r"(?:window\s*\.\s*)?location\s*\.\s*href\s*=",
        "form-submit": r"\.\s*(?:submit|requestSubmit)\s*\(",
    }
    for label, pattern in prohibited_patterns.items():
        testcase.assertIsNone(
            re.search(pattern, script, flags=re.IGNORECASE),
            label,
        )
    direct_creations = re.findall(
        r"document\s*\.\s*createElement\s*\((.*?)\)",
        script,
        flags=re.DOTALL,
    )
    testcase.assertEqual(direct_creations, ["tagName"])
    safe_tags_match = re.search(
        r"const SAFE_ELEMENT_TAGS = Object\.freeze\(\[(.*?)\]\);",
        script,
        flags=re.DOTALL,
    )
    testcase.assertIsNotNone(safe_tags_match)
    safe_tags = json.loads("[" + safe_tags_match.group(1) + "]")
    testcase.assertEqual(
        set(safe_tags),
        {
            "a",
            "article",
            "button",
            "code",
            "details",
            "div",
            "h2",
            "h3",
            "h4",
            "header",
            "label",
            "li",
            "ol",
            "p",
            "pre",
            "section",
            "span",
            "strong",
            "summary",
            "textarea",
            "ul",
        },
    )
    testcase.assertEqual(len(safe_tags), len(set(safe_tags)))
    testcase.assertRegex(
        script,
        r"(?s)SAFE_ELEMENT_TAGS\.includes\(tagName\).*?"
        r"document\.createElement\(tagName\)",
    )
    href_assignments = re.findall(
        r"\b([A-Za-z_$][\w$]*)\.href\s*=\s*([^;]+);",
        script,
    )
    testcase.assertEqual(href_assignments, [("link", "objectUrl")])
    testcase.assertIn("const objectUrl = URL.createObjectURL(blob);", script)
    testcase.assertIn('const link = createElement("a");', script)
    testcase.assertIn("link.download =", script)
    testcase.assertIn("URL.revokeObjectURL(objectUrl);", script)
    assert_runtime_navigation_contract(testcase, script)


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


def load_contract_module(path, module_name):
    if not path.is_file():
        raise AssertionError(f"missing contract module: {path.name}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load contract module: {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER_MODULE = load_builder_module()
QC_RENDERER_MODULE = load_qc_renderer_module()
CERT_VALIDATOR_MODULE = load_contract_module(
    CERT_VALIDATOR_PATH,
    "acceptance_cert_validator",
)
STANDARD_INSPECTOR_MODULE = load_contract_module(
    STANDARD_INSPECTOR_PATH,
    "acceptance_standard_inspector",
)


class AcceptanceCatalogTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self._temp_dir.name)

    def tearDown(self):
        self._temp_dir.cleanup()

    def require_node(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required for acceptance safety tests")
        return node

    def test_node_is_a_required_acceptance_safety_precondition(self):
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(
                AssertionError,
                "Node.js is required",
            ):
                self.require_node()
        source = Path(__file__).read_text(encoding="utf-8")
        self.assertNotRegex(
            source,
            r"@unittest\.skipUnless\(shutil\.which\([\"']node[\"']",
        )

    def write_catalog(self, value):
        path = self.temp_path / "catalog.json"
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def run_cli(
        self,
        catalog=None,
        output=None,
        forbidden_terms=(),
        cwd=None,
        builder=BUILDER,
        extra_args=(),
    ):
        command = [sys.executable, str(builder)]
        if catalog is not None:
            command.extend(["--catalog", str(catalog)])
        if output is not None:
            command.extend(["--output", str(output)])
        for term in forbidden_terms:
            command.extend(["--forbid", term])
        command.extend(extra_args)
        return subprocess.run(
            command,
            cwd=cwd,
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
                    if "synthetic" in payload:
                        self.assertIs(payload["synthetic"], True)
                    else:
                        self.assertIn("【合成测试数据】", item["content"])
                elif case_id in BUNDLE_CASE_FILES:
                    files = parse_file_bundle(item["content"])
                    self.assertEqual(set(files), BUNDLE_CASE_FILES[case_id])
                    for name, body in files.items():
                        if name.endswith(".json"):
                            payload = json.loads(body)
                            if "synthetic" in payload:
                                self.assertIs(payload["synthetic"], True)
                            else:
                                self.assertIn("【合成测试数据】", body)
                            bundle_json_files.add((case_id, name))
                            self.assertEqual(
                                set(payload),
                                BUNDLE_JSON_REQUIRED_KEYS[(case_id, name)],
                            )
                        else:
                            self.assertIn("【合成测试数据】", body)
        self.assertEqual(bundle_json_files, set(BUNDLE_JSON_REQUIRED_KEYS))

    def test_mode1_structured_cases_use_the_real_certification_validator(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        results = {}
        for case_id in ("M1-005", "M1-006", "M1-009", "M1-010"):
            standard = json.loads(cases[case_id]["inputs"][0]["content"])
            results[case_id] = CERT_VALIDATOR_MODULE.validate_certification(
                standard
            )

        self.assertIs(results["M1-005"]["valid"], True)
        self.assertEqual(results["M1-005"]["errors"], [])

        error_contracts = {
            "M1-006": {
                (
                    "ruleRepository[0].ruleKeywordGuide",
                    "keyword_guide_required",
                )
            },
            "M1-009": {
                (
                    "ruleRepository[0].ruleCode",
                    "invalid_rule_code_format",
                ),
                (
                    "ruleRepository[0].ruleKeywordGuide[0].keywordCode",
                    "invalid_keyword_code_format",
                ),
            },
            "M1-010": {
                (
                    "logicTopology.children[1].ruleCode",
                    "unknown_rule_reference",
                ),
                ("logicTopology", "unreferenced_rule"),
            },
        }
        for case_id, expected_errors in error_contracts.items():
            with self.subTest(case=case_id):
                self.assertIs(results[case_id]["valid"], False)
                actual = {
                    (item["path"], item["code"])
                    for item in results[case_id]["errors"]
                }
                self.assertTrue(expected_errors.issubset(actual))

    def test_m2_015_standard_is_structured_complete_by_real_inspector(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        payload = json.loads(cases["M2-015"]["inputs"][0]["content"])
        inspection = STANDARD_INSPECTOR_MODULE.inspect_standard(
            payload["standard"]
        )

        self.assertEqual(inspection["kind"], "structured_complete")
        self.assertIs(inspection["completeness"]["structural"], True)
        self.assertIs(inspection["completeness"]["executable"], True)
        self.assertIs(inspection["completeness"]["traceable"], True)
        self.assertEqual(
            {
                item["ruleCode"]
                for item in payload["auditResult"]["conditionResults"]
            },
            {
                item["ruleCode"]
                for item in payload["standard"]["ruleRepository"]
            },
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

        for case_id in ("GATE-005", "SAFE-003"):
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

    def test_safe_005_bundle_harness_runs_path_and_atomic_guards(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        files = parse_file_bundle(cases["SAFE-005"]["inputs"][0]["content"])

        with tempfile.TemporaryDirectory() as directory:
            temp_root = Path(directory)
            for name, body in files.items():
                (temp_root / name).write_text(body, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(temp_root / "harness.py"),
                    str(CERT_VALIDATOR_PATH),
                ],
                cwd=temp_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "harness_ok")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                (temp_root / "report.html").read_text(encoding="utf-8"),
                "【合成测试数据】existing html",
            )
            self.assertEqual(
                (temp_root / "report.txt").read_text(encoding="utf-8"),
                "【合成测试数据】existing text",
            )

    def test_safe_006_report_and_harness_run_real_renderers(self):
        cases = {
            case["id"]: case
            for case in BUILDER_MODULE.load_catalog(CATALOG)["cases"]
        }
        files = parse_file_bundle(cases["SAFE-006"]["inputs"][0]["content"])
        report = json.loads(files["report.json"])
        viewports = json.loads(files["viewports.json"])

        validated = QC_RENDERER_MODULE.validate_qc_report(report)
        rendered_text = QC_RENDERER_MODULE.render_qc_text(validated)
        rendered_html = QC_RENDERER_MODULE.render_qc_html(validated)
        long_marker = "LONG_EVIDENCE_BLOCK_"
        self.assertIn(long_marker, rendered_text)
        self.assertIn(long_marker, rendered_html)
        self.assertNotIn("https://", rendered_html)
        self.assertNotIn("http://", rendered_html)
        self.assertEqual(
            {(item["width"], item["height"]) for item in viewports["viewports"]},
            {(320, 800), (1440, 900)},
        )

        with tempfile.TemporaryDirectory() as directory:
            temp_root = Path(directory)
            for name, body in files.items():
                (temp_root / name).write_text(body, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(temp_root / "harness.py"),
                    str(QC_RENDERER_PATH),
                ],
                cwd=temp_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "harness_ok")
            self.assertEqual(result.stderr, "")
            self.assertIn(
                long_marker,
                (temp_root / "rendered-report.txt").read_text(encoding="utf-8"),
            )
            self.assertIn(
                long_marker,
                (temp_root / "rendered-report.html").read_text(encoding="utf-8"),
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

    def test_json_decoder_value_error_is_controlled_in_library_and_cli(self):
        integer_limit = sys.get_int_max_str_digits()
        if integer_limit == 0:
            self.skipTest("Python integer digit limit is disabled")
        sensitive_digits = "7" * (integer_limit + 100)
        path = self.temp_path / "private-oversized-integer.json"
        path.write_text(
            '{"value":' + sensitive_digits + "}",
            encoding="utf-8",
        )

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.load_catalog(path)

        self.assertEqual(str(caught.exception), "catalog_json_error")
        self.assertNotIn(sensitive_digits[:100], str(caught.exception))
        result = self.run_cli(path, output=self.temp_path / "output.html")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "catalog_error")
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn(sensitive_digits[:100], result.stderr)
        self.assertNotIn(path.name, result.stderr)

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

    def test_validate_catalog_accepts_the_exact_repository_contract(self):
        catalog = BUILDER_MODULE.load_catalog(CATALOG)

        validated = BUILDER_MODULE.validate_catalog(catalog)

        self.assertIs(validated, catalog)
        self.assertEqual(tuple(case["id"] for case in catalog["cases"]), EXPECTED_IDS)
        self.assertEqual(BUILDER_MODULE.CASE_FIELDS, frozenset(CASE_FIELDS))
        self.assertEqual(BUILDER_MODULE.INPUT_FIELDS, frozenset(INPUT_FIELDS))
        self.assertEqual(BUILDER_MODULE.STEP_FIELDS, frozenset(STEP_FIELDS))

    def test_validate_catalog_rejects_count_id_set_duplicates_and_order(self):
        mutations = {}
        too_few = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        too_few["cases"].pop()
        mutations["count"] = too_few
        duplicate = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        duplicate["cases"][1]["id"] = duplicate["cases"][0]["id"]
        mutations["duplicate"] = duplicate
        unknown = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        unknown["cases"][0]["id"] = "PRIVATE-UNKNOWN-ID"
        mutations["unknown"] = unknown
        out_of_order = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        out_of_order["cases"][0], out_of_order["cases"][1] = (
            out_of_order["cases"][1],
            out_of_order["cases"][0],
        )
        mutations["order"] = out_of_order

        for label, catalog in mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                    BUILDER_MODULE.validate_catalog(catalog)
                self.assertNotIn("PRIVATE-UNKNOWN-ID", str(caught.exception))

    def test_validate_catalog_rejects_unknown_or_missing_nested_fields(self):
        mutations = {}
        unknown_case = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        unknown_case["cases"][0]["private-business-content"] = "secret"
        mutations["unknown-case"] = unknown_case
        missing_case = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        missing_case["cases"][0].pop("notes")
        mutations["missing-case"] = missing_case
        unknown_input = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        unknown_input["cases"][0]["inputs"][0]["private-business-content"] = "secret"
        mutations["unknown-input"] = unknown_input
        unknown_step = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        unknown_step["cases"][0]["steps"][0]["private-business-content"] = "secret"
        mutations["unknown-step"] = unknown_step

        for label, catalog in mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                    BUILDER_MODULE.validate_catalog(catalog)
                self.assertNotIn("private-business-content", str(caught.exception))

    def test_validate_catalog_rejects_empty_inputs_steps_and_checks(self):
        mutations = {}
        for field in ("inputs", "steps", "acceptanceChecks"):
            catalog = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
            catalog["cases"][0][field] = []
            mutations[f"empty-{field}"] = catalog
        blank_check = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        blank_check["cases"][0]["acceptanceChecks"][0] = " \t "
        mutations["blank-check"] = blank_check
        blank_input = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        blank_input["cases"][0]["inputs"][0]["content"] = ""
        mutations["blank-input"] = blank_input
        blank_step = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        blank_step["cases"][0]["steps"][0]["expected"] = "\n"
        mutations["blank-step"] = blank_step

        for label, catalog in mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(BUILDER_MODULE.CatalogError):
                    BUILDER_MODULE.validate_catalog(catalog)

    def test_validate_catalog_rejects_illegal_enums_and_exact_type_errors(self):
        mutations = {}
        illegal_mode = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        illegal_mode["cases"][0]["mode"] = "PRIVATE-MODE"
        mutations["mode"] = illegal_mode
        illegal_priority = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        illegal_priority["cases"][0]["priority"] = "PRIVATE-PRIORITY"
        mutations["priority"] = illegal_priority
        bool_for_text = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        bool_for_text["cases"][0]["title"] = True
        mutations["bool-text"] = bool_for_text
        bool_for_list = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        bool_for_list["cases"][0]["inputs"] = True
        mutations["bool-list"] = bool_for_list
        integer_for_priority = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        integer_for_priority["cases"][0]["priority"] = 1
        mutations["integer-priority"] = integer_for_priority

        for label, catalog in mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                    BUILDER_MODULE.validate_catalog(catalog)
                self.assertNotIn("PRIVATE-", str(caught.exception))

    def test_validate_catalog_rejects_non_json_nan_and_excessive_depth(self):
        class PrivateValue:
            pass

        mutations = {}
        non_json = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        non_json["cases"][0]["inputs"][0]["content"] = PrivateValue()
        mutations["non-json"] = non_json
        nan_value = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        nan_value["cases"][0]["inputs"][0]["content"] = float("nan")
        mutations["nan"] = nan_value
        too_deep = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        nested = "private-business-content"
        for _ in range(65):
            nested = [nested]
        too_deep["cases"][0]["inputs"][0]["content"] = nested
        mutations["depth"] = too_deep

        for label, catalog in mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                    BUILDER_MODULE.validate_catalog(catalog)
                self.assertNotIn("private-business-content", str(caught.exception))
                self.assertNotIn("nan", str(caught.exception).casefold())
                if label == "depth":
                    self.assertEqual(str(caught.exception), "catalog_depth_error")

    def test_forbidden_terms_are_external_repeatable_and_not_hardcoded(self):
        catalog = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        term = catalog["cases"][0]["title"][:4]

        with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
            BUILDER_MODULE.validate_catalog(
                catalog,
                forbidden_terms=("term-not-present", term.swapcase()),
            )
        self.assertNotIn(term, str(caught.exception))

        forbidden = "".join(chr(code) for code in (100, 105, 102, 121))
        for path in ROOT.glob("*"):
            if path.suffix in {".json", ".py", ".html"}:
                with self.subTest(path=path.name):
                    self.assertNotIn(
                        forbidden,
                        path.read_text(encoding="utf-8").casefold(),
                    )

    def test_safe_json_for_script_blocks_script_html_and_unicode_breakouts(self):
        malicious = {
            "payload": "</script><script>alert('&')</script>\u2028\u2029",
            "markup": "<img src=x onerror=alert(1)>",
        }

        encoded = BUILDER_MODULE.safe_json_for_script(malicious)

        self.assertNotIn("<", encoded)
        self.assertNotIn(">", encoded)
        self.assertNotIn("&", encoded)
        self.assertNotIn("\u2028", encoded)
        self.assertNotIn("\u2029", encoded)
        self.assertIn("\\u003c", encoded)
        self.assertIn("\\u003e", encoded)
        self.assertIn("\\u0026", encoded)
        self.assertIn("\\u2028", encoded)
        self.assertIn("\\u2029", encoded)
        self.assertEqual(json.loads(encoded), malicious)

    def test_safe_json_for_script_uses_the_exact_canonical_json_contract(self):
        value = {"z": "local/path", "a": ["甲", 1]}
        expected = (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            .replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029")
        )

        self.assertEqual(BUILDER_MODULE.safe_json_for_script(value), expected)

    def test_generated_html_is_strictly_offline_and_has_only_fixed_scripts(self):
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )
        parser = parse_offline_html(rendered)

        self.assertEqual(parser.violations, [])
        self.assertEqual(len(parser.scripts), 2)
        self.assertEqual(
            parser.scripts[0]["attributes"],
            {"id": "catalog-data", "type": "application/json"},
        )
        self.assertEqual(parser.scripts[1]["attributes"], {})
        self.assertEqual(
            parser.runtime_script.strip(),
            BUILDER_MODULE.CONSOLE_JS.strip(),
        )
        self.assertEqual(len(parser.styles), 1)
        css = "".join(parser.styles[0])
        self.assertIsNone(re.search(r"@import\b", css, flags=re.IGNORECASE))
        self.assertIsNone(re.search(r"url\s*\(", css, flags=re.IGNORECASE))
        self.assertNotIn("@font-face", css.casefold())
        self.assertEqual(len(parser.csp_contents), 1)
        directives = {}
        for part in parser.csp_contents[0].split(";"):
            tokens = part.strip().split()
            if tokens:
                directives[tokens[0]] = tokens[1:]
        self.assertEqual(directives["default-src"], ["'none'"])
        self.assertEqual(directives["script-src"], ["'unsafe-inline'"])
        self.assertEqual(directives["style-src"], ["'unsafe-inline'"])
        for directive in (
            "img-src",
            "font-src",
            "connect-src",
            "media-src",
            "object-src",
            "frame-src",
            "base-uri",
            "form-action",
        ):
            with self.subTest(directive=directive):
                self.assertEqual(directives[directive], ["'none'"])
        self.assertLess(
            rendered.index('http-equiv="Content-Security-Policy"'),
            rendered.index("<style>"),
        )

    def test_offline_parser_detects_resource_event_css_and_refresh_mutations(self):
        mutated = r"""
        <base href="https://invalid.example/">
        <meta http-equiv="refresh" content="0;url=/next">
        <link href="/style.css"><img src="local.png" srcset="other.png">
        <iframe src="frame.html" srcdoc="<p>frame</p>"></iframe>
        <object data="object.bin"></object>
        <embed src="embed.bin"><source src="media.bin">
        <video src="video.bin" poster="poster.png"></video>
        <audio src="audio.bin"></audio>
        <track src="captions.vtt"><p onclick="bad()">text</p>
        <svg xlink:href="/asset" xlink|href="/asset-2" xml:base="/"></svg>
        <FoRm AcTiOn="/submit"><button FoRmAcTiOn="/other">send</button></FoRm>
        <a href="#local" ping="/audit">local</a>
        <table background="/table.png"><tr><td>cell</td></tr></table>
        <p STYLE="background:u\72l(local.png)">styled</p>
        <style>@\69mport "local.css"; p { background: url(local.png); }</style>
        """
        parser = parse_offline_html(mutated)
        css = "".join("".join(parts) for parts in parser.styles)

        for violation in (
            "prohibited-tag:base",
            "prohibited-tag:link",
            "prohibited-tag:img",
            "prohibited-tag:iframe",
            "prohibited-tag:object",
            "prohibited-tag:embed",
            "prohibited-tag:source",
            "prohibited-tag:video",
            "prohibited-tag:audio",
            "prohibited-tag:track",
            "meta-refresh",
            "event-attribute:onclick",
            "resource-attribute:src",
            "resource-attribute:srcdoc",
            "resource-attribute:srcset",
            "resource-attribute:poster",
            "resource-attribute:data",
            "resource-attribute:action",
            "resource-attribute:formaction",
            "resource-attribute:ping",
            "resource-attribute:background",
            "resource-attribute:xlink:href",
            "resource-attribute:xml:base",
            "external-href",
            "css-url:attribute",
            "css-import:block",
            "css-url:block",
        ):
            with self.subTest(violation=violation):
                self.assertIn(violation, parser.violations)
        self.assertRegex(css.casefold(), r"@\\69mport\b")
        self.assertRegex(css.casefold(), r"url\s*\(")

    def test_malicious_catalog_text_remains_data_in_python_and_javascript(self):
        self.require_node()
        catalog = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        malicious = (
            "</script><script>globalThis.compromised=true</script>\n"
            "<img src=x onerror=alert(1)>\n"
            '<button onclick="globalThis.compromised=true">x</button>'
            "\u2028\u2029"
        )
        catalog["cases"][0]["inputs"][0]["content"] = malicious

        rendered = BUILDER_MODULE.render_acceptance_html(catalog)
        parser = parse_offline_html(rendered)
        embedded = json.loads(parser.catalog_json)

        self.assertIn("\\u003c", parser.catalog_json)
        self.assertIn("\\u2028", parser.catalog_json)
        self.assertIn("\\u2029", parser.catalog_json)
        self.assertEqual(parser.violations, [])
        self.assertEqual(len(parser.scripts), 2)
        self.assertEqual(
            embedded["cases"][0]["inputs"][0]["content"],
            malicious,
        )
        node_program = (
            '"use strict";'
            'const raw=require("fs").readFileSync(0,"utf8");'
            "const value=JSON.parse(raw);"
            "process.stdout.write(value.cases[0].inputs[0].content);"
        )
        node_result = subprocess.run(
            ["node", "-e", node_program],
            input=parser.catalog_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(node_result.returncode, 0, node_result.stderr)
        self.assertEqual(node_result.stdout, malicious)

    def test_runtime_script_uses_only_the_approved_interaction_contract(self):
        self.require_node()
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )
        script = parse_offline_html(rendered).runtime_script

        for required in (
            "localStorage.getItem",
            "localStorage.setItem",
            "localStorage.removeItem",
            "navigator.clipboard.writeText",
            "JSON.parse",
            "JSON.stringify",
            "window.print",
        ):
            with self.subTest(required=required):
                self.assertIn(required, script)
        forbidden_patterns = {
            "eval": r"(?<![\w$])eval\s*\(",
            "function-constructor": r"\bnew\s+Function\b",
            "document-write": r"\bdocument\s*\.\s*write\s*\(",
            "html-assignment": r"\.\s*(?:innerHTML|outerHTML)\s*=",
            "html-insertion": r"\.\s*insertAdjacentHTML\s*\(",
            "network-request": r"(?<![\w$])fetch\s*\(",
            "xhr": r"\bXMLHttpRequest\b",
            "socket": r"\bWebSocket\b",
            "event-stream": r"\bEventSource\b",
            "beacon": r"\.\s*sendBeacon\s*\(",
            "dynamic-import": r"(?<![\w$])import\s*\(",
        }
        for label, pattern in forbidden_patterns.items():
            with self.subTest(label=label):
                self.assertIsNone(re.search(pattern, script))
        assert_runtime_offline_contract(self, script)
        leak_mutation = "\n".join(
            (
                script,
                'const leak = document.createElement("img");',
                'leak.src = "https:" + "//invalid.example/leak";',
            )
        )
        with self.assertRaises(AssertionError):
            assert_runtime_offline_contract(self, leak_mutation)
        syntax = subprocess.run(
            ["node", "--check", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_safe_element_allowlist_covers_every_literal_factory_tag(self):
        script = parse_offline_html(
            BUILDER_MODULE.render_acceptance_html(
                BUILDER_MODULE.load_catalog(CATALOG)
            )
        ).runtime_script
        safe_tags_match = re.search(
            r"const SAFE_ELEMENT_TAGS = Object\.freeze\(\[(.*?)\]\);",
            script,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(safe_tags_match)
        safe_tags = set(json.loads("[" + safe_tags_match.group(1) + "]"))
        literal_factory_tags = set(
            re.findall(
                r"(?<![\w.])createElement\(\s*[\"']([a-z0-9-]+)[\"']",
                script,
                flags=re.IGNORECASE,
            )
        )
        self.assertIn("article", literal_factory_tags)
        self.assertEqual(literal_factory_tags - safe_tags, set())

    def test_runtime_navigation_mutations_are_rejected_independently_of_csp(self):
        script = parse_offline_html(
            BUILDER_MODULE.render_acceptance_html(
                BUILDER_MODULE.load_catalog(CATALOG)
            )
        ).runtime_script
        assert_runtime_navigation_contract(self, script)
        mutation_groups = {
            "open-functions": (
                'open\n("https:" + "//invalid.example/bare");',
                'window\n.\nopen("https:" + "//invalid.example/window");',
            ),
            "location-sinks": (
                'location = "https:" + "//invalid.example/one";',
                'window\n.\nlocation = "https:" + "//invalid.example/two";',
                'document\n.\nlocation = "https:" + "//invalid.example/three";',
                'location\n.\nhref = "https:" + "//invalid.example/four";',
                'location\n.\nassign("https:" + "//invalid.example/five");',
                'location\n.\nreplace("https:" + "//invalid.example/six");',
                "location\n.\nreload();",
            ),
            "href-sinks": (
                "candidate\n.\nsetAttribute\n('href', target);",
                "candidate\n.\nhref = target;",
            ),
            "extra-click": ("dynamicAnchor\n.\nclick();",),
            "extra-anchor": ("const dynamicAnchor = createElement\n('a');",),
        }
        for label, mutations in mutation_groups.items():
            for index, mutation in enumerate(mutations):
                with self.subTest(label=label, mutation=index):
                    with self.assertRaises(AssertionError):
                        assert_runtime_navigation_contract(
                            self,
                            script + "\n" + mutation,
                        )

    def test_normalize_imported_results_is_pure_exact_and_prototype_safe(self):
        self.require_node()
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )
        exact_keys = re.search(
            r"(function exactKeys\(.*?\n\})\n\n",
            rendered,
            flags=re.DOTALL,
        )
        normalizer = re.search(
            r"(function normalizeImportedResults\(payload\).*?\n\})\n\n"
            r"function serializeResults",
            rendered,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(exact_keys)
        self.assertIsNotNone(normalizer)
        smoke = "\n".join(
            (
                '"use strict";',
                (
                    'const acceptanceCatalog = { catalogVersion: "V1", cases: '
                    '[{ id: "CASE-A" }, { id: "CASE-B" }] };'
                ),
                'const STATUS_VALUES = ["not-run", "passed", "failed", "blocked"];',
                (
                    "const knownIds = new Set("
                    "acceptanceCatalog.cases.map((item) => item.id));"
                ),
                exact_keys.group(1),
                normalizer.group(1),
                (
                    'const valid = { version: "V1", updatedAt: "2026-07-25T00:00:00Z", '
                    "results: { "
                    '"CASE-A": { status: "passed", actual: "ok", notes: "" }, '
                    '"CASE-B": { status: "blocked", actual: "", notes: "wait" } '
                    "} };"
                ),
                "const before = JSON.stringify(valid);",
                "const normalized = normalizeImportedResults(valid);",
                (
                    "if (JSON.stringify(valid) !== before || normalized === valid.results || "
                    'normalized["CASE-A"] === valid.results["CASE-A"]) '
                    'throw new Error("input-mutated-or-aliased");'
                ),
                (
                    'if (JSON.stringify(normalized) !== '
                    '\'{"CASE-A":{"status":"passed","actual":"ok","notes":""},'
                    '"CASE-B":{"status":"blocked","actual":"","notes":"wait"}}\') '
                    'throw new Error("valid-not-normalized");'
                ),
                'normalized["CASE-A"].actual = "changed";',
                (
                    'if (valid.results["CASE-A"].actual !== "ok") '
                    'throw new Error("result-alias");'
                ),
                "const invalid = [",
                '  { ...valid, version: "V2" },',
                "  { ...valid, updatedAt: 1 },",
                "  { results: valid.results, updatedAt: valid.updatedAt },",
                "  { ...valid, extra: true },",
                (
                    "  { ...valid, results: { ...valid.results, "
                    '"CASE-B": undefined, "CASE-X": valid.results["CASE-B"] } },'
                ),
                '  { ...valid, results: { "CASE-A": valid.results["CASE-A"] } },',
                (
                    "  { ...valid, results: { ...valid.results, "
                    '"CASE-A": { ...valid.results["CASE-A"], status: "unknown" } } },'
                ),
                (
                    "  { ...valid, results: { ...valid.results, "
                    '"CASE-A": { ...valid.results["CASE-A"], actual: 7 } } },'
                ),
                (
                    "  { ...valid, results: { ...valid.results, "
                    '"CASE-A": { ...valid.results["CASE-A"], notes: null } } },'
                ),
                (
                    "  { ...valid, results: { ...valid.results, "
                    '"CASE-A": { status: "passed", actual: "ok" } } },'
                ),
                (
                    "  { ...valid, results: { ...valid.results, "
                    '"CASE-A": { ...valid.results["CASE-A"], extra: true } } },'
                ),
                (
                    "  JSON.parse("
                    '\'{\"version\":\"V1\",\"updatedAt\":\"x\",\"results\":{'
                    '\"CASE-A\":{\"status\":\"passed\",\"actual\":\"\",\"notes\":\"\"},'
                    '\"__proto__\":{\"polluted\":true}}}\'),'
                ),
                (
                    "  { ...valid, results: { "
                    '"CASE-A": valid.results["CASE-A"], constructor: { polluted: true } } },'
                ),
                (
                    "  { ...valid, results: { "
                    '"CASE-A": valid.results["CASE-A"], prototype: { polluted: true } } }'
                ),
                "];",
                (
                    "invalid.forEach((value, index) => { let rejected = false; "
                    "try { normalizeImportedResults(value); } catch (error) { rejected = true; } "
                    "if (!rejected) throw new Error('accepted-invalid-' + index); });"
                ),
                (
                    'if (Object.prototype.polluted !== undefined || '
                    '({}).polluted !== undefined) throw new Error("prototype-polluted");'
                ),
            )
        )
        result = subprocess.run(
            ["node", "-"],
            input=smoke,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_embedded_catalog_matches_source_and_has_exact_ordered_id_fields(self):
        source = BUILDER_MODULE.load_catalog(CATALOG)
        rendered = BUILDER_MODULE.render_acceptance_html(source)
        parser = parse_offline_html(rendered)
        embedded = json.loads(parser.catalog_json)
        embedded_ids = tuple(case["id"] for case in embedded["cases"])

        self.assertEqual(embedded, source)
        self.assertEqual(len(embedded["cases"]), 40)
        self.assertEqual(embedded_ids, EXPECTED_IDS)
        for case_id in EXPECTED_IDS:
            with self.subTest(case=case_id):
                field_pattern = (
                    r'"id":'
                    + re.escape(json.dumps(case_id, ensure_ascii=False))
                )
                self.assertEqual(
                    len(re.findall(field_pattern, parser.catalog_json)),
                    1,
                )

    def test_render_acceptance_html_is_complete_static_and_safely_embedded(self):
        catalog = BUILDER_MODULE.load_catalog(CATALOG)

        rendered = BUILDER_MODULE.render_acceptance_html(catalog)

        self.assertIn(catalog["title"], rendered)
        self.assertIn("共 40 条", rendered)
        assert_static_acceptance_articles(self, rendered, catalog["cases"])
        match = re.search(
            r'<script id="catalog-data" type="application/json">(.*?)</script>',
            rendered,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        self.assertEqual(json.loads(match.group(1)), catalog)
        self.assertIn(
            'JSON.parse(document.getElementById("catalog-data").textContent)',
            rendered,
        )

    def test_static_article_contract_rejects_an_empty_case_article(self):
        catalog = BUILDER_MODULE.load_catalog(CATALOG)
        rendered = BUILDER_MODULE.render_acceptance_html(catalog)
        mutated = re.sub(
            r'<article class="acceptance-case">.*?</article>',
            '<article class="acceptance-case"></article>',
            rendered,
            count=1,
            flags=re.DOTALL,
        )
        self.assertNotEqual(mutated, rendered)

        with self.assertRaises(AssertionError):
            assert_static_acceptance_articles(self, mutated, catalog["cases"])

    def test_render_acceptance_html_never_executes_or_injects_user_data(self):
        catalog = deepcopy(BUILDER_MODULE.load_catalog(CATALOG))
        malicious = "</script><script>PRIVATE_ATTACK()</script>\u2028\u2029"
        catalog["title"] = malicious
        catalog["cases"][0]["inputs"][0]["content"] = (
            '<img src=x onerror="PRIVATE_ATTACK()"> & private'
        )

        rendered = BUILDER_MODULE.render_acceptance_html(catalog)

        self.assertNotIn("</script><script>", rendered)
        self.assertNotIn("<img src=x", rendered)
        self.assertNotIn("\u2028", rendered)
        self.assertNotIn("\u2029", rendered)
        for sink in (
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
            "Function(",
        ):
            with self.subTest(sink=sink):
                self.assertNotIn(sink, rendered)

    def test_render_acceptance_html_has_no_external_dependency_or_secret_shape(self):
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )

        for prohibited in (
            "http://",
            "https://",
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "sendBeacon",
            "<script src=",
            "import(",
        ):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited.casefold(), rendered.casefold())
        secret_patterns = (
            re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
            re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
            re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}\b"),
        )
        for pattern in secret_patterns:
            with self.subTest(pattern=pattern.pattern):
                self.assertIsNone(pattern.search(rendered))

    def test_interactive_console_has_unique_semantic_structure_and_labeled_controls(self):
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )
        parser = AcceptanceConsoleParser()
        parser.feed(rendered)
        parser.close()

        self.assertEqual(parser.tag_counts.get("h1"), 1)
        self.assertEqual(parser.tag_counts.get("main"), 1)
        for landmark in ("header", "main", "section", "article", "footer"):
            self.assertGreater(parser.tag_counts.get(landmark, 0), 0, landmark)
        required_ids = {
            "summary-dashboard",
            "case-filters",
            "case-list",
            "import-results",
            "export-results",
            "reset-results",
        }
        self.assertTrue(required_ids.issubset(parser.ids))
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertIn('class="skip-link"', rendered)
        self.assertIn('href="#main-content"', rendered)
        for tag, attributes in parser.controls:
            with self.subTest(tag=tag, control=attributes.get("id")):
                control_id = attributes.get("id")
                has_name = bool(attributes.get("aria-label"))
                has_label = bool(control_id and control_id in parser.label_targets)
                self.assertTrue(has_name or has_label)
        self.assertEqual(parser.external_resources, [])

    def test_dashboard_filters_and_a11y_live_regions_cover_the_acceptance_workflow(self):
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )

        for label in (
            "总数",
            "通过",
            "失败",
            "阻塞",
            "未执行",
            "完成率",
            "关键词",
            "模式",
            "分类",
            "优先级",
            "输入类型",
            "风险",
            "状态",
            "清除筛选",
        ):
            with self.subTest(label=label):
                self.assertIn(label, rendered)
        self.assertGreaterEqual(rendered.count('aria-live="polite"'), 2)
        for state in ("not-run", "passed", "failed", "blocked"):
            self.assertIn(f'"{state}"', rendered)
        self.assertIn("错误放行风险", rendered)
        self.assertIn("错误拒绝风险", rendered)
        self.assertIn("toLocaleLowerCase", rendered)
        self.assertIn("input.content", rendered)

    def test_runtime_case_renderer_covers_every_case_field_with_safe_dom_apis(self):
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )

        for field in (
            "id",
            "title",
            "mode",
            "priority",
            "category",
            "objective",
            "preconditions",
            "inputKinds",
            "inputs",
            "name",
            "format",
            "content",
            "steps",
            "actor",
            "action",
            "expected",
            "expectedOutcome",
            "mustContain",
            "mustNotContain",
            "acceptanceChecks",
            "notes",
        ):
            with self.subTest(field=field):
                self.assertRegex(rendered, rf"\b{field}\b")
        for api in (
            "document.createElement",
            ".textContent",
            ".setAttribute",
            ".append",
            ".replaceChildren",
        ):
            self.assertIn(api, rendered)
        self.assertIn('createElement("code")', rendered)
        self.assertIn('createElement("textarea")', rendered)
        self.assertIn('aria-pressed', rendered)
        self.assertIn("copyInput(input.content, code", rendered)
        for sink in (
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
            "Function(",
        ):
            self.assertNotIn(sink, rendered)

    def test_versioned_storage_and_exact_result_schema_are_embedded(self):
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )

        self.assertIn(
            '"chronic-disease-certification-qc-acceptance:" + '
            "acceptanceCatalog.catalogVersion",
            rendered,
        )
        self.assertIn(
            "JSON.stringify({ version, updatedAt, results })",
            rendered,
        )
        self.assertIn("localStorage.setItem(storageKey", rendered)
        self.assertIn("localStorage.getItem(storageKey)", rendered)
        self.assertIn("localStorage.removeItem(storageKey)", rendered)
        self.assertIn("showNotice(", rendered)
        self.assertIn("normalizeImportedResults", rendered)
        self.assertIn("candidateResults", rendered)

    def test_import_export_reset_copy_and_print_actions_follow_contract(self):
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )

        self.assertIn('accept=".json,application/json"', rendered)
        self.assertIn("慢特病Skill验收结果-", rendered)
        self.assertIn("window.confirm(", rendered)
        self.assertIn("window.print()", rendered)
        self.assertIn("navigator.clipboard.writeText", rendered)
        self.assertIn("document.createRange()", rendered)
        self.assertIn("selection.addRange(range)", rendered)
        self.assertIn("URL.createObjectURL", rendered)
        self.assertIn("URL.revokeObjectURL", rendered)
        self.assertIn('"updatedAt"', rendered)

    def test_console_styles_are_tokenized_responsive_printable_and_restrained(self):
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )

        for token in (
            "--color-bg",
            "--color-surface-strong",
            "--color-success",
            "--color-warning",
            "--color-danger",
            "--space-1",
            "--radius-md",
            "--focus-ring",
            "--motion-fast",
        ):
            with self.subTest(token=token):
                self.assertIn(token, rendered)
        self.assertIn("@media (min-width: 1100px)", rendered)
        self.assertIn("@media (min-width: 600px) and (max-width: 1099px)", rendered)
        self.assertIn("@media (max-width: 599px)", rendered)
        self.assertIn("@media (prefers-reduced-motion: reduce)", rendered)
        self.assertIn("@media print", rendered)
        self.assertIn("break-inside: avoid", rendered)
        self.assertIn("overflow-x: hidden", rendered)
        self.assertNotIn("gradient(", rendered.casefold())
        self.assertNotIn("@import", rendered.casefold())

    def test_interactive_script_has_valid_javascript_syntax(self):
        self.require_node()
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )
        scripts = re.findall(
            r"<script(?: [^>]*)?>(.*?)</script>",
            rendered,
            flags=re.DOTALL,
        )
        interactive = "\n".join(
            script
            for script in scripts
            if "acceptanceCatalog" in script
            and "JSON.parse" in script
        )

        result = subprocess.run(
            ["node", "--check", "-"],
            input=interactive,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_print_view_keeps_status_actual_and_notes_with_full_text(self):
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )

        self.assertIn("print-result-summary", rendered)
        self.assertIn("syncPrintSummary", rendered)
        self.assertIn("printStatus", rendered)
        self.assertIn("printActual", rendered)
        self.assertIn("printNotes", rendered)
        self.assertIn('window.addEventListener("beforeprint"', rendered)
        self.assertIn('window.addEventListener("afterprint"', rendered)
        print_css = rendered.split("@media print", 1)[1].split("</style>", 1)[0]
        self.assertRegex(
            print_css,
            r"\.print-result-summary\s*\{[^}]*display:\s*block",
        )
        self.assertRegex(
            print_css,
            r"\.print-result-value\s*\{[^}]*white-space:\s*pre-wrap",
        )
        self.assertNotRegex(
            print_css,
            r"\.print-result-summary[^}]*display:\s*none",
        )

    def test_every_article_has_fixed_five_stage_timeline_and_separate_steps(self):
        catalog = BUILDER_MODULE.load_catalog(CATALOG)
        rendered = BUILDER_MODULE.render_acceptance_html(catalog)
        parser = AcceptanceArticleParser()
        parser.feed(rendered)
        parser.close()
        expected_stages = (
            "输入清点",
            "用户确认",
            "独立复核",
            "结果对比",
            "正式报告",
        )

        self.assertEqual(len(parser.articles), 40)
        for article, case in zip(parser.articles, catalog["cases"]):
            content = "\n".join(article["text"])
            with self.subTest(case=case["id"]):
                for stage in expected_stages:
                    self.assertIn(stage, content)
                self.assertIn("操作步骤", content)
                for step in case["steps"]:
                    self.assertIn(step["actor"], content)
                    self.assertIn(step["action"], content)
                    self.assertIn(step["expected"], content)
        self.assertIn("WORKFLOW_STAGES", rendered)
        self.assertIn("appendWorkflowTimeline", rendered)
        self.assertIn("appendOperationalSteps", rendered)

    def test_all_cards_are_native_collapsibles_with_complete_summaries(self):
        catalog = BUILDER_MODULE.load_catalog(CATALOG)
        rendered = BUILDER_MODULE.render_acceptance_html(catalog)
        parser = AcceptanceArticleParser()
        parser.feed(rendered)
        parser.close()

        self.assertEqual(len(parser.articles), 40)
        for article, case in zip(parser.articles, catalog["cases"]):
            content = "\n".join(article["text"] + article["attributes"])
            with self.subTest(case=case["id"]):
                self.assertEqual(article["tags"].count("details"), 1)
                self.assertEqual(article["tags"].count("summary"), 1)
                for value in (
                    case["id"],
                    case["title"],
                    case["mode"],
                    case["priority"],
                    "未执行",
                ):
                    self.assertIn(value, content)
        self.assertIn('createElement("details"', rendered)
        self.assertIn('createElement("summary"', rendered)
        self.assertIn('addEventListener("toggle"', rendered)
        self.assertIn("expandedCases", rendered)

    def test_copy_button_never_falls_below_44_pixels(self):
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )

        copy_rules = re.findall(
            r"\.copy-button\s*\{([^}]*)\}",
            rendered,
            flags=re.DOTALL,
        )
        self.assertTrue(copy_rules)
        self.assertTrue(
            all(
                re.search(r"min-height:\s*44px", rule)
                for rule in copy_rules
            )
        )
        self.assertNotRegex(
            rendered,
            r"\.copy-button\s*\{[^}]*min-height:\s*(?:[0-3]?\d|4[0-3])px",
        )

    def test_case_list_is_a_live_section_with_atomic_result_count(self):
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )

        self.assertRegex(
            rendered,
            r'<section id="case-list"[^>]*aria-live="polite"[^>]*>',
        )
        self.assertRegex(
            rendered,
            r'id="result-count"[^>]*role="status"[^>]*'
            r'aria-live="polite"[^>]*aria-atomic="true"',
        )
        self.assertNotIn('<div id="case-list"', rendered)

    def test_node_smoke_executes_print_sync_and_default_expansion_behavior(self):
        self.require_node()
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )
        status_labels = re.search(
            r"(const STATUS_LABELS = \{.*?\};)",
            rendered,
            flags=re.DOTALL,
        )
        workflow_stages = re.search(
            r"(const WORKFLOW_STAGES = \[.*?\];)",
            rendered,
            flags=re.DOTALL,
        )
        expanded_cases = re.search(
            r"(const expandedCases = new Set\(.*?\n\);)",
            rendered,
            flags=re.DOTALL,
        )
        sync_function = re.search(
            r"(function syncPrintSummary\(.*?\n\})\n\n"
            r"function appendPrintResultSummary",
            rendered,
            flags=re.DOTALL,
        )
        for match in (
            status_labels,
            workflow_stages,
            expanded_cases,
            sync_function,
        ):
            self.assertIsNotNone(match)

        smoke = "\n".join(
            (
                '"use strict";',
                status_labels.group(1),
                workflow_stages.group(1),
                (
                    "const acceptanceCatalog = { cases: ["
                    '{ id: "P1-FIRST", priority: "P1" },'
                    '{ id: "P0-SECOND", priority: "P0" },'
                    '{ id: "P1-THIRD", priority: "P1" }'
                    "] };"
                ),
                expanded_cases.group(1),
                (
                    'const results = { CASE: { status: "failed", '
                    'actual: "line 1\\nline 2", notes: "follow-up" } };'
                ),
                sync_function.group(1),
                (
                    "const printSummary = { printStatus: {}, "
                    "printActual: {}, printNotes: {} };"
                ),
                'syncPrintSummary({ id: "CASE" }, printSummary);',
                (
                    'if (printSummary.printStatus.textContent !== "失败" || '
                    'printSummary.printActual.textContent !== "line 1\\nline 2" || '
                    'printSummary.printNotes.textContent !== "follow-up") '
                    'throw new Error("print-sync");'
                ),
                (
                    'if (WORKFLOW_STAGES.map((item) => item[0]).join("→") !== '
                    '"输入清点→用户确认→独立复核→结果对比→正式报告") '
                    'throw new Error("workflow-stages");'
                ),
                (
                    'if (!expandedCases.has("P1-FIRST") || '
                    '!expandedCases.has("P0-SECOND") || '
                    'expandedCases.has("P1-THIRD")) '
                    'throw new Error("default-expansion");'
                ),
            )
        )
        result = subprocess.run(
            ["node", "--check", "-"],
            input=smoke,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(
            ["node", "-"],
            input=smoke,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_node_smoke_keeps_import_transactional_when_storage_write_fails(self):
        self.require_node()
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )
        serialize_function = re.search(
            r"(function serializeResults\(nextResults\).*?\n\})\n\n"
            r"function stringifyResultsDocument",
            rendered,
            flags=re.DOTALL,
        )
        stringify_function = re.search(
            r"(function stringifyResultsDocument\(.*?\n\})\n\n"
            r"function persistResults",
            rendered,
            flags=re.DOTALL,
        )
        persist_function = re.search(
            r"(function persistResults\(nextResults\).*?\n\})\n\n",
            rendered,
            flags=re.DOTALL,
        )
        import_function = re.search(
            r"(async function importResults\(file\).*?\n\})\n\n"
            r"function resetResults",
            rendered,
            flags=re.DOTALL,
        )
        for match in (
            serialize_function,
            stringify_function,
            persist_function,
            import_function,
        ):
            self.assertIsNotNone(match)

        smoke = "\n".join(
            (
                '"use strict";',
                (
                    'const acceptanceCatalog = { catalogVersion: "V1", '
                    'cases: [{ id: "CASE" }] };'
                ),
                'const storageKey = "acceptance:V1";',
                (
                    'const oldResults = { CASE: { status: "not-run", '
                    'actual: "old", notes: "" } };'
                ),
                (
                    'const candidateResults = { CASE: { status: "passed", '
                    'actual: "new", notes: "imported" } };'
                ),
                "let results = oldResults;",
                "let stored = 'old-storage';",
                "let shouldFail = true;",
                "let renders = 0;",
                "let updates = 0;",
                "let hasPendingSave = true;",
                "const notices = [];",
                (
                    "const localStorage = { setItem(key, value) { "
                    'if (shouldFail) throw new Error("quota"); stored = value; } };'
                ),
                "function showNotice(message) { notices.push(message); }",
                "function normalizeImportedResults() { return candidateResults; }",
                "function updateDashboard() { updates += 1; }",
                "function renderCases() { renders += 1; }",
                "function cancelPendingSave() {}",
                serialize_function.group(1),
                stringify_function.group(1),
                persist_function.group(1),
                import_function.group(1),
                "(async () => {",
                (
                    '  const file = { name: "results.json", '
                    'async text() { return "{}"; } };'
                ),
                "  await importResults(file);",
                (
                    "  if (results !== oldResults || stored !== 'old-storage' || "
                    "renders !== 0 || updates !== 0 || notices.length !== 1) "
                    'throw new Error("failed-import-mutated-state");'
                ),
                "  shouldFail = false;",
                "  notices.length = 0;",
                "  await importResults(file);",
                (
                    "  if (results !== candidateResults || renders !== 1 || "
                    "updates !== 1 || notices.length !== 1 || "
                    '!stored.includes("\\"actual\\":\\"new\\"")) '
                    'throw new Error("successful-import-not-applied");'
                ),
                "})().catch((error) => { console.error(error); process.exit(1); });",
            )
        )
        result = subprocess.run(
            ["node", "-"],
            input=smoke,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_node_interaction_mutations_preserve_state_and_export_exact_fields(self):
        self.require_node()
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )
        definitions = []
        patterns = (
            r"(function exactKeys\(.*?\n\})\n\n",
            (
                r"(function normalizeImportedResults\(payload\).*?\n\})\n\n"
                r"function serializeResults"
            ),
            (
                r"(function serializeResults\(nextResults\).*?\n\})\n\n"
                r"function stringifyResultsDocument"
            ),
            (
                r"(function stringifyResultsDocument\(.*?\n\})\n\n"
                r"function persistResults"
            ),
            r"(function persistResults\(nextResults\).*?\n\})\n\n",
            (
                r"(function loadSavedResults\(\).*?\n\})\n\n"
                r"function appendTextList"
            ),
            (
                r"(async function importResults\(file\).*?\n\})\n\n"
                r"function resetResults"
            ),
        )
        for pattern in patterns:
            match = re.search(pattern, rendered, flags=re.DOTALL)
            self.assertIsNotNone(match, pattern)
            definitions.append(match.group(1))

        smoke = "\n".join(
            (
                '"use strict";',
                (
                    'const acceptanceCatalog = { catalogVersion: "V1", cases: '
                    '[{ id: "CASE-A" }, { id: "CASE-B" }] };'
                ),
                'const STATUS_VALUES = ["not-run", "passed", "failed", "blocked"];',
                (
                    "const knownIds = new Set("
                    "acceptanceCatalog.cases.map((item) => item.id));"
                ),
                'const storageKey = "acceptance:V1";',
                'const SAVE_FAILURE_NOTICE = "save-failed";',
                (
                    'const oldResults = { "CASE-A": { status: "not-run", '
                    'actual: "old", notes: "" }, "CASE-B": { status: "not-run", '
                    'actual: "", notes: "" } };'
                ),
                "let results = oldResults;",
                "let storageValue = '{broken';",
                "let storageShouldFail = false;",
                "let hasPendingSave = true;",
                "let updates = 0;",
                "let renders = 0;",
                "const notices = [];",
                (
                    "const localStorage = { getItem() { return storageValue; }, "
                    "setItem(key, value) { if (storageShouldFail) "
                    "throw new Error('quota'); storageValue = value; } };"
                ),
                "function showNotice(message) { notices.push(message); }",
                "function cancelPendingSave() {}",
                "function updateDashboard() { updates += 1; }",
                "function renderCases() { renders += 1; }",
                *definitions,
                (
                    'const valid = { version: "V1", updatedAt: "2026-07-25T00:00:00Z", '
                    'results: { "CASE-A": { status: "passed", actual: "new", notes: "" }, '
                    '"CASE-B": { status: "blocked", actual: "", notes: "wait" } } };'
                ),
                "(async () => {",
                "  loadSavedResults();",
                (
                    '  if (results !== oldResults) '
                    'throw new Error("broken-storage-overwrote");'
                ),
                (
                    '  const wrongVersion = { name: "results.json", async text() { '
                    'return JSON.stringify({ ...valid, version: "V2" }); } };'
                ),
                "  await importResults(wrongVersion);",
                (
                    "  if (results !== oldResults || updates !== 0 || renders !== 0) "
                    'throw new Error("invalid-import-overwrote");'
                ),
                "  storageShouldFail = true;",
                (
                    '  const validFile = { name: "results.json", async text() { '
                    "return JSON.stringify(valid); } };"
                ),
                "  await importResults(validFile);",
                (
                    "  if (results !== oldResults || updates !== 0 || renders !== 0) "
                    'throw new Error("failed-storage-overwrote");'
                ),
                "  storageShouldFail = false;",
                "  await importResults(validFile);",
                (
                    '  if (results === oldResults || results["CASE-A"].actual !== "new" || '
                    "updates !== 1 || renders !== 1) "
                    'throw new Error("valid-import-not-applied");'
                ),
                '  results["CASE-A"].extra = "drop";',
                (
                    '  results["EXTRA"] = { status: "passed", actual: "drop", '
                    'notes: "drop", extra: true };'
                ),
                "  const exported = JSON.parse(serializeResults(results));",
                (
                    "  if (Object.keys(exported).sort().join(',') !== "
                    "'results,updatedAt,version' || exported.version !== 'V1') "
                    'throw new Error("wrong-export-root");'
                ),
                (
                    "  if (Object.keys(exported.results).sort().join(',') !== "
                    "'CASE-A,CASE-B') throw new Error('wrong-export-ids');"
                ),
                (
                    "  if (Object.keys(exported.results['CASE-A']).sort().join(',') !== "
                    "'actual,notes,status') throw new Error('wrong-export-fields');"
                ),
                "})().catch((error) => { console.error(error); process.exit(1); });",
            )
        )
        result = subprocess.run(
            ["node", "-"],
            input=smoke,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_risk_mapping_uses_expected_fields_and_locks_known_directions(self):
        self.require_node()
        catalog = BUILDER_MODULE.load_catalog(CATALOG)
        rendered = BUILDER_MODULE.render_acceptance_html(catalog)
        derive_function = re.search(
            r"(function deriveRisk\(caseData\).*?\n\})\n\n"
            r"function isGateStep",
            rendered,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(derive_function)
        selected = {
            case["id"]: case
            for case in catalog["cases"]
            if case["id"] in {
                "M2-001",
                "M2-002",
                "M2-008",
                "M2-009",
                "M2-010",
            }
        }
        expected = {
            "M2-001": "其他",
            "M2-002": "错误拒绝风险",
            "M2-008": "错误放行风险",
            "M2-009": "错误放行风险",
            "M2-010": "错误拒绝风险",
        }
        smoke = "\n".join(
            (
                '"use strict";',
                "const cases = " + json.dumps(selected, ensure_ascii=False) + ";",
                "const expected = " + json.dumps(expected, ensure_ascii=False) + ";",
                derive_function.group(1),
                (
                    "for (const [id, direction] of Object.entries(expected)) { "
                    "if (deriveRisk(cases[id]) !== direction) "
                    'throw new Error(id + ":" + deriveRisk(cases[id])); }'
                ),
                (
                    "const both = { title: '错误放行风险', objective: '', "
                    "expectedOutcome: '', mustContain: [], acceptanceChecks: [], "
                    "steps: [{ action: '', expected: '错误拒绝风险' }] };"
                ),
                (
                    "if (deriveRisk(both) !== '其他') "
                    'throw new Error("dual-direction");'
                ),
            )
        )
        result = subprocess.run(
            ["node", "-"],
            input=smoke,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_node_fake_timer_debounces_input_and_flushes_latest_value(self):
        self.require_node()
        rendered = BUILDER_MODULE.render_acceptance_html(
            BUILDER_MODULE.load_catalog(CATALOG)
        )
        debounce_block = re.search(
            r"(function cancelPendingSave\(\).*?\n\})\n\n"
            r"(function flushPendingResults\(\).*?\n\})\n\n"
            r"(function scheduleResultsSave\(\).*?\n\})",
            rendered,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(debounce_block)
        self.assertIn("scheduleResultsSave();", rendered)
        self.assertNotRegex(
            rendered,
            r'addEventListener\("input".*?persistResults\(',
        )
        self.assertIn('window.addEventListener("beforeunload"', rendered)
        self.assertIn('document.addEventListener("visibilitychange"', rendered)

        smoke = "\n".join(
            (
                '"use strict";',
                "const SAVE_DELAY_MS = 250;",
                "let pendingSaveTimer = 0;",
                "let hasPendingSave = false;",
                "let results = { CASE: { actual: '' } };",
                "let nextTimerId = 1;",
                "const timers = new Map();",
                "const writes = [];",
                (
                    "const window = { setTimeout(callback, delay) { "
                    "const id = nextTimerId++; timers.set(id, { callback, delay }); "
                    "return id; }, clearTimeout(id) { timers.delete(id); } };"
                ),
                (
                    "function persistResults(nextResults) { "
                    "writes.push(JSON.stringify(nextResults)); return true; }"
                ),
                debounce_block.group(1),
                debounce_block.group(2),
                debounce_block.group(3),
                "results.CASE.actual = 'a'; scheduleResultsSave();",
                "results.CASE.actual = 'ab'; scheduleResultsSave();",
                (
                    "if (writes.length !== 0 || timers.size !== 1) "
                    'throw new Error("not-debounced");'
                ),
                "const timer = Array.from(timers.values())[0];",
                (
                    "if (timer.delay !== 250) "
                    'throw new Error("wrong-delay");'
                ),
                "timers.clear(); timer.callback();",
                (
                    "if (writes.length !== 1 || "
                    '!writes[0].includes("\\"actual\\":\\"ab\\"")) '
                    'throw new Error("latest-value-not-saved");'
                ),
                "results.CASE.actual = 'abc'; scheduleResultsSave();",
                "flushPendingResults();",
                (
                    "if (writes.length !== 2 || "
                    '!writes[1].includes("\\"actual\\":\\"abc\\"") || timers.size !== 0) '
                    'throw new Error("flush-failed");'
                ),
            )
        )
        result = subprocess.run(
            ["node", "-"],
            input=smoke,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_write_text_atomically_normalizes_lf_and_sets_mode(self):
        destination = self.temp_path / "output.html"

        BUILDER_MODULE.write_text_atomically(destination, "甲\r\n乙\r丙\n\n")

        self.assertEqual(destination.read_bytes(), "甲\n乙\n丙\n".encode("utf-8"))
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o644)
        self.assertEqual(list(self.temp_path.glob(".output.html.*.tmp")), [])

    @unittest.skipUnless(os.name == "posix", "POSIX mode contract")
    def test_atomic_success_keeps_stage_private_and_preserves_output_mode(self):
        real_fdopen = os.fdopen
        observed_stage_modes = []

        def inspect_stage_mode(descriptor, *args, **kwargs):
            observed_stage_modes.append(
                stat.S_IMODE(os.fstat(descriptor).st_mode)
            )
            return real_fdopen(descriptor, *args, **kwargs)

        for label, initial_mode in (
            ("new", None),
            ("private", 0o600),
            ("group-readable", 0o640),
        ):
            with self.subTest(label=label):
                destination = self.temp_path / f"{label}.html"
                if initial_mode is not None:
                    destination.write_text("old", encoding="utf-8")
                    destination.chmod(initial_mode)
                with mock.patch("os.fdopen", side_effect=inspect_stage_mode):
                    BUILDER_MODULE.write_text_atomically(destination, "new")
                expected_mode = (
                    0o644 if initial_mode is None else initial_mode
                )
                self.assertEqual(
                    stat.S_IMODE(destination.stat().st_mode),
                    expected_mode,
                )
        self.assertEqual(observed_stage_modes, [0o600, 0o600, 0o600])

    def test_write_text_atomically_rejects_missing_parent_and_output_symlink(self):
        missing_parent = self.temp_path / "missing" / "output.html"
        with self.assertRaises(BUILDER_MODULE.CatalogError):
            BUILDER_MODULE.write_text_atomically(missing_parent, "new")

        target = self.temp_path / "target.html"
        target.write_text("old", encoding="utf-8")
        link = self.temp_path / "output.html"
        try:
            os.symlink(target, link)
        except OSError as error:
            supported_skip = {
                errno.EACCES,
                errno.EPERM,
                getattr(errno, "ENOTSUP", -1),
                getattr(errno, "EOPNOTSUPP", -1),
            }
            if error.errno in supported_skip:
                self.skipTest(f"symlink unavailable: errno {error.errno}")
            raise

        with self.assertRaises(BUILDER_MODULE.CatalogError):
            BUILDER_MODULE.write_text_atomically(link, "new")
        self.assertEqual(target.read_text(encoding="utf-8"), "old")
        self.assertTrue(link.is_symlink())

    def test_write_text_atomically_rejects_same_path_and_relative_alias(self):
        source = self.temp_path / "catalog.json"
        source.write_text("old", encoding="utf-8")

        with self.assertRaises(BUILDER_MODULE.CatalogError):
            BUILDER_MODULE.write_text_atomically(
                source,
                "new",
                source_paths=(source,),
            )

        previous_cwd = Path.cwd()
        try:
            os.chdir(self.temp_path)
            with self.assertRaises(BUILDER_MODULE.CatalogError):
                BUILDER_MODULE.write_text_atomically(
                    Path("catalog.json"),
                    "new",
                    source_paths=(Path(".") / "catalog.json",),
                )
        finally:
            os.chdir(previous_cwd)
        self.assertEqual(source.read_text(encoding="utf-8"), "old")

    def test_write_text_atomically_rejects_hardlink_and_source_symlink_aliases(self):
        source = self.temp_path / "catalog.json"
        source.write_text("old", encoding="utf-8")
        hardlink = self.temp_path / "hardlink.html"
        symlink = self.temp_path / "source-alias.json"
        supported_skip = {
            errno.EACCES,
            errno.EPERM,
            getattr(errno, "ENOTSUP", -1),
            getattr(errno, "EOPNOTSUPP", -1),
        }
        try:
            os.link(source, hardlink)
            os.symlink(source, symlink)
        except OSError as error:
            if error.errno in supported_skip:
                self.skipTest(f"links unavailable: errno {error.errno}")
            raise

        with self.assertRaises(BUILDER_MODULE.CatalogError):
            BUILDER_MODULE.write_text_atomically(
                hardlink,
                "new",
                source_paths=(source,),
            )
        with self.assertRaises(BUILDER_MODULE.CatalogError):
            BUILDER_MODULE.write_text_atomically(
                source,
                "new",
                source_paths=(symlink,),
            )
        self.assertEqual(source.read_text(encoding="utf-8"), "old")

    def test_atomic_write_failures_preserve_existing_bytes_mode_and_cleanup(self):
        real_fdopen = os.fdopen

        class WriteFailingHandle:
            def __init__(self, descriptor, *args, **kwargs):
                self._handle = real_fdopen(descriptor, *args, **kwargs)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return self._handle.__exit__(exc_type, exc_value, traceback)

            def write(self, value):
                del value
                raise OSError("private-write")

        class FlushFailingHandle:
            def __init__(self, descriptor, *args, **kwargs):
                self._handle = real_fdopen(descriptor, *args, **kwargs)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return self._handle.__exit__(exc_type, exc_value, traceback)

            def write(self, value):
                return self._handle.write(value)

            def flush(self):
                raise OSError("private-flush")

        failure_patches = (
            ("write", mock.patch("os.fdopen", side_effect=WriteFailingHandle)),
            ("flush", mock.patch("os.fdopen", side_effect=FlushFailingHandle)),
            ("fsync", mock.patch("os.fsync", side_effect=OSError("private-fsync"))),
            ("replace", mock.patch("os.replace", side_effect=OSError("private-replace"))),
        )
        for label, failure_patch in failure_patches:
            with self.subTest(label=label):
                case_dir = self.temp_path / label
                case_dir.mkdir()
                destination = case_dir / "output.html"
                original = b"private-old\r\nbytes"
                destination.write_bytes(original)
                destination.chmod(0o600)

                with failure_patch:
                    with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                        BUILDER_MODULE.write_text_atomically(destination, "new")

                self.assertNotIn("private-", str(caught.exception))
                self.assertEqual(str(caught.exception), "output_write_error")
                self.assertEqual(destination.read_bytes(), original)
                self.assertEqual(
                    stat.S_IMODE(destination.stat().st_mode),
                    0o600,
                )
                self.assertEqual(
                    list(case_dir.glob(".output.html.*.tmp")),
                    [],
                )

    @unittest.skipUnless(os.name == "posix", "POSIX mode contract")
    def test_mode_failures_happen_before_replace_and_preserve_existing_output(self):
        real_chmod = os.chmod

        def fail_target_mode_once():
            failed = False

            def chmod(path, mode):
                nonlocal failed
                if not failed and mode == 0o640:
                    failed = True
                    raise OSError("private-target-mode")
                return real_chmod(path, mode)

            return chmod

        failures = (
            (
                "fchmod",
                mock.patch(
                    "os.fchmod",
                    side_effect=OSError("private-stage-mode"),
                ),
            ),
            (
                "chmod",
                mock.patch(
                    "os.chmod",
                    side_effect=fail_target_mode_once(),
                ),
            ),
        )
        for label, failure_patch in failures:
            with self.subTest(label=label):
                case_dir = self.temp_path / label
                case_dir.mkdir()
                destination = case_dir / "output.html"
                original = b"private-old-bytes"
                destination.write_bytes(original)
                destination.chmod(0o640)

                with (
                    failure_patch,
                    mock.patch("os.replace", wraps=os.replace) as replace,
                ):
                    with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                        BUILDER_MODULE.write_text_atomically(
                            destination,
                            "new",
                        )

                self.assertEqual(str(caught.exception), "output_write_error")
                replace.assert_not_called()
                self.assertEqual(destination.read_bytes(), original)
                self.assertEqual(
                    stat.S_IMODE(destination.stat().st_mode),
                    0o640,
                )
                self.assertEqual(
                    list(case_dir.glob(".output.html.*.tmp")),
                    [],
                )

    @unittest.skipUnless(os.name == "posix", "POSIX mode contract")
    def test_cleanup_mode_failure_still_unlinks_stage_and_is_controlled(self):
        destination = self.temp_path / "output.html"
        destination.write_bytes(b"old bytes")
        destination.chmod(0o640)
        real_chmod = os.chmod

        def fail_private_cleanup(path, mode):
            if mode == 0o600:
                raise OSError("private-tighten")
            return real_chmod(path, mode)

        with (
            mock.patch(
                "os.replace",
                side_effect=OSError("private-replace"),
            ),
            mock.patch(
                "os.chmod",
                side_effect=fail_private_cleanup,
            ),
        ):
            with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                BUILDER_MODULE.write_text_atomically(destination, "new")

        self.assertEqual(str(caught.exception), "output_cleanup_error")
        self.assertEqual(destination.read_bytes(), b"old bytes")
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o640)
        self.assertEqual(
            list(self.temp_path.glob(".output.html.*.tmp")),
            [],
        )

    @unittest.skipUnless(os.name == "posix", "POSIX mode contract")
    def test_replace_and_cleanup_failure_leaves_private_stage_and_cleanup_error(self):
        destination = self.temp_path / "output.html"
        destination.write_bytes(b"old bytes")
        destination.chmod(0o600)

        with (
            mock.patch(
                "os.replace",
                side_effect=OSError("private-replace"),
            ),
            mock.patch.object(
                Path,
                "unlink",
                side_effect=OSError("private-cleanup"),
            ),
        ):
            with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                BUILDER_MODULE.write_text_atomically(destination, "new")

        self.assertEqual(str(caught.exception), "output_cleanup_error")
        self.assertEqual(destination.read_bytes(), b"old bytes")
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        stages = list(self.temp_path.glob(".output.html.*.tmp"))
        self.assertEqual(len(stages), 1)
        self.assertEqual(stat.S_IMODE(stages[0].stat().st_mode), 0o600)
        stages[0].unlink()

    def test_main_only_converts_controlled_catalog_errors(self):
        output = self.temp_path / "output.html"
        for error_type in (TypeError, ValueError):
            with self.subTest(error_type=error_type.__name__):
                with mock.patch.object(
                    BUILDER_MODULE,
                    "render_acceptance_html",
                    side_effect=error_type("private-programming-error"),
                ):
                    with self.assertRaises(error_type):
                        BUILDER_MODULE.main(
                            [
                                "--catalog",
                                str(CATALOG),
                                "--output",
                                str(output),
                            ]
                        )

    def test_main_reports_cleanup_error_without_traceback_or_details(self):
        destination = self.temp_path / "output.html"
        stderr = io.StringIO()
        with (
            mock.patch(
                "os.replace",
                side_effect=OSError("private-replace"),
            ),
            mock.patch.object(
                Path,
                "unlink",
                side_effect=OSError("private-cleanup"),
            ),
            redirect_stderr(stderr),
        ):
            result = BUILDER_MODULE.main(
                [
                    "--catalog",
                    str(CATALOG),
                    "--output",
                    str(destination),
                ]
            )

        self.assertEqual(result, 1)
        self.assertEqual(stderr.getvalue(), "catalog_error\n")
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertNotIn("private-", stderr.getvalue())
        for stage in self.temp_path.glob(".output.html.*.tmp"):
            stage.unlink()

    def test_successful_replace_syncs_parent_directory(self):
        destination = self.temp_path / "output.html"
        real_fsync = os.fsync
        directory_fsync_calls = []

        def record_fsync(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                directory_fsync_calls.append(descriptor)
            return real_fsync(descriptor)

        with mock.patch("os.fsync", side_effect=record_fsync):
            BUILDER_MODULE.write_text_atomically(destination, "new")

        self.assertEqual(len(directory_fsync_calls), 1)

    def test_directory_fsync_only_ignores_explicit_unsupported_errno(self):
        if not hasattr(BUILDER_MODULE, "_fsync_directory"):
            self.fail("missing directory fsync helper")
        unsupported_open = OSError(errno.EINVAL, "private-unsupported-open")
        with mock.patch("os.open", side_effect=unsupported_open):
            BUILDER_MODULE._fsync_directory(self.temp_path)

        unsupported_fsync = OSError(
            errno.EINVAL,
            "private-unsupported-fsync",
        )
        with (
            mock.patch("os.open", return_value=123),
            mock.patch("os.fsync", side_effect=unsupported_fsync),
            mock.patch("os.close") as close,
        ):
            BUILDER_MODULE._fsync_directory(self.temp_path)
        close.assert_called_once_with(123)

        unexpected = OSError(errno.EIO, "private-io")
        with (
            mock.patch("os.open", return_value=456),
            mock.patch("os.fsync", side_effect=unexpected),
            mock.patch("os.close") as close,
        ):
            with self.assertRaises(BUILDER_MODULE.CatalogError) as caught:
                BUILDER_MODULE._fsync_directory(self.temp_path)
        close.assert_called_once_with(456)
        self.assertEqual(
            str(caught.exception),
            "output_directory_sync_error",
        )
        self.assertNotIn("private-", str(caught.exception))

    def test_render_and_atomic_write_are_byte_deterministic(self):
        catalog = BUILDER_MODULE.load_catalog(CATALOG)
        rendered = BUILDER_MODULE.render_acceptance_html(catalog)
        destination = self.temp_path / "output.html"
        cli_destination = self.temp_path / "cli-output.html"

        BUILDER_MODULE.write_text_atomically(
            destination,
            rendered,
            source_paths=(CATALOG,),
        )
        first = hashlib.sha256(destination.read_bytes()).hexdigest()
        BUILDER_MODULE.write_text_atomically(
            destination,
            BUILDER_MODULE.render_acceptance_html(catalog),
            source_paths=(CATALOG,),
        )
        second = hashlib.sha256(destination.read_bytes()).hexdigest()

        self.assertEqual(first, second)
        expected_bytes = destination.read_bytes()
        self.assertEqual(REPOSITORY_OUTPUT.read_bytes(), expected_bytes)
        cli_result = self.run_cli(CATALOG, output=cli_destination)
        self.assertEqual(cli_result.returncode, 0, cli_result.stderr)
        self.assertEqual(cli_result.stdout.strip(), "catalog_built")
        self.assertEqual(cli_result.stderr, "")
        self.assertEqual(cli_destination.read_bytes(), expected_bytes)

    def test_cli_success(self):
        output = self.temp_path / EXPECTED_GENERATED_FILE
        result = self.run_cli(CATALOG, output=output)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "catalog_built")
        self.assertEqual(result.stderr, "")
        self.assertTrue(output.is_file())
        self.assertIn("M1-001", output.read_text(encoding="utf-8"))

    def test_cli_defaults_are_relative_to_script_across_cwd(self):
        script_dir = self.temp_path / "script"
        other_dir = self.temp_path / "other"
        script_dir.mkdir()
        other_dir.mkdir()
        copied_builder = script_dir / BUILDER.name
        copied_catalog = script_dir / CATALOG.name
        copied_builder.write_bytes(BUILDER.read_bytes())
        copied_catalog.write_bytes(CATALOG.read_bytes())

        result = self.run_cli(cwd=other_dir, builder=copied_builder)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "catalog_built")
        self.assertEqual(result.stderr, "")
        output = script_dir / EXPECTED_GENERATED_FILE
        self.assertTrue(output.is_file())
        self.assertIn("SAFE-006", output.read_text(encoding="utf-8"))

    def test_cli_forbidden_terms_are_repeatable_and_failure_is_generic(self):
        catalog = BUILDER_MODULE.load_catalog(CATALOG)
        sensitive_term = catalog["cases"][0]["title"][:4]
        output = self.temp_path / "output.html"

        result = self.run_cli(
            CATALOG,
            output=output,
            forbidden_terms=("term-not-present", sensitive_term),
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "catalog_error")
        self.assertNotIn(sensitive_term, result.stderr)
        self.assertFalse(output.exists())

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
        sensitive_argument = "--PRIVATE-SECRET-ARGUMENT"
        result = self.run_cli(extra_args=(sensitive_argument,))

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.strip(), "catalog_error")
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn(sensitive_argument, result.stderr)


if __name__ == "__main__":
    unittest.main()
