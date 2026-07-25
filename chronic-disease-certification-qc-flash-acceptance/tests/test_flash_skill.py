import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "chronic-disease-certification-qc-flash"


def read(path):
    return path.read_text(encoding="utf-8")


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


if __name__ == "__main__":
    unittest.main()
