# 认定标准版本比对与影响分析 Flash Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Flash Skill that compares two or more confirmed standards, explains traceable rule changes, and optionally compares the same patient material against each version without treating the result as a final eligibility decision.

**Architecture:** A `flash-1.0/standard_version_impact` contract maintains independent version namespaces and records whether order came from source text, user confirmation, or is unknown. One fixed offline template renders standard changes and optional version assessments from embedded JSON only.

**Tech Stack:** Markdown, static HTML/CSS/vanilla JavaScript, JSON, Python `unittest`.

---

## File structure

- Create: `chronic-disease-standard-version-impact-flash/SKILL.md`
- Create: `chronic-disease-standard-version-impact-flash/agents/openai.yaml`
- Create: `chronic-disease-standard-version-impact-flash/references/version-impact-contract.md`
- Create: `chronic-disease-standard-version-impact-flash/references/output-checklist.md`
- Create: `chronic-disease-standard-version-impact-flash/assets/version-impact-template.html`
- Create: `chronic-disease-standard-version-impact-flash-acceptance/fixtures/valid-version-impact.json`
- Create: `chronic-disease-standard-version-impact-flash-acceptance/tests/test_version_impact_skill.py`

### Task 1: Establish failing boundary and contract tests

**Files:**
- Create: `chronic-disease-standard-version-impact-flash-acceptance/tests/test_version_impact_skill.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "chronic-disease-standard-version-impact-flash"

class VersionImpactSkillTests(unittest.TestCase):
    def read_skill_file(self, relative_path):
        path = SKILL_ROOT / relative_path
        if not path.is_file():
            self.fail(f"missing required Skill file: {path}")
        return path.read_text(encoding="utf-8")

    def test_skill_requires_confirmed_versions_and_order_basis(self):
        skill = self.read_skill_file("SKILL.md")
        self.assertIn("确认比较顺序", skill)
        self.assertIn("不得单独当作政策生效日期", skill)
        self.assertIn("不评价原审核结果", skill)

    def test_contract_uses_version_scoped_rule_ids(self):
        contract = self.read_skill_file("references/version-impact-contract.md")
        self.assertIn("S1:R001", contract)
        self.assertIn("standard_version_impact", contract)
        self.assertIn("排序依据", contract)
```

- [ ] **Step 2: Verify red**

Run `python3 -m unittest discover -s chronic-disease-standard-version-impact-flash-acceptance/tests -p 'test_version_impact_skill.py' -v`.

Expected: explicit missing-file assertion failures.

- [ ] **Step 3: Implement the minimum Skill and contract**

Define two-or-more standard inputs, order basis, version-scoped rule IDs, condition groups, change categories, optional material documents, optional version assessments, assessment delta, and dual confirmation. Prohibit original-audit inputs, QC risk fields, and final eligibility language.

- [ ] **Step 4: Verify partial green and commit**

Run the Task 1 command; commit with `feat: define version impact flash contract`.

### Task 2: Lock a fixture and template through red-green tests

**Files:**
- Create: `chronic-disease-standard-version-impact-flash-acceptance/fixtures/valid-version-impact.json`
- Create: `chronic-disease-standard-version-impact-flash/assets/version-impact-template.html`
- Modify: `chronic-disease-standard-version-impact-flash-acceptance/tests/test_version_impact_skill.py`

- [ ] **Step 1: Add failing fixture and template tests**

```python
import json
FIXTURE = ROOT / "chronic-disease-standard-version-impact-flash-acceptance/fixtures/valid-version-impact.json"

    def test_fixture_keeps_versions_and_assessments_separate(self):
        if not FIXTURE.is_file(): self.fail(f"missing required fixture: {FIXTURE}")
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(data["mode"], "standard_version_impact")
        self.assertEqual(len(data["standardInputs"]), 2)
        self.assertEqual(data["changes"][0]["type"], "条件修改")
        self.assertTrue(data["versionAssessments"])
        self.assertIn("S1:R001", data["versionAssessments"][0]["ruleJudgments"][0]["ruleId"])

    def test_template_has_comparison_sections_and_one_data_slot(self):
        template = self.read_skill_file("assets/version-impact-template.html")
        self.assertEqual(template.count("__FLASH_DATA_JSON__"), 1)
        self.assertIn("版本与排序依据", template)
        self.assertIn("标准差异", template)
        self.assertIn("各版本规则证据判读", template)
        self.assertNotIn("五维检查", template)
```

- [ ] **Step 2: Verify red, then implement fixture and template**

The fixture must use two versions with source-confirmed order, one condition modification, and optional material assessments with independent `S1:` and `S2:` rule IDs. The template must validate `flash-1.0/standard_version_impact`, use `textContent`, and render ordering, condition groups, changes, optional assessments, deltas, sources and confirmation.

- [ ] **Step 3: Verify green, JSON round trip, and commit**

Run the Task 1 command, inject escaped fixture JSON into `#flash-data` and assert round-trip equality, then commit with `feat: add version impact flash`.
