import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "chronic-disease-certification-qc-flash"
ACCEPTANCE_ROOT = REPO_ROOT / "chronic-disease-certification-qc-flash-acceptance"


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

        ui = read(SKILL_ROOT / "agents" / "openai.yaml")
        self.assertIn('display_name: "门诊慢特病认定与质控 Flash"', ui)
        self.assertIn("$chronic-disease-certification-qc-flash", ui)

    def test_no_placeholder_markers_in_runtime_docs(self):
        forbidden = ("TO" + "DO", "T" + "BD")
        runtime_files = (
            path for path in SKILL_ROOT.rglob("*") if path.is_file()
        )

        for path in runtime_files:
            content = read(path)
            for marker in forbidden:
                self.assertNotIn(marker, content, path.relative_to(REPO_ROOT))


if __name__ == "__main__":
    unittest.main()
