import copy
import json
import re
import subprocess
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
MODE2_REJECTION_MARKERS = (
    "未予通过",
    "不能通过",
    "不予通过",
    "未通过",
    "不通过",
    "拒绝",
)
MODE1_RENDERER_TARGET_IDS = {
    "analysis",
    "analysis-content",
    "analysis-title",
    "confirmation",
    "confirmation-content",
    "confirmation-title",
    "flash-data",
    "logic",
    "logic-content",
    "logic-title",
    "main",
    "overview",
    "overview-content",
    "page-navigation",
    "report-description",
    "report-error",
    "report-title",
    "sources",
    "sources-content",
    "sources-title",
}
MODE2_RENDERER_TARGET_IDS = {
    "analysis",
    "analysis-content",
    "analysis-heading",
    "confirmation",
    "confirmation-content",
    "confirmation-heading",
    "dimensions",
    "dimensions-content",
    "dimensions-heading",
    "error-panel",
    "flash-data",
    "header-meta",
    "issues",
    "issues-content",
    "issues-heading",
    "main",
    "page-navigation",
    "recommendations",
    "recommendations-content",
    "recommendations-heading",
    "report-shell",
    "report-title",
    "rules",
    "rules-content",
    "rules-heading",
    "scope",
    "scope-content",
    "scope-heading",
    "sources",
    "sources-content",
    "sources-heading",
    "summary",
    "summary-content",
    "summary-heading",
}


def read(path):
    return path.read_text(encoding="utf-8")


def embedded_html(template_path, fixture_path):
    template = read(template_path)
    data = json.loads(read(fixture_path))
    return embedded_html_from_data(template, data)


def embedded_html_from_data(template, data):
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    payload = (
        payload.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return template.replace("__FLASH_DATA_JSON__", payload)


def extract_flash_payload(html):
    match = re.search(
        r'<script id="flash-data" type="application/json">'
        r"(?P<payload>.*?)</script>",
        html,
        re.DOTALL,
    )
    if not match:
        raise AssertionError("HTML must contain the flash-data JSON slot")
    return match.group("payload")


def assert_exact_template_ids(test_case, template, expected_ids):
    actual_ids = re.findall(
        r'<[a-z][^>]*\bid="([^"]+)"[^>]*>',
        template,
        re.IGNORECASE,
    )
    test_case.assertEqual(expected_ids, set(actual_ids))
    for target_id in sorted(expected_ids):
        test_case.assertEqual(
            1,
            actual_ids.count(target_id),
            f'id="{target_id}" must occur exactly once',
        )
    test_case.assertRegex(
        template,
        r'<button\b[^>]*class="[^"]*\bnav-toggle\b[^"]*"[^>]*'
        r'\baria-controls="page-navigation"[^>]*>',
    )


def run_qc_renderer(template_path, payload, action="none", report_kind="qc"):
    template = read(template_path)
    scripts = re.findall(
        r"<script(?:\s[^>]*)?>(.*?)</script>",
        template,
        re.DOTALL | re.IGNORECASE,
    )
    if len(scripts) != 2:
        raise AssertionError("qc template must contain data and renderer scripts")
    elements = []
    for tag_match in re.finditer(
        r"<(?P<tag>[a-z][\w-]*)\b(?P<attrs>[^>]*)>",
        template,
        re.IGNORECASE,
    ):
        attributes = tag_match.group("attrs")
        id_match = re.search(r'\bid="([^"]+)"', attributes, re.IGNORECASE)
        if not id_match:
            continue
        class_match = re.search(
            r'\bclass="([^"]*)"',
            attributes,
            re.IGNORECASE,
        )
        elements.append({
            "id": id_match.group(1),
            "tagName": tag_match.group("tag"),
            "hidden": bool(re.search(
                r"(?:^|\s)hidden(?:\s|=|$)",
                attributes,
                re.IGNORECASE,
            )),
            "className": class_match.group(1) if class_match else "",
        })

    nav_match = re.search(
        r'<nav\b(?P<attrs>[^>]*)\bid="(?P<id>[^"]+)"[^>]*>'
        r"(?P<body>.*?)</nav>",
        template,
        re.DOTALL | re.IGNORECASE,
    )
    if not nav_match:
        raise AssertionError("qc template must contain its real navigation")
    nav_targets = re.findall(
        r'<a\b[^>]*\bhref="#([^"]+)"',
        nav_match.group("body"),
        re.IGNORECASE,
    )

    toggle_match = re.search(
        r'<button\b(?P<attrs>[^>]*)\bclass="[^"]*\bnav-toggle\b[^"]*"'
        r"[^>]*>",
        template,
        re.IGNORECASE,
    )
    if not toggle_match:
        raise AssertionError("qc template must contain its real nav toggle")
    toggle_tag = toggle_match.group(0)
    expanded_match = re.search(
        r'\baria-expanded="([^"]+)"',
        toggle_tag,
        re.IGNORECASE,
    )
    controls_match = re.search(
        r'\baria-controls="([^"]+)"',
        toggle_tag,
        re.IGNORECASE,
    )
    template_model = {
        "reportKind": report_kind,
        "elements": elements,
        "navigation": {
            "id": nav_match.group("id"),
            "targets": nav_targets,
        },
        "toggle": {
            "ariaExpanded": (
                expanded_match.group(1) if expanded_match else "false"
            ),
            "ariaControls": (
                controls_match.group(1) if controls_match else ""
            ),
        },
    }
    payload_text = (
        payload
        if isinstance(payload, str)
        else json.dumps(payload, ensure_ascii=False)
    )
    harness = r"""
const fs = require("fs");
const vm = require("vm");

class ClassList {
  constructor(element) {
    this.element = element;
    this.values = new Set(
      element.className.split(/\s+/).filter(Boolean)
    );
  }
  add(value) {
    this.values.add(value);
    this.element.className = Array.from(this.values).join(" ");
  }
  remove(value) {
    this.values.delete(value);
    this.element.className = Array.from(this.values).join(" ");
  }
  toggle(value, force) {
    const enabled = force === undefined ? !this.values.has(value) : force;
    if (enabled) this.add(value);
    else this.remove(value);
    return enabled;
  }
  contains(value) {
    return this.values.has(value);
  }
}

class Element {
  constructor(tagName, id = "") {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.children = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this.className = "";
    this.classList = new ClassList(this);
    this.hidden = false;
    this.textContent = "";
    this.hash = "";
  }
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  append(...children) {
    children.forEach(child => this.appendChild(child));
  }
  replaceChildren(...children) {
    this.children = [];
    this.append(...children);
  }
  setAttribute(name, value) {
    const stringValue = String(value);
    this.attributes.set(name, stringValue);
    if (name === "href") this.hash = stringValue;
    if (name === "id") this.id = stringValue;
  }
  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }
  hasAttribute(name) {
    return this.attributes.has(name);
  }
  removeAttribute(name) {
    this.attributes.delete(name);
  }
  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }
  dispatch(type) {
    (this.listeners.get(type) || []).forEach(handler => handler({
      currentTarget: this,
      target: this
    }));
  }
  querySelectorAll(selector) {
    if (selector === 'a[href^="#"]') {
      return this.children.filter(child => child.tagName === "A");
    }
    return [];
  }
  focus() {
    document.activeElement = this;
  }
  blur() {
    if (document.activeElement === this) document.activeElement = null;
    this.dispatch("blur");
  }
}

const elements = new Map();
const register = (id, tagName = "div") => {
  const element = new Element(tagName, id);
  elements.set(id, element);
  return element;
};
const templateModel = JSON.parse(
  fs.readFileSync(process.argv[5], "utf8")
);
templateModel.elements.forEach(spec => {
  const element = register(spec.id, spec.tagName);
  element.hidden = spec.hidden;
  element.className = spec.className;
  element.classList = new ClassList(element);
});
const nav = elements.get(templateModel.navigation.id);
templateModel.navigation.targets.forEach(id => {
  const link = new Element("a");
  link.setAttribute("href", `#${id}`);
  nav.appendChild(link);
});
const toggle = new Element("button");
toggle.className = "nav-toggle";
toggle.classList = new ClassList(toggle);
toggle.setAttribute(
  "aria-expanded",
  templateModel.toggle.ariaExpanded
);
toggle.setAttribute(
  "aria-controls",
  templateModel.toggle.ariaControls
);
const sideNav = new Element("aside");
sideNav.className = "side-nav";
sideNav.classList = new ClassList(sideNav);

const document = {
  title: "",
  activeElement: null,
  documentElement: { scrollHeight: 4000 },
  createElement(tagName) {
    return new Element(tagName);
  },
  getElementById(id) {
    return elements.get(id) || null;
  },
  querySelector(selector) {
    if (selector === ".nav-toggle") return toggle;
    if (selector === ".side-nav") return sideNav;
    if (selector.startsWith(".")) {
      const className = selector.slice(1);
      return Array.from(elements.values()).find(
        element => element.classList.contains(className)
      ) || null;
    }
    return null;
  },
  querySelectorAll(selector) {
    if (selector === ".side-nav nav a") return nav ? nav.children : [];
    if (selector === "main section") {
      return templateModel.navigation.targets
        .map(id => elements.get(id))
        .filter(Boolean);
    }
    return [];
  }
};

const window = {
  scrollY: 0,
  innerHeight: 800,
  listeners: new Map(),
  addEventListener(type, handler) {
    this.listeners.set(type, handler);
  }
};

const renderer = fs.readFileSync(process.argv[2], "utf8");
const dataSlot = elements.get("flash-data");
if (dataSlot) {
  dataSlot.textContent = fs.readFileSync(process.argv[3], "utf8");
}
const context = {
  document,
  window,
  console,
  JSON,
  Array,
  Object,
  String,
  Boolean,
  Error,
  Math,
  Set
};
vm.runInNewContext(renderer, context);

if (process.argv[4] === "menu") {
  toggle.dispatch("click");
  if (nav && nav.children[1]) nav.children[1].dispatch("click");
}

const collectText = element => element ? [
  element.textContent,
  ...element.children.flatMap(collectText)
].join(" ") : "";
const descendantsWithClass = (element, className) => {
  if (!element) return [];
  return element.children.flatMap(child => [
    ...(child.className.split(/\s+/).includes(className) ? [child] : []),
    ...descendantsWithClass(child, className)
  ]);
};
const directChild = (element, tagName) =>
  element.children.find(child => child.tagName === tagName) || null;
const serializeTree = element => element ? {
  tag: element.tagName.toLowerCase(),
  id: element.id,
  className: element.className,
  text: element.textContent,
  children: element.children.map(serializeTree)
} : null;
const walk = element => element
  ? [element, ...element.children.flatMap(walk)]
  : [];
const shell = templateModel.reportKind === "certification"
  ? elements.get("main")
  : elements.get("report-shell");
const errorPanel = templateModel.reportKind === "certification"
  ? elements.get("report-error")
  : elements.get("error-panel");
const summary = templateModel.reportKind === "certification"
  ? elements.get("overview-content")
  : elements.get("summary-content");
const rules = elements.get("rules-content");
const scopeContent = elements.get("scope-content");
const sourcesContent = elements.get("sources-content");
const issuesContent = elements.get("issues-content");
const dimensionsContent = elements.get("dimensions-content");
const logicContent = elements.get("logic-content");
const ruleNodes = descendantsWithClass(logicContent, "rule-node");
const extractionNodes = descendantsWithClass(
  logicContent,
  "extraction-node"
);
const logicGroups = descendantsWithClass(logicContent, "logic-group");
const logicChildren = descendantsWithClass(logicContent, "logic-children");
const allElements = Array.from(new Set(
  Array.from(elements.values()).flatMap(walk)
));
const idCounts = {};
allElements.forEach(element => {
  if (element.id) idCounts[element.id] = (idCounts[element.id] || 0) + 1;
});
const scopeHeading = elements.get("scope-heading");
process.stdout.write(JSON.stringify({
  shellHidden: shell ? shell.hidden : null,
  errorHidden: errorPanel ? errorPanel.hidden : null,
  errorText: collectText(errorPanel),
  summaryChildCount: summary ? summary.children.length : null,
  rulesChildCount: rules ? rules.children.length : null,
  summaryText: collectText(summary),
  summaryLabels: summary
    ? summary.children.slice(0, 5).map(card => {
      const label = walk(card).find(item =>
        item.className.split(/\s+/).includes("label")
      );
      return label ? collectText(label).trim() : "";
    })
    : [],
  scopeText: collectText(scopeContent),
  sourcesText: collectText(sourcesContent),
  issuesText: collectText(issuesContent),
  dimensionsText: collectText(dimensionsContent),
  rulesText: collectText(rules),
  sourceIds: sourcesContent
    ? walk(sourcesContent).map(item => item.id).filter(id =>
      id && id !== "sources-content"
    )
    : [],
  sourcePreTexts: sourcesContent
    ? walk(sourcesContent)
      .filter(item => item.tagName === "PRE")
      .map(item => item.textContent)
    : [],
  issueLinkTargets: issuesContent
    ? walk(issuesContent)
      .filter(item => item.tagName === "A")
      .map(item => item.getAttribute("href"))
    : [],
  renderedIssueCount: issuesContent
    ? issuesContent.children.filter(item =>
      item.className.split(/\s+/).includes("issue")
    ).length
    : null,
  ...(templateModel.reportKind === "certification" ? {
    logicTreeShape: {
      groupCount: logicGroups.length,
      childrenCount: logicChildren.length,
      ruleCount: ruleNodes.length,
      extractionCount: extractionNodes.length,
      rulesContainOwnExtractions: ruleNodes.map(rule =>
        descendantsWithClass(rule, "extraction-node").length
      ),
      structure: serializeTree(logicContent)
    },
    ruleNodeCount: ruleNodes.length,
    extractionNodeCount: extractionNodes.length,
    ruleNodeTags: ruleNodes.map(rule => rule.tagName.toLowerCase()),
    extractionNodeTags: extractionNodes.map(
      item => item.tagName.toLowerCase()
    ),
    ruleSummaryTexts: ruleNodes.map(rule =>
      collectText(directChild(rule, "SUMMARY"))
    ),
    extractionSummaryTexts: extractionNodes.map(item =>
      collectText(directChild(item, "SUMMARY"))
    ),
    ruleExtractionSummaryTexts: ruleNodes.map(rule =>
      descendantsWithClass(rule, "extraction-node").map(item =>
        collectText(directChild(item, "SUMMARY"))
      )
    ),
    warningCountsPerRule: ruleNodes.map(rule =>
      descendantsWithClass(rule, "weak-warning").length
    ),
    logicText: collectText(logicContent),
    overviewText: collectText(summary),
    idCounts,
    rulesTabIndex: allElements.find(element => element.id === "rules")
      ?.getAttribute("tabindex") ?? null,
    extractionsTabIndex: allElements.find(
      element => element.id === "extractions"
    )?.getAttribute("tabindex") ?? null
  } : {}),
  focusId: document.activeElement ? document.activeElement.id : null,
  focusTabIndex: scopeHeading
    ? scopeHeading.getAttribute("tabindex")
    : null,
  toggleExpanded: toggle.getAttribute("aria-expanded"),
  navOpen: nav ? nav.classList.contains("is-open") : null
}));
"""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        renderer_path = root / "renderer.js"
        payload_path = root / "payload.json"
        harness_path = root / "harness.js"
        model_path = root / "template-model.json"
        renderer_path.write_text(scripts[1], encoding="utf-8")
        payload_path.write_text(payload_text, encoding="utf-8")
        harness_path.write_text(harness, encoding="utf-8")
        model_path.write_text(
            json.dumps(template_model, ensure_ascii=False),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "node",
                str(harness_path),
                str(renderer_path),
                str(payload_path),
                action,
                str(model_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def run_mode1_renderer(template_path, payload):
    return run_qc_renderer(
        template_path,
        payload,
        report_kind="certification",
    )


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


def normalize_mode2_conclusion_direction(conclusion):
    normalized = re.sub(r"\s+", "", conclusion)
    if any(marker in normalized for marker in MODE2_REJECTION_MARKERS):
        return "does_not_meet"
    if "通过" in normalized:
        return "meets"
    return None


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
    source_types = []
    source_names = []
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
        source_types.append(source["type"])
        source_names.append(source["name"])
    test_case.assertEqual(
        len(source_names),
        len(set(source_names)),
        "source document names must be unique",
    )
    test_case.assertIn("patient_material", source_types)
    test_case.assertIn("audit_result", source_types)
    if profile["standardKind"] == "absent":
        test_case.assertNotIn("standard", source_types)
    else:
        test_case.assertIn("standard", source_types)

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
    if profile["standardKind"] != "absent":
        test_case.assertTrue(
            base_review["materialFacts"],
            "review with a standard requires materialFacts",
        )
        test_case.assertTrue(
            judgments,
            "review with a standard requires ruleJudgments",
        )
        for index, judgment in enumerate(judgments):
            test_case.assertTrue(
                judgment["evidence"],
                f"baseReview.ruleJudgments[{index}].evidence",
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
    issue_dimensions = set()
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
        issue_dimensions.add(issue["dimension"])
    issue_status_dimensions = {
        dimension["name"]
        for dimension in dimensions
        if dimension["status"] == "issue"
    }
    test_case.assertEqual(
        issue_status_dimensions,
        issue_dimensions,
        "issue dimensions and issue records must cover the same dimensions",
    )

    patient_source_text = "\n".join(
        f"{source['name']}\n{source['content']}"
        for source in sources
        if source["type"] == "patient_material"
    )
    audit_material_ids = {
        material_id
        for source in sources
        if source["type"] == "audit_result"
        for material_id in re.findall(r"\d{8,}", source["content"])
    }
    for material_id in audit_material_ids:
        if material_id in patient_source_text:
            continue
        qualified_issues = [
            issue
            for issue in issues
            if issue["dimension"] == "证据提取准确性"
            and issue["severity"] in {"medium", "high"}
            and material_id in issue["sourceReference"]
        ]
        test_case.assertTrue(
            qualified_issues,
            (
                f"audit material ID {material_id} must resolve to patient "
                "material or a medium/high evidence-extraction issue"
            ),
        )

    qc_conclusion = comparison["qcConclusion"]
    risk = comparison["risk"]
    has_issues = bool(issue_status_dimensions)
    has_not_checked = any(
        dimension["status"] == "not_checked"
        for dimension in dimensions
    )
    original_result = normalize_mode2_conclusion_direction(
        comparison["originalConclusion"]
    )
    preliminary_result = base_review["preliminaryResult"]
    condition_status = dimension_statuses["审核条件与结论一致性"]
    directional_mismatch = (
        original_result is not None
        and preliminary_result in {"meets", "does_not_meet"}
        and original_result != preliminary_result
    )
    directional_match = (
        original_result is not None
        and preliminary_result in {"meets", "does_not_meet"}
        and original_result == preliminary_result
    )

    if directional_mismatch:
        test_case.assertEqual("issue", condition_status)
        test_case.assertEqual("problematic", qc_conclusion)
        expected_risk = (
            "false_rejection"
            if original_result == "does_not_meet"
            else "false_approval"
        )
        test_case.assertEqual(expected_risk, risk)
    elif directional_match:
        test_case.assertEqual("passed", condition_status)
    else:
        test_case.assertEqual("not_checked", condition_status)

    if has_issues:
        test_case.assertEqual("problematic", qc_conclusion)
        test_case.assertTrue(issues)
        if not directional_mismatch:
            test_case.assertEqual("none", risk)
    elif has_not_checked:
        test_case.assertEqual("uncertain", qc_conclusion)
        test_case.assertEqual("unknown", risk)
    else:
        test_case.assertEqual(
            {"passed"},
            set(dimension_statuses.values()),
        )
        test_case.assertTrue(
            directional_match,
            "reliable requires a known aligned audit direction",
        )
        test_case.assertEqual("reliable", qc_conclusion)
        test_case.assertEqual("none", risk)

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
    test_case.assertEqual(
        source_names,
        confirmation["inventoryShown"],
        "confirmation inventory must exactly mirror source document names",
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
        test_case.assertNotEqual("reliable", qc_conclusion)

    if profile["standardKind"] == "natural_language":
        test_case.assertEqual(
            [
                f"TMP-R{index:03d}"
                for index in range(1, len(judgments) + 1)
            ],
            [judgment["ruleId"] for judgment in judgments],
        )

    if profile["auditDetail"] == "conclusion_only":
        for name in MODE2_DIMENSIONS[:3]:
            dimension = dimensions[MODE2_DIMENSIONS.index(name)]
            test_case.assertEqual("not_checked", dimension["status"])
        condition_dimension = dimensions[
            MODE2_DIMENSIONS.index("审核条件与结论一致性")
        ]
        rule_dimension = dimensions[MODE2_DIMENSIONS.index("规则维护质量")]
        if profile["standardKind"] == "absent":
            test_case.assertEqual(
                "not_checked",
                condition_dimension["status"],
            )
            test_case.assertEqual("not_checked", rule_dimension["status"])
            test_case.assertEqual("uncertain", qc_conclusion)
            test_case.assertEqual("unknown", risk)
        else:
            test_case.assertNotEqual("not_checked", rule_dimension["status"])
            rule_issue = rule_dimension["status"] == "issue"
            if (
                original_result is None
                or preliminary_result == "uncertain"
            ):
                test_case.assertEqual(
                    "not_checked",
                    condition_dimension["status"],
                )
                if rule_issue:
                    test_case.assertEqual("problematic", qc_conclusion)
                    test_case.assertEqual("none", risk)
                else:
                    test_case.assertEqual("uncertain", qc_conclusion)
                    test_case.assertEqual("unknown", risk)
            elif preliminary_result == original_result:
                test_case.assertEqual("passed", condition_dimension["status"])
                if rule_issue:
                    test_case.assertEqual("problematic", qc_conclusion)
                    test_case.assertEqual("none", risk)
                else:
                    test_case.assertEqual("uncertain", qc_conclusion)
                    test_case.assertEqual("unknown", risk)
            else:
                test_case.assertEqual("issue", condition_dimension["status"])
                test_case.assertEqual("problematic", qc_conclusion)
                expected_risk = (
                    "false_rejection"
                    if original_result == "does_not_meet"
                    else "false_approval"
                )
                test_case.assertEqual(expected_risk, risk)


def assert_natural_language_ambiguity_scenario(test_case, fixture):
    assert_valid_mode2(test_case, fixture)
    test_case.assertEqual(
        "natural_language",
        fixture["inputProfile"]["standardKind"],
    )
    test_case.assertTrue(
        fixture["analysisRecord"]["uncertainties"],
        "conclusion-affecting natural-language ambiguity must be recorded",
    )
    test_case.assertEqual(
        "uncertain",
        fixture["auditComparison"]["qcConclusion"],
    )
    test_case.assertEqual("unknown", fixture["auditComparison"]["risk"])


def assert_directional_risk_scenario(
    test_case,
    fixture,
    original_conclusion,
    preliminary_result,
    expected_risk,
):
    assert_valid_mode2(test_case, fixture)
    test_case.assertEqual(
        original_conclusion,
        fixture["auditComparison"]["originalConclusion"],
    )
    test_case.assertEqual(
        preliminary_result,
        fixture["baseReview"]["preliminaryResult"],
    )
    test_case.assertEqual(expected_risk, fixture["auditComparison"]["risk"])


def assert_conclusion_only_direction_scenario(
    test_case,
    fixture,
    original_conclusion,
    preliminary_result,
    condition_status,
    qc_conclusion,
    risk,
):
    assert_valid_mode2(test_case, fixture)
    test_case.assertEqual(
        "conclusion_only",
        fixture["inputProfile"]["auditDetail"],
    )
    test_case.assertEqual(
        ["not_checked", "not_checked", "not_checked"],
        [dimension["status"] for dimension in fixture["dimensions"][:3]],
    )
    test_case.assertEqual(
        original_conclusion,
        fixture["auditComparison"]["originalConclusion"],
    )
    test_case.assertEqual(
        preliminary_result,
        fixture["baseReview"]["preliminaryResult"],
    )
    test_case.assertEqual(
        condition_status,
        fixture["dimensions"][3]["status"],
    )
    test_case.assertEqual(
        qc_conclusion,
        fixture["auditComparison"]["qcConclusion"],
    )
    test_case.assertEqual(risk, fixture["auditComparison"]["risk"])
    if fixture["inputProfile"]["standardKind"] == "absent":
        test_case.assertEqual(
            "not_checked",
            fixture["dimensions"][4]["status"],
        )
    else:
        test_case.assertNotEqual(
            "not_checked",
            fixture["dimensions"][4]["status"],
        )


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
                    "name": "患者材料-2079388752224174082",
                    "type": "patient_material",
                    "content": (
                        "材料ID2079388752224174082原文："
                        "患者材料明确记载证据 A。"
                    ),
                },
                {
                    "name": "患者补充材料-2079388752224174083",
                    "type": "patient_material",
                    "content": (
                        "材料ID2079388752224174083原文："
                        "患者补充材料明确记载证据 B。"
                    ),
                },
                {
                    "name": "认定标准",
                    "type": "standard",
                    "content": (
                        "正式规则码1001：要求满足证据 A；"
                        "逻辑引用1001。"
                    ),
                },
                {
                    "name": "原审核结果",
                    "type": "audit_result",
                    "content": (
                        "finalResult=不通过；ruleResults：1001 不通过；"
                        "1001_01: 原审核认定证据 A 缺失，"
                        "引用材料ID2079388752224174082；"
                        "advice：重新核验材料后复核结论。"
                    ),
                },
            ],
            self.fixture["sourceDocuments"],
        )
        self.assertEqual(
            ["1001"],
            [
                judgment["ruleId"]
                for judgment in self.fixture["baseReview"]["ruleJudgments"]
            ],
        )
        source_names = [
            source["name"] for source in self.fixture["sourceDocuments"]
        ]
        self.assertEqual(
            source_names,
            self.fixture["confirmation"]["inventoryShown"],
        )
        self.assertEqual(len(source_names), len(set(source_names)))

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

        missing_patient_material = copy.deepcopy(self.fixture)
        missing_patient_material["sourceDocuments"] = [
            source
            for source in missing_patient_material["sourceDocuments"]
            if source["type"] != "patient_material"
        ]
        mutations["missing patient material"] = missing_patient_material

        missing_audit_result = copy.deepcopy(self.fixture)
        missing_audit_result["sourceDocuments"] = [
            source
            for source in missing_audit_result["sourceDocuments"]
            if source["type"] != "audit_result"
        ]
        mutations["missing audit result"] = missing_audit_result

        missing_structured_standard = copy.deepcopy(self.fixture)
        missing_structured_standard["sourceDocuments"] = [
            source
            for source in missing_structured_standard["sourceDocuments"]
            if source["type"] != "standard"
        ]
        mutations["missing structured standard"] = missing_structured_standard

        empty_detailed_facts = copy.deepcopy(self.fixture)
        empty_detailed_facts["baseReview"]["materialFacts"] = []
        mutations["empty detailed material facts"] = empty_detailed_facts

        empty_detailed_judgments = copy.deepcopy(self.fixture)
        empty_detailed_judgments["baseReview"]["ruleJudgments"] = []
        mutations["empty detailed rule judgments"] = empty_detailed_judgments

        empty_detailed_evidence = copy.deepcopy(self.fixture)
        empty_detailed_evidence["baseReview"]["ruleJudgments"][0]["evidence"] = []
        mutations["empty detailed judgment evidence"] = empty_detailed_evidence

        reliable_with_issues = copy.deepcopy(self.fixture)
        reliable_with_issues["auditComparison"]["qcConclusion"] = "reliable"
        reliable_with_issues["auditComparison"]["risk"] = "none"
        mutations["reliable with issues"] = reliable_with_issues

        reliable_with_risk = copy.deepcopy(self.fixture)
        reliable_with_risk["auditComparison"]["qcConclusion"] = "reliable"
        reliable_with_risk["issues"] = []
        for dimension in reliable_with_risk["dimensions"]:
            dimension["status"] = "passed"
            dimension["summary"] = "本维度复核通过"
        mutations["reliable with non-none risk"] = reliable_with_risk

        problematic_without_issues = copy.deepcopy(self.fixture)
        problematic_without_issues["issues"] = []
        for dimension in problematic_without_issues["dimensions"]:
            dimension["status"] = "passed"
            dimension["summary"] = "本维度复核通过"
        mutations["problematic without issues"] = problematic_without_issues

        uncertain_without_unknown_risk = copy.deepcopy(self.fixture)
        uncertain_without_unknown_risk["auditComparison"]["qcConclusion"] = (
            "uncertain"
        )
        mutations["uncertain without unknown risk"] = uncertain_without_unknown_risk

        missing_issue_record = copy.deepcopy(self.fixture)
        missing_issue_record["issues"] = missing_issue_record["issues"][:1]
        mutations["issue dimension without record"] = missing_issue_record

        record_for_passed_dimension = copy.deepcopy(self.fixture)
        record_for_passed_dimension["issues"][0]["dimension"] = "证据提取准确性"
        mutations["record for passed dimension"] = record_for_passed_dimension

        for name, mutation in mutations.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, mutation)

    def test_rejects_inventory_omissions_extras_reordering_and_duplicate_names(self):
        missing = copy.deepcopy(self.fixture)
        missing["confirmation"]["inventoryShown"] = missing["confirmation"][
            "inventoryShown"
        ][:-1]

        extra = copy.deepcopy(self.fixture)
        extra["confirmation"]["inventoryShown"].append("额外材料")

        reordered = copy.deepcopy(self.fixture)
        reordered["confirmation"]["inventoryShown"] = list(
            reversed(reordered["confirmation"]["inventoryShown"])
        )

        duplicate_name = copy.deepcopy(self.fixture)
        duplicate_name["sourceDocuments"][1]["name"] = duplicate_name[
            "sourceDocuments"
        ][0]["name"]
        duplicate_name["confirmation"]["inventoryShown"] = [
            source["name"] for source in duplicate_name["sourceDocuments"]
        ]

        for name, mutation in {
            "missing": missing,
            "extra": extra,
            "reordered": reordered,
            "duplicate source name": duplicate_name,
        }.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, mutation)

    def test_accepts_reliable_report_without_issue_dimensions_or_risk(self):
        reliable = copy.deepcopy(self.fixture)
        reliable["auditComparison"]["qcConclusion"] = "reliable"
        reliable["auditComparison"]["risk"] = "none"
        reliable["auditComparison"]["summary"] = "复核未发现原审核存在质量问题"
        reliable["auditComparison"]["originalConclusion"] = "通过"
        reliable["analysisRecord"]["preliminaryConclusion"] = (
            "原审核判断与患者材料及认定标准一致"
        )
        for source in reliable["sourceDocuments"]:
            if source["type"] == "audit_result":
                source["content"] = "原审核认定证据 A 已提供，结论为通过。"
        reliable["issues"] = []
        for dimension in reliable["dimensions"]:
            dimension["status"] = "passed"
            dimension["summary"] = "本维度复核通过"
            dimension["notCheckedReason"] = ""

        assert_valid_mode2(self, reliable)

    def test_accepts_problematic_local_issue_without_directional_risk(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["auditComparison"] = {
            "originalConclusion": "通过",
            "qcConclusion": "problematic",
            "risk": "none",
            "summary": "存在局部规则维护问题，但不改变本次通过结论",
        }
        fixture["analysisRecord"]["preliminaryConclusion"] = (
            "独立复核结果与原审核通过方向一致"
        )
        for source in fixture["sourceDocuments"]:
            if source["type"] == "audit_result":
                source["content"] = "原审核认定证据 A 已提供，结论为通过。"
        fixture["issues"] = [
            {
                "id": "I001",
                "dimension": "规则维护质量",
                "severity": "low",
                "auditClaim": "规则编号格式可直接用于维护",
                "actualEvidence": "认定标准中的规则编号格式不统一",
                "sourceReference": "认定标准：测试条款",
                "impact": "影响规则维护效率但不改变本次审核方向",
                "recommendation": "统一规则编号格式",
            }
        ]
        for dimension in fixture["dimensions"]:
            dimension["status"] = "passed"
            dimension["summary"] = "本维度复核通过"
            dimension["notCheckedReason"] = ""
        fixture["dimensions"][4]["status"] = "issue"
        fixture["dimensions"][4]["summary"] = "规则编号格式存在局部维护问题"
        fixture["recommendations"] = ["统一规则编号格式"]

        assert_valid_mode2(self, fixture)

    def brief_fixture(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["inputProfile"]["auditDetail"] = "brief"
        for source in fixture["sourceDocuments"]:
            if source["type"] == "audit_result":
                source["content"] = (
                    "原审核摘要主张证据 A 缺失，结论为不通过。"
                )
        fixture["analysisRecord"]["inputSummary"] = [
            "已收到患者材料、结构化标准和简要审核结果"
        ]
        fixture["dimensions"][2]["status"] = "not_checked"
        fixture["dimensions"][2]["summary"] = "简要审核结果未展示推理过程"
        fixture["dimensions"][2]["notCheckedReason"] = "未提供完整审核过程"
        return fixture

    def test_accepts_brief_report_with_independent_base_review_evidence(self):
        assert_valid_mode2(self, self.brief_fixture())

    def test_rejects_brief_report_with_empty_base_review_evidence(self):
        empty_facts = self.brief_fixture()
        empty_facts["baseReview"]["materialFacts"] = []

        empty_judgments = self.brief_fixture()
        empty_judgments["baseReview"]["ruleJudgments"] = []

        empty_evidence = self.brief_fixture()
        empty_evidence["baseReview"]["ruleJudgments"][0]["evidence"] = []

        for name, mutation in {
            "material facts": empty_facts,
            "rule judgments": empty_judgments,
            "judgment evidence": empty_evidence,
        }.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, mutation)

    def conclusion_only_fixture(
        self,
        original_conclusion,
        preliminary_result,
        condition_status,
        qc_conclusion,
        risk,
    ):
        fixture = copy.deepcopy(self.fixture)
        fixture["inputProfile"]["auditDetail"] = "conclusion_only"
        fixture["auditComparison"] = {
            "originalConclusion": original_conclusion,
            "qcConclusion": qc_conclusion,
            "risk": risk,
            "summary": "仅依据原审核结论方向与独立复核结果进行质控",
        }
        fixture["analysisRecord"]["inputSummary"] = [
            "已收到患者材料、结构化标准和原审核结论"
        ]
        fixture["analysisRecord"]["preliminaryConclusion"] = (
            "只能独立复核患者材料与认定标准，并比较原审核结论方向"
        )
        if preliminary_result == "does_not_meet":
            for source in fixture["sourceDocuments"]:
                if source["type"] == "patient_material":
                    source["content"] = "患者材料未记载证据 A。"
            fixture["analysisRecord"]["evidenceFindings"] = [
                "患者材料未提供证据 A"
            ]
            fixture["baseReview"]["materialFacts"] = [
                "患者材料未记载证据 A"
            ]
            fixture["baseReview"]["ruleJudgments"][0] = {
                "ruleId": "1001",
                "result": "not_met",
                "evidence": ["患者材料：未记载证据 A"],
                "reason": "材料中缺少标准要求的证据 A",
            }
        fixture["baseReview"]["preliminaryResult"] = preliminary_result
        for source in fixture["sourceDocuments"]:
            if source["type"] == "audit_result":
                source["content"] = f"原审核结论为{original_conclusion}。"
        fixture["issues"] = []
        for dimension in fixture["dimensions"][:3]:
            dimension["status"] = "not_checked"
            dimension["summary"] = "原审核仅提供结论，过程依赖维度无法核查"
            dimension["notCheckedReason"] = "未提供审核主张、证据和规则过程"
        condition_dimension = fixture["dimensions"][3]
        condition_dimension["status"] = condition_status
        condition_dimension["notCheckedReason"] = (
            "原审核结论方向不明确"
            if condition_status == "not_checked"
            else ""
        )
        if condition_status == "issue":
            condition_dimension["summary"] = (
                "独立复核结果与原审核结论方向相反"
            )
            fixture["issues"] = [
                {
                    "id": "I001",
                    "dimension": "审核条件与结论一致性",
                    "severity": "high",
                    "auditClaim": f"原审核结论为{original_conclusion}",
                    "actualEvidence": (
                        f"独立复核结果为{preliminary_result}"
                    ),
                    "sourceReference": "患者材料与认定标准：测试条款",
                    "impact": "可能改变申请的通过或不通过方向",
                    "recommendation": "按独立复核结果重新判定最终结论",
                }
            ]
        elif condition_status == "passed":
            condition_dimension["summary"] = (
                "独立复核结果与原审核结论方向一致"
            )
        else:
            condition_dimension["summary"] = (
                "原审核结论方向不明确，无法比较一致性"
            )
        return fixture

    def conclusion_only_scenarios(self):
        return (
            (
                "错误拒绝",
                self.conclusion_only_fixture(
                    "不通过",
                    "meets",
                    "issue",
                    "problematic",
                    "false_rejection",
                ),
                "不通过",
                "meets",
                "issue",
                "problematic",
                "false_rejection",
            ),
            (
                "错误通过",
                self.conclusion_only_fixture(
                    "通过",
                    "does_not_meet",
                    "issue",
                    "problematic",
                    "false_approval",
                ),
                "通过",
                "does_not_meet",
                "issue",
                "problematic",
                "false_approval",
            ),
            (
                "方向一致",
                self.conclusion_only_fixture(
                    "通过",
                    "meets",
                    "passed",
                    "uncertain",
                    "unknown",
                ),
                "通过",
                "meets",
                "passed",
                "uncertain",
                "unknown",
            ),
            (
                "方向未知",
                self.conclusion_only_fixture(
                    "方向未明确",
                    "meets",
                    "not_checked",
                    "uncertain",
                    "unknown",
                ),
                "方向未明确",
                "meets",
                "not_checked",
                "uncertain",
                "unknown",
            ),
        )

    def test_accepts_table_driven_conclusion_only_direction_scenarios(self):
        for (
            name,
            fixture,
            original,
            preliminary,
            condition_status,
            qc_conclusion,
            risk,
        ) in self.conclusion_only_scenarios():
            with self.subTest(scenario=name):
                assert_conclusion_only_direction_scenario(
                    self,
                    fixture,
                    original,
                    preliminary,
                    condition_status,
                    qc_conclusion,
                    risk,
                )

    def test_generic_validator_rejects_known_conclusion_only_mismatches(self):
        hidden_error_rejection = self.conclusion_only_fixture(
            "不通过",
            "meets",
            "not_checked",
            "uncertain",
            "unknown",
        )
        reliable_consistency = self.conclusion_only_fixture(
            "通过",
            "meets",
            "passed",
            "reliable",
            "none",
        )
        wrong_directional_risk = self.conclusion_only_fixture(
            "不通过",
            "meets",
            "issue",
            "problematic",
            "false_approval",
        )
        invented_unknown_direction = self.conclusion_only_fixture(
            "方向未明确",
            "meets",
            "passed",
            "uncertain",
            "unknown",
        )

        for name, mutation in {
            "hidden error rejection": hidden_error_rejection,
            "reliable consistency": reliable_consistency,
            "wrong directional risk": wrong_directional_risk,
            "invented unknown direction": invented_unknown_direction,
        }.items():
            with self.subTest(mismatch=name):
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, mutation)

    def absent_conclusion_only_fixture(self):
        fixture = self.conclusion_only_fixture(
            "不通过",
            "uncertain",
            "not_checked",
            "uncertain",
            "unknown",
        )
        fixture["inputProfile"]["standardKind"] = "absent"
        fixture["sourceDocuments"] = [
            source
            for source in fixture["sourceDocuments"]
            if source["type"] != "standard"
        ]
        fixture["confirmation"]["inventoryShown"] = [
            source["name"] for source in fixture["sourceDocuments"]
        ]
        fixture["baseReview"]["ruleJudgments"] = []
        fixture["baseReview"]["preliminaryResult"] = "uncertain"
        fixture["dimensions"][3]["status"] = "not_checked"
        fixture["dimensions"][3]["summary"] = (
            "标准缺失，无法独立得出审核方向"
        )
        fixture["dimensions"][3]["notCheckedReason"] = "未提供认定标准"
        fixture["dimensions"][4]["status"] = "not_checked"
        fixture["dimensions"][4]["summary"] = (
            "标准缺失，无法检查规则维护质量"
        )
        fixture["dimensions"][4]["notCheckedReason"] = "未提供认定标准"
        fixture["issues"] = []
        return fixture

    def test_accepts_absent_conclusion_only_uncertain_outcome(self):
        assert_valid_mode2(self, self.absent_conclusion_only_fixture())

    def test_rejects_absent_conclusion_only_cross_field_claims(self):
        passed_condition = self.absent_conclusion_only_fixture()
        passed_condition["dimensions"][3]["status"] = "passed"
        passed_condition["dimensions"][3]["notCheckedReason"] = ""

        reliable = self.absent_conclusion_only_fixture()
        reliable["auditComparison"]["qcConclusion"] = "reliable"
        reliable["auditComparison"]["risk"] = "none"

        directional_issue = self.absent_conclusion_only_fixture()
        directional_issue["dimensions"][3]["status"] = "issue"
        directional_issue["dimensions"][3]["notCheckedReason"] = ""
        directional_issue["auditComparison"]["qcConclusion"] = "problematic"
        directional_issue["auditComparison"]["risk"] = "false_rejection"
        directional_issue["issues"] = [
            {
                "id": "I001",
                "dimension": "审核条件与结论一致性",
                "severity": "high",
                "auditClaim": "原审核结论为不通过",
                "actualEvidence": "未提供标准却声称可独立得出方向",
                "sourceReference": "原审核结果：测试结论",
                "impact": "可能错误推断审核方向",
                "recommendation": "补充认定标准后再比较方向",
            }
        ]

        for name, mutation in {
            "passed condition": passed_condition,
            "reliable outcome": reliable,
            "directional issue": directional_issue,
        }.items():
            with self.subTest(mismatch=name):
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, mutation)

    def test_accepts_conclusion_only_local_rule_issue_without_directional_risk(self):
        fixture = self.conclusion_only_scenarios()[3][1]
        fixture["dimensions"][4]["status"] = "issue"
        fixture["dimensions"][4]["summary"] = "可见标准存在规则编号维护问题"
        fixture["issues"] = [
            {
                "id": "I001",
                "dimension": "规则维护质量",
                "severity": "low",
                "auditClaim": "规则编号格式便于维护",
                "actualEvidence": "标准中的规则编号格式不统一",
                "sourceReference": "认定标准：测试条款",
                "impact": "影响维护效率但不改变审核方向",
                "recommendation": "统一规则编号格式",
            }
        ]
        fixture["auditComparison"]["qcConclusion"] = "problematic"
        fixture["auditComparison"]["risk"] = "none"

        assert_valid_mode2(self, fixture)

    def direction_consistent_rule_issue_fixture(self):
        fixture = self.conclusion_only_scenarios()[2][1]
        fixture["dimensions"][4]["status"] = "issue"
        fixture["dimensions"][4]["summary"] = "可见标准存在规则编号维护问题"
        fixture["issues"] = [
            {
                "id": "I001",
                "dimension": "规则维护质量",
                "severity": "low",
                "auditClaim": "规则编号格式便于维护",
                "actualEvidence": "标准中的规则编号格式不统一",
                "sourceReference": "认定标准：测试条款",
                "impact": "影响维护效率但不改变审核方向",
                "recommendation": "统一规则编号格式",
            }
        ]
        fixture["auditComparison"]["qcConclusion"] = "problematic"
        fixture["auditComparison"]["risk"] = "none"
        return fixture

    def test_accepts_direction_consistent_rule_issue_as_problematic_none(self):
        assert_valid_mode2(self, self.direction_consistent_rule_issue_fixture())

    def test_rejects_uncertain_unknown_when_an_actual_issue_exists(self):
        fixture = self.direction_consistent_rule_issue_fixture()
        fixture["auditComparison"]["qcConclusion"] = "uncertain"
        fixture["auditComparison"]["risk"] = "unknown"

        with self.assertRaises(AssertionError):
            assert_valid_mode2(self, fixture)

    def test_accepts_conclusion_only_direction_issue_with_local_rule_issue(self):
        fixture = self.conclusion_only_scenarios()[0][1]
        fixture["dimensions"][4]["status"] = "issue"
        fixture["dimensions"][4]["summary"] = "可见标准存在规则编号维护问题"
        fixture["issues"].append(
            {
                "id": "I002",
                "dimension": "规则维护质量",
                "severity": "low",
                "auditClaim": "规则编号格式便于维护",
                "actualEvidence": "标准中的规则编号格式不统一",
                "sourceReference": "认定标准：测试条款",
                "impact": "影响维护效率但不改变错误拒绝风险方向",
                "recommendation": "统一规则编号格式",
            }
        )

        assert_valid_mode2(self, fixture)

    def test_rejects_conclusion_only_process_checks_and_direction_mismatches(self):
        for index, dimension_name in enumerate(MODE2_DIMENSIONS[:3]):
            fixture = self.conclusion_only_scenarios()[3][1]
            fixture["dimensions"][index]["status"] = "passed"
            fixture["dimensions"][index]["notCheckedReason"] = ""
            with self.subTest(process_dimension=dimension_name):
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, fixture)

        mismatches = []

        hidden_error_rejection = self.conclusion_only_fixture(
            "不通过",
            "meets",
            "not_checked",
            "uncertain",
            "unknown",
        )
        mismatches.append(("hidden error rejection", hidden_error_rejection))

        wrong_rejection_risk = self.conclusion_only_scenarios()[0][1]
        wrong_rejection_risk["auditComparison"]["risk"] = "false_approval"
        mismatches.append(("wrong rejection risk", wrong_rejection_risk))

        missing_rejection_risk = self.conclusion_only_scenarios()[0][1]
        missing_rejection_risk["auditComparison"]["risk"] = "none"
        mismatches.append(("missing rejection risk", missing_rejection_risk))

        hidden_consistency = self.conclusion_only_fixture(
            "通过",
            "meets",
            "not_checked",
            "uncertain",
            "unknown",
        )
        mismatches.append(("hidden consistency", hidden_consistency))

        invented_unknown_direction = self.conclusion_only_fixture(
            "方向未明确",
            "meets",
            "passed",
            "uncertain",
            "unknown",
        )
        mismatches.append(("invented unknown direction", invented_unknown_direction))

        unchecked_visible_standard = self.conclusion_only_scenarios()[3][1]
        unchecked_visible_standard["dimensions"][4]["status"] = "not_checked"
        unchecked_visible_standard["dimensions"][4]["summary"] = (
            "错误地跳过可见标准"
        )
        unchecked_visible_standard["dimensions"][4]["notCheckedReason"] = (
            "原审核过程不可见"
        )
        mismatches.append(("unchecked visible standard", unchecked_visible_standard))

        expected = self.conclusion_only_scenarios()
        expected_by_name = {
            "hidden error rejection": expected[0][2:],
            "wrong rejection risk": expected[0][2:],
            "missing rejection risk": expected[0][2:],
            "hidden consistency": expected[2][2:],
            "invented unknown direction": expected[3][2:],
            "unchecked visible standard": expected[3][2:],
        }
        for name, fixture in mismatches:
            with self.subTest(mismatch=name):
                with self.assertRaises(AssertionError):
                    assert_conclusion_only_direction_scenario(
                        self,
                        fixture,
                        *expected_by_name[name],
                    )

    def natural_language_fixture(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["inputProfile"]["standardKind"] = "natural_language"
        second_judgment = copy.deepcopy(fixture["baseReview"]["ruleJudgments"][0])
        fixture["baseReview"]["ruleJudgments"].append(second_judgment)
        for index, judgment in enumerate(
            fixture["baseReview"]["ruleJudgments"],
            start=1,
        ):
            judgment["ruleId"] = f"TMP-R{index:03d}"
        return fixture

    def test_accepts_consecutive_natural_language_temp_rule_ids(self):
        assert_valid_mode2(self, self.natural_language_fixture())

    def test_accepts_non_conclusion_uncertainty_with_definite_qc_result(self):
        fixture = self.natural_language_fixture()
        fixture["analysisRecord"]["uncertainties"] = [
            "来源材料的页码标注不清晰，但不影响证据 A 的认定"
        ]

        self.assertEqual(
            "problematic",
            fixture["auditComparison"]["qcConclusion"],
        )
        self.assertEqual(
            "false_rejection",
            fixture["auditComparison"]["risk"],
        )
        assert_valid_mode2(self, fixture)

    def test_rejects_duplicate_or_nonsequential_natural_language_temp_ids(self):
        duplicate = self.natural_language_fixture()
        duplicate["baseReview"]["ruleJudgments"][1]["ruleId"] = "TMP-R001"

        starts_at_999 = self.natural_language_fixture()
        starts_at_999["baseReview"]["ruleJudgments"][0]["ruleId"] = "TMP-R999"

        for name, mutation in {
            "duplicate": duplicate,
            "starts at 999": starts_at_999,
        }.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_valid_mode2(self, mutation)

    def ambiguous_natural_language_fixture(self):
        fixture = self.natural_language_fixture()
        fixture["analysisRecord"]["uncertainties"] = [
            "自然语言标准中“证据充分”的含义存在影响结论的歧义"
        ]
        fixture["analysisRecord"]["preliminaryConclusion"] = (
            "自然语言标准存在影响结论的歧义，质控结论不确定"
        )
        fixture["auditComparison"]["qcConclusion"] = "uncertain"
        fixture["auditComparison"]["risk"] = "unknown"
        fixture["auditComparison"]["summary"] = (
            "自然语言标准的关键含义不明确，无法确定原审核是否可靠"
        )
        fixture["baseReview"]["preliminaryResult"] = "uncertain"
        fixture["issues"] = []
        for dimension in fixture["dimensions"]:
            dimension["status"] = "passed"
            dimension["summary"] = "本维度未发现实际问题"
            dimension["notCheckedReason"] = ""
        fixture["dimensions"][3]["status"] = "not_checked"
        fixture["dimensions"][3]["summary"] = (
            "独立复核方向不确定，无法比较结论一致性"
        )
        fixture["dimensions"][3]["notCheckedReason"] = (
            "自然语言标准存在影响结论的歧义"
        )
        return fixture

    def test_accepts_natural_language_conclusion_ambiguity_degradation(self):
        assert_natural_language_ambiguity_scenario(
            self,
            self.ambiguous_natural_language_fixture(),
        )

    def test_rejects_unrecorded_or_non_degraded_natural_language_ambiguity(self):
        missing_uncertainty = self.ambiguous_natural_language_fixture()
        missing_uncertainty["analysisRecord"]["uncertainties"] = []

        definite_conclusion = self.ambiguous_natural_language_fixture()
        definite_conclusion["auditComparison"]["qcConclusion"] = "problematic"

        directional_risk = self.ambiguous_natural_language_fixture()
        directional_risk["auditComparison"]["risk"] = "false_rejection"

        for name, mutation in {
            "missing uncertainty": missing_uncertainty,
            "definite conclusion": definite_conclusion,
            "directional risk": directional_risk,
        }.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_natural_language_ambiguity_scenario(self, mutation)

    def false_approval_fixture(self):
        fixture = copy.deepcopy(self.fixture)
        for source in fixture["sourceDocuments"]:
            if source["type"] == "patient_material":
                source["content"] = "患者材料未记载证据 A。"
            elif source["type"] == "audit_result":
                source["content"] = (
                    "原审核认定证据 A 已满足，结论为通过。"
                )
        fixture["analysisRecord"]["evidenceFindings"] = [
            "患者材料未提供证据 A"
        ]
        fixture["analysisRecord"]["preliminaryConclusion"] = (
            "原审核的满足判断与患者材料不一致"
        )
        fixture["baseReview"]["materialFacts"] = ["患者材料未记载证据 A"]
        fixture["baseReview"]["ruleJudgments"][0] = {
            "ruleId": "1001",
            "result": "not_met",
            "evidence": ["患者材料：未记载证据 A"],
            "reason": "材料中缺少标准要求的证据 A",
        }
        fixture["baseReview"]["preliminaryResult"] = "does_not_meet"
        fixture["auditComparison"] = {
            "originalConclusion": "通过",
            "qcConclusion": "problematic",
            "risk": "false_approval",
            "summary": "原审核将未满足的证据条件判为满足，可能导致错误通过",
        }
        fixture["dimensions"][0]["summary"] = "原审核未识别证据 A 实际缺失"
        fixture["dimensions"][1]["summary"] = (
            "复核能够从患者材料中准确识别证据 A 缺失"
        )
        fixture["dimensions"][3]["summary"] = (
            "证据 A 未满足标准要求，但原审核仍给出通过结论"
        )
        fixture["issues"][0].update(
            {
                "auditClaim": "原审核主张证据 A 已满足",
                "actualEvidence": "患者材料未记载证据 A",
                "impact": "可能导致不符合条件的申请被错误通过",
                "recommendation": "重新核对证据 A 的缺失状态",
            }
        )
        fixture["issues"][1].update(
            {
                "auditClaim": "原审核以证据 A 已满足为由给出通过结论",
                "actualEvidence": "证据 A 不满足认定标准要求",
                "impact": "可能造成审核条件与通过结论不一致",
                "recommendation": "根据证据 A 未满足的事实修正审核结论",
            }
        )
        fixture["recommendations"] = [
            "重新核对患者材料中的证据 A",
            "复核并修正最终审核结论",
        ]
        return fixture

    def test_accepts_paired_false_rejection_and_false_approval_directions(self):
        assert_directional_risk_scenario(
            self,
            self.fixture,
            "不通过",
            "meets",
            "false_rejection",
        )

        false_approval = self.false_approval_fixture()
        assert_directional_risk_scenario(
            self,
            false_approval,
            "通过",
            "does_not_meet",
            "false_approval",
        )

    def test_rejects_reversed_canonical_and_false_approval_directions(self):
        reversed_rejection = copy.deepcopy(self.fixture)
        reversed_rejection["auditComparison"]["risk"] = "false_approval"

        reversed_approval = self.false_approval_fixture()
        reversed_approval["auditComparison"]["risk"] = "false_rejection"

        missing_rejection_risk = copy.deepcopy(self.fixture)
        missing_rejection_risk["auditComparison"]["risk"] = "none"

        missing_approval_risk = self.false_approval_fixture()
        missing_approval_risk["auditComparison"]["risk"] = "none"

        scenarios = (
            (
                "reversed rejection",
                reversed_rejection,
                "不通过",
                "meets",
                "false_rejection",
            ),
            (
                "reversed approval",
                reversed_approval,
                "通过",
                "does_not_meet",
                "false_approval",
            ),
            (
                "missing rejection risk",
                missing_rejection_risk,
                "不通过",
                "meets",
                "false_rejection",
            ),
            (
                "missing approval risk",
                missing_approval_risk,
                "通过",
                "does_not_meet",
                "false_approval",
            ),
        )
        for name, fixture, original, preliminary, expected_risk in scenarios:
            with self.subTest(scenario=name):
                with self.assertRaises(AssertionError):
                    assert_directional_risk_scenario(
                        self,
                        fixture,
                        original,
                        preliminary,
                        expected_risk,
                    )

    def test_accepts_absent_profile_and_rejects_standard_or_rule_review(self):
        absent = copy.deepcopy(self.fixture)
        absent["inputProfile"]["standardKind"] = "absent"
        absent["sourceDocuments"] = [
            source
            for source in absent["sourceDocuments"]
            if source["type"] != "standard"
        ]
        absent["confirmation"]["inventoryShown"] = [
            source["name"] for source in absent["sourceDocuments"]
        ]
        absent["analysisRecord"]["inputSummary"] = [
            "已收到患者材料和详细审核结果，未提供认定标准"
        ]
        absent["analysisRecord"]["interpretations"] = [
            "未提供认定标准，不判断独立政策资格"
        ]
        absent["analysisRecord"]["preliminaryConclusion"] = (
            "原审核的材料缺失主张有问题，独立资格结论不确定"
        )
        absent["baseReview"]["ruleJudgments"] = []
        absent["baseReview"]["preliminaryResult"] = "uncertain"
        absent["auditComparison"]["risk"] = "none"
        absent["auditComparison"]["summary"] = (
            "材料缺失主张与患者材料不符，但无标准时无法判断独立资格"
        )
        absent["dimensions"][3]["status"] = "not_checked"
        absent["dimensions"][3]["summary"] = "未提供认定标准，无法核查条件与结论一致性"
        absent["dimensions"][3]["notCheckedReason"] = "未提供认定标准"
        absent["dimensions"][4]["status"] = "not_checked"
        absent["dimensions"][4]["summary"] = "未提供认定标准，无法检查规则维护质量"
        absent["dimensions"][4]["notCheckedReason"] = "未提供认定标准"
        absent["issues"] = [
            issue
            for issue in absent["issues"]
            if issue["dimension"] != "审核条件与结论一致性"
        ]

        assert_valid_mode2(self, absent)

        with_standard = copy.deepcopy(absent)
        with_standard["sourceDocuments"].append(
            {
                "name": "不应存在的标准",
                "type": "standard",
                "content": "标准内容",
            }
        )
        with_standard["confirmation"]["inventoryShown"] = [
            source["name"] for source in with_standard["sourceDocuments"]
        ]
        with_judgment = copy.deepcopy(absent)
        with_judgment["baseReview"]["ruleJudgments"] = [
            {
                "ruleId": "1001",
                "result": "met",
                "evidence": ["证据 A"],
                "reason": "错误地执行了规则判断",
            }
        ]
        with_policy_result = copy.deepcopy(absent)
        with_policy_result["baseReview"]["preliminaryResult"] = "meets"
        with_rule_maintenance_check = copy.deepcopy(absent)
        with_rule_maintenance_check["dimensions"][4]["status"] = "passed"
        with_rule_maintenance_check["dimensions"][4]["summary"] = (
            "错误地声称已检查规则维护质量"
        )
        with_rule_maintenance_check["dimensions"][4]["notCheckedReason"] = ""

        for name, mutation in {
            "standard source": with_standard,
            "rule judgment": with_judgment,
            "policy result": with_policy_result,
            "rule maintenance check": with_rule_maintenance_check,
        }.items():
            with self.subTest(mutation=name):
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
        self.assertRegex(
            section,
            r"(?m)^5\. .*只依据患者材料和认定标准.*`baseReview`",
        )
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
            "至少一项 `patient_material`",
            "至少一项 `audit_result`",
            "`reliable` 时",
            "`problematic` 时",
            "`uncertain` 时",
            "连续且唯一",
            "不论 `auditDetail`",
            "`false_approval` 表示原审核通过",
            "`false_rejection` 表示原审核不通过",
            "`both` 表示同时存在错误通过和错误拒绝风险",
            "影响结论的歧义",
            "`analysisRecord.uncertainties` 必须非空",
            "`problematic` 时允许 `risk=none`",
            "不改变通过/不通过方向",
            "前三个过程依赖维度",
            "第四个“审核条件与结论一致性”维度",
            "规则维护质量不依赖 `auditDetail`",
            "`confirmation.inventoryShown`",
            "`sourceDocuments[].name`",
            "顺序和内容完全一致",
            "文档名不得重复",
            "方向一致时",
            "必须使用 `qcConclusion=uncertain`、`risk=unknown`",
            "禁止使用 `reliable`",
            "`standardKind=absent` 且 `auditDetail=conclusion_only`",
            "规则维护质量存在明确局部问题",
            "`qcConclusion=problematic`、`risk=none`",
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

    def test_output_checklist_requires_mode2_risk_direction_self_check(self):
        checklist = read(
            SKILL_ROOT / "references" / "output-checklist.md"
        )
        for marker in (
            "baseReview.preliminaryResult",
            "auditComparison.originalConclusion",
            "false_approval（错误通过）",
            "false_rejection（错误拒绝）",
            "both（双向风险）",
            "problematic + none",
            "前三个过程依赖维度",
            "审核条件与结论一致性",
            "confirmation.inventoryShown",
            "sourceDocuments[].name",
            "方向一致也必须使用不确定结论",
            "禁止标为可靠",
            "标准缺失且仅有原审核结论",
            "局部规则维护问题",
        ):
            self.assertIn(marker, checklist)


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
        for section_id in (
            "overview",
            "logic",
            "analysis",
            "sources",
            "confirmation",
        ):
            self.assertEqual(
                1,
                len(
                    re.findall(
                        rf'<section\b[^>]*\bid="{section_id}"[^>]*>',
                        self.template,
                    )
                ),
            )
        for nested_anchor in ("rules", "extractions"):
            self.assertNotRegex(
                self.template,
                rf'<section\b[^>]*\bid="{nested_anchor}"[^>]*>',
            )

    def test_all_renderer_target_ids_exist_exactly_once(self):
        assert_exact_template_ids(
            self,
            self.template,
            MODE1_RENDERER_TARGET_IDS,
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

    def test_validate_has_minimal_fail_closed_delivery_gates(self):
        for marker in (
            'data.schemaVersion !== "flash-1.0"',
            'data.mode !== "certification"',
            "data.confirmation.confirmed !== true",
        ):
            self.assertIn(marker, self.template)

    def test_error_state_hides_formal_report_and_shows_chinese_message(self):
        self.assertRegex(
            self.template,
            r'<div\b[^>]*\bid="report-error"[^>]*\bhidden[^>]*>',
        )
        self.assertLess(
            self.template.index('id="report-error"'),
            self.template.index('class="app-shell"'),
        )
        self.assertIn('byId("main").hidden = true', self.template)
        self.assertIn("errorBox.hidden = false", self.template)
        self.assertIn("无法生成报告", self.template)

    def test_node_vm_harness_executes_valid_mode1_fixture(self):
        fixture = json.loads(read(self.fixture_path))
        state = run_mode1_renderer(self.template_path, fixture)
        self.assertFalse(state["shellHidden"])
        self.assertTrue(state["errorHidden"])
        self.assertGreater(state["summaryChildCount"], 0)
        self.assertGreater(state["ruleNodeCount"], 0)

    def test_node_vm_harness_fail_closes_delivery_gate_violations(self):
        fixture = json.loads(read(self.fixture_path))
        mutations = (
            (
                "schema",
                "报告数据版本必须为 flash-1.0",
                lambda item: item.update(schemaVersion="flash-0.9"),
            ),
            (
                "mode",
                "报告数据模式必须为 certification",
                lambda item: item.update(mode="qc"),
            ),
            (
                "confirmation",
                "正式报告需要用户确认",
                lambda item: item["confirmation"].update(confirmed=False),
            ),
        )
        for name, message, mutate in mutations:
            with self.subTest(gate=name):
                candidate = copy.deepcopy(fixture)
                mutate(candidate)
                state = run_mode1_renderer(self.template_path, candidate)
                self.assertTrue(state["shellHidden"])
                self.assertFalse(state["errorHidden"])
                self.assertIn(message, state["errorText"])

    def test_template_embeds_exact_mode1_fixture(self):
        fixture = json.loads(read(self.fixture_path))
        html = embedded_html(self.template_path, self.fixture_path)

        self.assertIn("测试病种甲", html)
        self.assertIn("R001", html)
        payload = extract_flash_payload(html)
        self.assertNotEqual("__FLASH_DATA_JSON__", payload.strip())
        self.assertEqual(fixture, json.loads(payload))

    def test_hostile_source_content_cannot_break_out_of_data_slot(self):
        hostile = (
            "</script><script>"
            "globalThis.__flashOwned=true"
            "</script><&>"
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
        payload = re.search(
            r'<script id="flash-data" type="application/json">'
            r"(?P<payload>.*?)</script>",
            hostile_html,
            re.DOTALL,
        )
        self.assertIsNotNone(payload)
        restored = json.loads(payload.group("payload"))
        self.assertEqual(fixture, restored)
        self.assertEqual(
            hostile,
            restored["sourceDocuments"][0]["content"],
        )
        script_tags = re.findall(
            r"<script\b[^>]*>",
            hostile_html,
            re.IGNORECASE,
        )
        original_script_tags = re.findall(
            r"<script\b[^>]*>",
            self.template,
            re.IGNORECASE,
        )
        executable_scripts = [
            tag
            for tag in script_tags
            if 'type="application/json"' not in tag
        ]
        self.assertEqual(len(original_script_tags), len(script_tags))
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


class FlashQcReportTemplateTests(unittest.TestCase):
    def setUp(self):
        self.template_path = SKILL_ROOT / "assets" / "qc-report-template.html"
        self.fixture_path = ACCEPTANCE_ROOT / "fixtures" / "valid-mode2.json"
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
        script_tags = re.findall(r"<script\b[^>]*>", self.template, re.IGNORECASE)
        self.assertEqual(2, len(script_tags))
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
            "createElement",
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
            ("summary", "结论总览"),
            ("scope", "输入范围"),
            ("dimensions", "五维检查"),
            ("issues", "问题清单"),
            ("rules", "逐规则复核"),
            ("recommendations", "建议"),
            ("analysis", "分析记录"),
            ("sources", "原始材料"),
            ("confirmation", "确认记录"),
        )
        for section_id, label in navigation:
            self.assertIn(f'<a href="#{section_id}">{label}</a>', self.template)
            self.assertEqual(
                1,
                len(
                    re.findall(
                        rf'<section\b[^>]*\bid="{section_id}"[^>]*>',
                        self.template,
                    )
                ),
            )

    def test_all_renderer_target_ids_exist_exactly_once(self):
        assert_exact_template_ids(
            self,
            self.template,
            MODE2_RENDERER_TARGET_IDS,
        )

    def test_template_exposes_accessible_navigation_and_print_details(self):
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
        self.assertEqual(1, len(re.findall(r"<h1\b", self.template, re.IGNORECASE)))
        self.assertIn(":focus-visible", self.template)
        self.assertIn(
            "details:not([open]) > :not(summary)",
            self.template,
        )
        self.assertRegex(
            self.template,
            r"details:not\(\[open\]\) > :not\(summary\)\s*\{\s*"
            r"display:\s*block\s*!important;",
        )

    def test_renderer_declares_all_approved_chinese_mappings(self):
        mappings = (
            'structured: "结构化标准"',
            'natural_language: "自然语言标准"',
            'absent: "未提供标准"',
            'detailed: "详细审核结果"',
            'brief: "简要审核结果"',
            'conclusion_only: "仅审核结论"',
            'met: "满足"',
            'not_met: "不满足"',
            'unknown: "无法判断"',
            'meets: "符合"',
            'does_not_meet: "不符合"',
            'uncertain: "无法确定"',
            'reliable: "可靠"',
            'problematic: "存在问题"',
            'none: "未发现明显风险"',
            'false_approval: "错误放行风险"',
            'false_rejection: "错误拒绝风险"',
            'both: "双向风险"',
            'passed: "已通过"',
            'issue: "发现问题"',
            'not_checked: "未检查"',
            'high: "高"',
            'medium: "中"',
            'low: "低"',
            'patient_material: "患者材料"',
            'standard: "认定标准"',
            'audit_result: "原审核结果"',
            'true: "已确认"',
            'false: "未确认"',
            'two_stage_non_blind: "两阶段复核：先独立判断，再对照原审核"',
        )
        for mapping in mappings:
            self.assertIn(mapping, self.template)

    def test_renderer_declares_complete_mode2_fields_and_empty_states(self):
        for field in (
            "standardKind",
            "auditDetail",
            "materialsConfirmedComplete",
            "materialFacts",
            "ruleJudgments",
            "preliminaryResult",
            "originalConclusion",
            "qcConclusion",
            "risk",
            "dimensions",
            "notCheckedReason",
            "auditClaim",
            "actualEvidence",
            "sourceReference",
            "impact",
            "recommendation",
            "inputSummary",
            "interpretations",
            "evidenceFindings",
            "uncertainties",
            "preliminaryConclusion",
            "inventoryShown",
            "userResponse",
        ):
            self.assertIn(field, self.template)
        for empty_state in (
            "未发现质控问题",
            "暂无改进建议",
            "无",
        ):
            self.assertIn(empty_state, self.template)

    def test_error_state_hides_report_and_replaces_partial_output(self):
        self.assertRegex(
            self.template,
            r'<div\b[^>]*\bid="error-panel"[^>]*\bhidden[^>]*>',
        )
        self.assertRegex(
            self.template,
            r'<div\b[^>]*\bclass="shell"[^>]*\bid="report-shell"[^>]*>',
        )
        self.assertIn("const showError = error =>", self.template)
        self.assertIn('byId("report-shell").hidden = true', self.template)
        self.assertIn("panel.replaceChildren(", self.template)
        self.assertIn("showError(error)", self.template)
        error_panel = self.template.index('id="error-panel"')
        report_shell = self.template.index('id="report-shell"')
        self.assertLess(error_panel, report_shell)

    def test_rules_section_renders_full_base_review(self):
        rules_renderer = self.template[
            self.template.index("const renderRules = data =>"):
            self.template.index("const renderRecommendations = data =>")
        ]
        for required in (
            "review.materialFacts",
            "review.preliminaryResult",
            "review.ruleJudgments",
            '"本次质控提取的患者材料事实"',
            '"独立复核初步结果"',
        ):
            self.assertIn(required, rules_renderer)

    def test_analysis_long_content_is_collapsible_and_print_visible(self):
        renderer = self.template[
            self.template.index("const makeAnalysisCard ="):
            self.template.index("const requireObject =")
        ]
        self.assertIn('node("details")', renderer)
        self.assertIn('node("summary", title)', renderer)
        self.assertIn('"detail-body"', renderer)
        self.assertIn(
            'makeAnalysisCard("初步结论", [analysis.preliminaryConclusion])',
            self.template,
        )
        self.assertIn(
            "details:not([open]) > :not(summary)",
            self.template,
        )

    def test_renderer_javascript_has_valid_syntax(self):
        scripts = re.findall(
            r"<script(?:\s[^>]*)?>(.*?)</script>",
            self.template,
            re.DOTALL | re.IGNORECASE,
        )
        self.assertEqual(2, len(scripts))
        with tempfile.TemporaryDirectory() as directory:
            script_path = Path(directory) / "renderer.js"
            script_path.write_text(scripts[1], encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script_path)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_validate_has_minimal_fail_closed_quality_gates(self):
        for marker in (
            'data.schemaVersion !== "flash-1.0"',
            "data.inputProfile.materialsConfirmedComplete !== true",
            "data.confirmation.confirmed !== true",
            "standardKinds",
            "auditDetails",
            "preliminaryResults",
            "qcConclusions",
            "riskValues",
            "dimensionNames",
            "dimensionStatuses",
            "sourceTypes",
            "ruleResults",
            "issueSeverities",
        ):
            self.assertIn(marker, self.template)

    def test_node_vm_harness_executes_valid_fixture(self):
        fixture = json.loads(read(self.fixture_path))
        state = run_qc_renderer(self.template_path, fixture)
        self.assertFalse(state["shellHidden"])
        self.assertTrue(state["errorHidden"])
        self.assertGreater(state["summaryChildCount"], 0)
        self.assertGreater(state["rulesChildCount"], 2)

    def test_node_vm_harness_uses_ids_from_passed_template(self):
        fixture = json.loads(read(self.fixture_path))
        broken_template = self.template.replace(
            'id="summary-content"',
            'id="summary-content-broken"',
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            template_path = Path(directory) / "broken-template.html"
            template_path.write_text(broken_template, encoding="utf-8")
            state = run_qc_renderer(template_path, fixture)

        self.assertTrue(state["shellHidden"])
        self.assertFalse(state["errorHidden"])
        self.assertIsNone(state["summaryChildCount"])
        self.assertIn("replaceChildren", state["errorText"])

    def test_node_vm_harness_fail_closes_bad_json(self):
        state = run_qc_renderer(self.template_path, "{ bad json")
        self.assertTrue(state["shellHidden"])
        self.assertFalse(state["errorHidden"])
        self.assertIn("无法解析报告数据", state["errorText"])

    def test_node_vm_harness_fail_closes_critical_false_gates(self):
        fixture = json.loads(read(self.fixture_path))
        mutations = (
            ("schema", lambda item: item.update(schemaVersion="flash-0.9")),
            (
                "materials",
                lambda item: item["inputProfile"].update(
                    materialsConfirmedComplete=False
                ),
            ),
            (
                "confirmation",
                lambda item: item["confirmation"].update(confirmed=False),
            ),
        )
        for name, mutate in mutations:
            with self.subTest(gate=name):
                candidate = copy.deepcopy(fixture)
                mutate(candidate)
                state = run_qc_renderer(self.template_path, candidate)
                self.assertTrue(state["shellHidden"])
                self.assertFalse(state["errorHidden"])

    def test_node_vm_harness_fail_closes_invalid_dimension(self):
        fixture = json.loads(read(self.fixture_path))
        fixture["dimensions"][1]["name"] = "自定义维度"
        fixture["dimensions"][2]["status"] = "skipped"
        state = run_qc_renderer(self.template_path, fixture)
        self.assertTrue(state["shellHidden"])
        self.assertFalse(state["errorHidden"])
        self.assertIn("五维", state["errorText"])

    def test_mobile_menu_link_moves_focus_to_target_heading(self):
        fixture = json.loads(read(self.fixture_path))
        state = run_qc_renderer(self.template_path, fixture, action="menu")
        self.assertEqual("scope-heading", state["focusId"])
        self.assertEqual("-1", state["focusTabIndex"])
        self.assertEqual("false", state["toggleExpanded"])
        self.assertFalse(state["navOpen"])
        self.assertIn(
            'heading.addEventListener("blur"',
            self.template,
        )
        mobile = self.template[self.template.index("@media (max-width: 980px)"):]
        self.assertRegex(
            mobile,
            r"section\s*\{[^}]*scroll-margin-top:\s*5\.5rem;",
        )

    def test_empty_dimensions_raise_visible_chinese_contract_error(self):
        fixture = json.loads(read(self.fixture_path))
        fixture["dimensions"] = []
        self.assert_embedded_fixture_has_error_contract(
            fixture,
            "if (!data.dimensions.length)",
            "未提供五维复核结果",
        )

    def test_empty_sources_raise_visible_chinese_contract_error(self):
        fixture = json.loads(read(self.fixture_path))
        fixture["sourceDocuments"] = []
        self.assert_embedded_fixture_has_error_contract(
            fixture,
            "if (!data.sourceDocuments.length)",
            "未提供原始材料",
        )

    def test_missing_required_field_and_bad_json_have_visible_chinese_errors(self):
        self.assertIn(
            'data.schemaVersion !== "flash-1.0"',
            self.template,
        )
        self.assertIn(
            'data.mode !== "qc"',
            self.template,
        )
        self.assertIn(
            'throw new Error("数据不是模式 2 质控报告")',
            self.template,
        )
        self.assertIn("无法解析报告数据", self.template)
        self.assertIn("报告数据不完整", self.template)

    def test_template_embeds_exact_mode2_fixture(self):
        fixture = json.loads(read(self.fixture_path))
        html = embedded_html(self.template_path, self.fixture_path)
        self.assertIn("测试审核质控报告", html)
        self.assertIn("I002", html)
        payload = extract_flash_payload(html)
        self.assertNotEqual("__FLASH_DATA_JSON__", payload.strip())
        self.assertEqual(fixture, json.loads(payload))

    def test_hostile_source_content_cannot_break_out_of_data_slot(self):
        hostile = (
            "</script><script>"
            "globalThis.__flashOwned=true"
            "</script><&>"
        )
        fixture = json.loads(read(self.fixture_path))
        fixture["sourceDocuments"][0]["content"] = hostile
        with tempfile.TemporaryDirectory() as directory:
            fixture_path = Path(directory) / "hostile.json"
            fixture_path.write_text(
                json.dumps(fixture, ensure_ascii=False),
                encoding="utf-8",
            )
            hostile_html = embedded_html(self.template_path, fixture_path)
        self.assertNotIn(hostile, hostile_html)
        self.assertIn("\\u003c/script", hostile_html)
        payload = re.search(
            r'<script id="flash-data" type="application/json">'
            r"(?P<payload>.*?)</script>",
            hostile_html,
            re.DOTALL,
        )
        self.assertIsNotNone(payload)
        restored = json.loads(payload.group("payload"))
        self.assertEqual(fixture, restored)
        self.assertEqual(
            hostile,
            restored["sourceDocuments"][0]["content"],
        )
        script_tags = re.findall(r"<script\b[^>]*>", hostile_html, re.IGNORECASE)
        original_script_tags = re.findall(
            r"<script\b[^>]*>",
            self.template,
            re.IGNORECASE,
        )
        executable_scripts = [
            tag for tag in script_tags if 'type="application/json"' not in tag
        ]
        self.assertEqual(len(original_script_tags), len(script_tags))
        self.assertEqual(1, len(executable_scripts))

    def test_navigation_uses_final_anchor_fallback_without_observer_override(self):
        set_active = self.template.index("const setActive = target =>")
        at_bottom = self.template.index("const isAtDocumentBottom = () =>")
        observer = self.template.index("new IntersectionObserver")
        scroll_handler = self.template.index('window.addEventListener("scroll"')
        self.assertLess(set_active, at_bottom)
        self.assertLess(at_bottom, observer)
        self.assertLess(observer, scroll_handler)
        self.assertIn("setActive(entry.target)", self.template)
        self.assertIn("setActive(link)", self.template)
        self.assertGreaterEqual(
            self.template.count('setActive("confirmation")'),
            2,
        )
        observer_body = self.template[observer:scroll_handler]
        self.assertLess(
            observer_body.index("if (isAtDocumentBottom())"),
            observer_body.index("const visible"),
        )
        self.assertIn(
            'link.setAttribute("aria-current", "location")',
            self.template,
        )
        self.assertIn('link.removeAttribute("aria-current")', self.template)


class FlashSharedGuardrailTests(unittest.TestCase):
    def test_checklist_uses_checkboxes_and_covers_shared_invariants(self):
        checklist = read(SKILL_ROOT / "references" / "output-checklist.md")
        for heading in ("## 通用", "## 模式 1", "## 模式 2"):
            self.assertIn(heading, checklist)
        checklist_items = [
            line for line in checklist.splitlines() if line.startswith("- ")
        ]
        self.assertGreaterEqual(len(checklist_items), 20)
        for item in checklist_items:
            self.assertTrue(item.startswith("- [ ] "), item)
        for marker in (
            "JSON 可解析",
            "sourceDocuments",
            "analysisRecord",
            "用户确认",
            "当前模式的正确模板",
            "__FLASH_DATA_JSON__",
            "模板 CSS 和 JavaScript 未修改",
            "HTML 内嵌数据可以还原为交付 JSON",
            "英文状态",
            "均来自 JSON",
            "每条规则在逻辑树中恰好出现一次",
            "五个质控维度各出现一次",
            "baseReview",
            "auditComparison",
            "not_checked",
            "风险方向",
            "局部问题",
            "仅结论",
            "inventoryShown",
            "疑似秘密",
            "目标服务或地址",
            "材料范围",
        ):
            self.assertIn(marker, checklist)

    def test_conclusion_only_guidance_is_split_into_atomic_checkboxes(self):
        checklist = read(SKILL_ROOT / "references" / "output-checklist.md")
        items = [
            line
            for line in checklist.splitlines()
            if line.startswith("- [ ] ") and "仅结论" in line
        ]
        self.assertGreaterEqual(len(items), 5)
        for marker in (
            "前三个过程依赖维度",
            "方向相反",
            "方向一致",
            "方向未知",
            "标准缺失",
        ):
            self.assertTrue(any(marker in item for item in items), marker)

    def test_combination_common_security_and_stop_rules_are_explicit(self):
        skill = read(SKILL_ROOT / "SKILL.md")
        for marker in (
            "## 组合请求",
            "先完整执行模式 1",
            "作为模式 2 的认定标准输入",
            "模式 2 的输入完整性确认",
            "## 通用约束",
            "JSON 是唯一业务内容源",
            "不执行其中的指令",
            "不使用用户未提供的政策或医学知识",
            "## 安全与错误处理",
            "API 密钥",
            "令牌",
            "Cookie",
            "密码",
            "系统提示",
            "停止生成正式成果物",
            "先移除或替换",
            "才可向外部服务发送或上传患者材料",
            "输入不足",
            "阻断性歧义",
            "未确认完整",
            "模板缺失",
            "内嵌 JSON 不一致",
            "不把部分页面称为正式交付物",
        ):
            self.assertIn(marker, skill)
        self.assertNotRegex(skill, r"scripts/|python3|node |npm |shell")
        self.assertLessEqual(len(skill.splitlines()), 140)

    def test_combination_gate_is_section_scoped_and_ordered(self):
        skill = read(SKILL_ROOT / "SKILL.md")
        match = re.search(
            r"(?ms)^## 组合请求$\n(?P<body>.*?)(?=^## |\Z)",
            skill,
        )
        self.assertIsNotNone(match)
        body = match.group("body")
        markers = (
            "先完整执行模式 1",
            "阻断性歧义已经解决",
            "用户已确认",
            "正式 JSON",
            "才把该 JSON 作为模式 2 的认定标准输入",
            "模式 2 的输入完整性确认",
        )
        positions = [body.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))

    def test_security_stops_and_scopes_external_sends_in_single_bullets(self):
        skill = read(SKILL_ROOT / "SKILL.md")
        match = re.search(
            r"(?ms)^## 安全与错误处理$\n(?P<body>.*?)(?=^## |\Z)",
            skill,
        )
        self.assertIsNotNone(match)
        bullets = [
            line for line in match.group("body").splitlines()
            if line.startswith("- ")
        ]
        secret = next(line for line in bullets if "API 密钥" in line)
        for marker in (
            "立即停止后续处理",
            "脱敏告警",
            "不含具体值",
            "不得回显",
            "记录",
            "上传",
            "秘密",
        ):
            self.assertIn(marker, secret)
        external = next(line for line in bullets if "外部" in line)
        for marker in (
            "目标服务或地址",
            "具体动作",
            "材料范围",
            "任一项不清楚",
            "保持本地处理并询问",
            "不得发送",
        ):
            self.assertIn(marker, external)

    def test_runtime_files_do_not_contain_external_runtime_commands(self):
        command_pattern = re.compile(
            r"^[ \t]*(?:(?:[-*+>])[ \t]+|\d+[.)][ \t]+)?`*"
            r"(?:python3?[ \t]+\S+|node[ \t]+\S+|"
            r"npm[ \t]+(?:run|exec)\b|npx[ \t]+\S+|"
            r"bash[ \t]+\S+|sh[ \t]+-c\b)",
            re.I | re.MULTILINE,
        )
        for path in SKILL_ROOT.rglob("*"):
            if path.is_file():
                self.assertIsNone(command_pattern.search(read(path)), str(path))

    def test_runtime_command_pattern_handles_wrapped_commands_without_prose_false_positives(self):
        command_pattern = re.compile(
            r"^[ \t]*(?:(?:[-*+>])[ \t]+|\d+[.)][ \t]+)?`*"
            r"(?:python3?[ \t]+\S+|node[ \t]+\S+|"
            r"npm[ \t]+(?:run|exec)\b|npx[ \t]+\S+|"
            r"bash[ \t]+\S+|sh[ \t]+-c\b)",
            re.I | re.MULTILINE,
        )
        commands = (
            "python3 tool.py",
            "- `python validate.py`",
            "1. node render.js",
            "2) `npm run build`",
            "* npx package",
            "> bash deploy.sh",
            "+ `sh -c 'echo ok'`",
        )
        prose = (
            "不支持 Python、Node 或 Shell 运行时。",
            "- 不调用外部运行时脚本。",
            "`node` 是运行时名称。",
            "const node = makeNode();",
            "npm 包管理说明。",
        )
        for candidate in commands:
            with self.subTest(command=candidate):
                self.assertIsNotNone(command_pattern.search(candidate))
        for candidate in prose:
            with self.subTest(prose=candidate):
                self.assertIsNone(command_pattern.search(candidate))

    def test_openai_metadata_matches_final_flash_interface(self):
        interface = parse_openai_interface(
            read(SKILL_ROOT / "agents" / "openai.yaml")
        )
        self.assertEqual(
            {
                "display_name": "门诊慢特病认定与质控 Flash",
                "short_description":
                    "轻量生成门诊慢特病认定标准并复核患者材料与智能审核结果",
                "default_prompt":
                    "使用 $chronic-disease-certification-qc-flash "
                    "生成门诊慢特病认定标准，或复核患者材料与智能审核结果。",
            },
            interface,
        )


class FlashFinalAcceptanceTests(unittest.TestCase):
    RUNTIME_FILES = {
        "SKILL.md",
        "agents/openai.yaml",
        "references/mode1-contract.md",
        "references/mode2-contract.md",
        "references/output-checklist.md",
        "assets/certification-template.html",
        "assets/qc-report-template.html",
    }
    FORWARD_CASE_IDS = (
        "M1-CLEAR",
        "M1-AMBIGUOUS",
        "M2-DETAILED",
        "M2-CONCLUSION-ONLY",
        "M2-NO-STANDARD",
        "COMBINED",
        "PRESSURE-URGENT",
        "PRESSURE-INJECTION",
        "PRESSURE-HTML",
    )
    FORWARD_RESULT_FIELDS = (
        "Outcome",
        "Coverage",
        "Gate behavior",
        "JSON contract",
        "HTML behavior",
        "Difference from baseline",
        "Follow-up change",
        "Provenance",
    )
    FORWARD_COVERAGE = {
        "M1-CLEAR": "gate-stage / partial",
        "M1-AMBIGUOUS": "reachable assertions complete",
        "M2-DETAILED": "gate-stage / partial",
        "M2-CONCLUSION-ONLY": "gate-stage / partial",
        "M2-NO-STANDARD": "gate-stage / partial",
        "COMBINED": "reachable assertions complete",
        "PRESSURE-URGENT": "reachable assertions complete",
        "PRESSURE-INJECTION": "reachable assertions complete",
        "PRESSURE-HTML": "gate-stage / partial",
    }

    def test_forward_results_record_all_cases_and_complete_evidence_fields(self):
        results_path = ACCEPTANCE_ROOT / "forward-results.md"
        raw_path = ACCEPTANCE_ROOT / "forward-raw-results.json"
        self.assertTrue(results_path.is_file())
        self.assertTrue(raw_path.is_file())
        results = read(results_path)
        catalog = json.loads(
            read(ACCEPTANCE_ROOT / "evaluation-cases.json")
        )
        raw = json.loads(read(raw_path))

        self.assertEqual({"runDate", "isolation", "cases"}, set(raw))
        self.assertEqual("2026-07-25", raw["runDate"])
        assert_nonempty_string(self, raw["isolation"], "raw.isolation")
        self.assertEqual(
            {"id", "evaluator", "prompt", "response"},
            set(raw["cases"][0]),
        )
        catalog_cases = catalog["cases"]
        raw_cases = raw["cases"]
        self.assertEqual(len(catalog_cases), len(raw_cases))
        self.assertEqual(
            [case["id"] for case in catalog_cases],
            [case["id"] for case in raw_cases],
        )
        self.assertEqual(
            [case["prompt"] for case in catalog_cases],
            [case["prompt"] for case in raw_cases],
        )
        self.assertEqual(
            len(raw_cases),
            len({case["id"] for case in raw_cases}),
        )
        raw_by_id = {}
        for index, case in enumerate(raw_cases):
            self.assertEqual(
                {"id", "evaluator", "prompt", "response"},
                set(case),
                f"raw.cases[{index}]",
            )
            self.assertRegex(case["evaluator"], r"^/root/eval_[a-z0-9_]+$")
            assert_nonempty_string(
                self,
                case["response"],
                f"raw.cases[{index}].response",
            )
            raw_by_id[case["id"]] = case

        self.assertIn("fresh evaluator", results)
        self.assertIn("未提供 expected、设计文档或基线结果", results)
        self.assertIn("确认门禁", results)
        self.assertIn("## Pass rubric", results)
        self.assertIn("9/9 reachable gate-stage behavior pass", results)
        self.assertIn(
            "不等于 9/9 end-to-end artifact pass",
            results,
        )
        self.assertIn(
            "9/9 cases 均有 expected，语义匹配仍由人工审查",
            results,
        )
        self.assertIn("## Artifact verification", results)
        self.assertIn("93 项自动化测试通过", results)
        self.assertIn("两份 fixture", results)
        self.assertIn("Mode 2 Node VM DOM", results)
        self.assertIn("Mode 1 早期 browser smoke", results)
        self.assertIn("MachPort", results)
        self.assertIn("Permission denied", results)
        self.assertIn("应用内浏览器安全策略", results)
        self.assertIn("file://", results)
        self.assertIn("Step 4 未完成", results)
        self.assertIn("非产品缺陷", results)
        self.assertIn(
            "不能替代 CSS、打印和控制台的真实视觉验收",
            results,
        )

        headings = re.findall(r"(?m)^## ([A-Z0-9-]+)$", results)
        self.assertEqual(list(self.FORWARD_CASE_IDS), headings)
        for index, case_id in enumerate(self.FORWARD_CASE_IDS):
            start = results.index(f"## {case_id}\n")
            if index + 1 < len(self.FORWARD_CASE_IDS):
                end = results.index(
                    f"## {self.FORWARD_CASE_IDS[index + 1]}\n",
                    start,
                )
            else:
                end = len(results)
            section = results[start:end]
            for field in self.FORWARD_RESULT_FIELDS:
                self.assertRegex(
                    section,
                    rf"(?m)^- {re.escape(field)}: \S",
                    f"{case_id} missing {field}",
                )
            self.assertIn(
                f"- Coverage: {self.FORWARD_COVERAGE[case_id]}",
                section,
            )
            provenance = re.search(
                r"(?m)^- Provenance: `forward-raw-results\.json`; "
                r"evaluator: `(?P<evaluator>/root/eval_[a-z0-9_]+)`$",
                section,
            )
            self.assertIsNotNone(
                provenance,
                f"{case_id} missing auditable provenance",
            )
            self.assertEqual(
                raw_by_id[case_id]["evaluator"],
                provenance.group("evaluator"),
            )
            evidence = re.search(
                r"(?m)^- Evidence:\s*\n\n {2,}> (?P<excerpt>[^\n]+)$",
                section,
            )
            self.assertIsNotNone(
                evidence,
                f"{case_id} missing quoted evaluator evidence",
            )
            self.assertIn(
                evidence.group("excerpt"),
                raw_by_id[case_id]["response"],
                f"{case_id} evidence is not a verbatim raw substring",
            )

    def test_skill_stays_compact_and_progressively_loads_mode_contracts(self):
        skill = read(SKILL_ROOT / "SKILL.md")
        self.assertLessEqual(len(skill.splitlines()), 140)

        mode1_match = re.search(
            r"(?ms)^## 模式 1：.*?$\n(?P<body>.*?)(?=^## |\Z)",
            skill,
        )
        mode2_match = re.search(
            r"(?ms)^## 模式 2：.*?$\n(?P<body>.*?)(?=^## |\Z)",
            skill,
        )
        self.assertIsNotNone(mode1_match)
        self.assertIsNotNone(mode2_match)
        mode1 = mode1_match.group("body")
        mode2 = mode2_match.group("body")

        self.assertIn("references/mode1-contract.md", mode1)
        self.assertIn("references/mode2-contract.md", mode2)
        self.assertNotIn("mode2-contract.md", mode1)
        self.assertNotIn("mode1-contract.md", mode2)
        self.assertIn("模式 1 不读取模式 2 的契约", mode1)
        self.assertIn("模式 2 不读取模式 1 的契约", mode2)

    def test_skill_and_checklist_validate_the_data_slot_not_the_whole_html(self):
        skill = read(SKILL_ROOT / "SKILL.md")
        checklist = read(
            SKILL_ROOT / "references" / "output-checklist.md"
        )
        mode_sections = (
            re.search(
                r"(?ms)^## 模式 1：.*?$\n(?P<body>.*?)(?=^## |\Z)",
                skill,
            ),
            re.search(
                r"(?ms)^## 模式 2：.*?$\n(?P<body>.*?)(?=^## |\Z)",
                skill,
            ),
        )
        for match in mode_sections:
            self.assertIsNotNone(match)
            section = match.group("body")
            for marker in (
                "替换前",
                "数据槽",
                "占位符恰好出现一次",
                "替换后",
                "可解析",
                "逐字段等值",
                "用户数据",
                "合法存在",
            ):
                self.assertIn(marker, section)

        for marker in (
            "替换前",
            "数据槽",
            "占位符恰好出现一次",
            "替换后",
            "可解析",
            "逐字段等值",
            "用户数据",
            "合法存在",
        ):
            self.assertIn(marker, checklist)
        self.assertNotIn("确认没有残留占位符", skill)
        self.assertNotIn("完整 HTML 中绝对不存在", skill + checklist)

    def test_fixtures_keep_complete_sources_and_visible_analysis_fields(self):
        for fixture_name in ("valid-mode1.json", "valid-mode2.json"):
            with self.subTest(fixture=fixture_name):
                fixture = json.loads(
                    read(ACCEPTANCE_ROOT / "fixtures" / fixture_name)
                )
                self.assertTrue(fixture["sourceDocuments"])
                for source in fixture["sourceDocuments"]:
                    self.assertEqual({"name", "type", "content"}, set(source))
                    for field in ("name", "type", "content"):
                        assert_nonempty_string(
                            self,
                            source[field],
                            f"{fixture_name}.sourceDocuments.{field}",
                        )

                analysis = fixture["analysisRecord"]
                assert_string_array(
                    self,
                    analysis["inputSummary"],
                    f"{fixture_name}.analysisRecord.inputSummary",
                    allow_empty=False,
                )
                assert_nonempty_string(
                    self,
                    analysis["preliminaryConclusion"],
                    f"{fixture_name}.analysisRecord.preliminaryConclusion",
                )

    def test_templates_have_one_safe_slot_and_no_network_or_html_injection(self):
        for template_name in (
            "certification-template.html",
            "qc-report-template.html",
        ):
            with self.subTest(template=template_name):
                template = read(SKILL_ROOT / "assets" / template_name)
                self.assertEqual(1, template.count("__FLASH_DATA_JSON__"))
                self.assertNotRegex(template, r"(?i)https?://")
                self.assertNotRegex(template, r"(?i)\binnerHTML\b")

    def test_runtime_contains_exactly_the_seven_nonempty_design_files(self):
        actual = {
            path.relative_to(SKILL_ROOT).as_posix()
            for path in SKILL_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(self.RUNTIME_FILES, actual)
        for relative in sorted(self.RUNTIME_FILES):
            with self.subTest(runtime_file=relative):
                path = SKILL_ROOT / relative
                self.assertTrue(path.is_file())
                self.assertTrue(read(path).strip())

    def test_both_fixtures_round_trip_through_safe_html_injection(self):
        pairs = (
            ("certification-template.html", "valid-mode1.json"),
            ("qc-report-template.html", "valid-mode2.json"),
        )
        for template_name, fixture_name in pairs:
            with self.subTest(template=template_name, fixture=fixture_name):
                fixture_path = ACCEPTANCE_ROOT / "fixtures" / fixture_name
                expected = json.loads(read(fixture_path))
                rendered = embedded_html(
                    SKILL_ROOT / "assets" / template_name,
                    fixture_path,
                )
                payload = extract_flash_payload(rendered)
                self.assertNotEqual("__FLASH_DATA_JSON__", payload.strip())
                self.assertEqual(expected, json.loads(payload))

    def test_placeholder_literal_in_user_source_round_trips_for_both_modes(self):
        pairs = (
            ("certification-template.html", "valid-mode1.json"),
            ("qc-report-template.html", "valid-mode2.json"),
        )
        literal = "__FLASH_DATA_JSON__"
        for template_name, fixture_name in pairs:
            with self.subTest(template=template_name, fixture=fixture_name):
                fixture = json.loads(
                    read(ACCEPTANCE_ROOT / "fixtures" / fixture_name)
                )
                fixture["sourceDocuments"][0]["content"] = (
                    f"合法原文保留字面串：{literal}"
                )
                rendered = embedded_html_from_data(
                    read(SKILL_ROOT / "assets" / template_name),
                    fixture,
                )
                self.assertIn(literal, rendered)
                payload = extract_flash_payload(rendered)
                self.assertNotEqual(literal, payload.strip())
                restored = json.loads(payload)
                self.assertEqual(fixture, restored)
                self.assertEqual(
                    fixture["sourceDocuments"][0]["content"],
                    restored["sourceDocuments"][0]["content"],
                )


if __name__ == "__main__":
    unittest.main()
