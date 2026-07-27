# 材料证据编目与归位 Flash Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Flash skill that objectively catalogs and relates patient materials, producing validated JSON and an offline HTML report without any eligibility or audit judgment.

**Architecture:** The skill package owns the operating instructions, strict output contract, checklist and an immutable-at-runtime HTML template. A companion acceptance package uses `unittest` and one canonical fixture to check the safety boundary, contract, and HTML data-slot convention without requiring a JavaScript runtime.

**Tech Stack:** Markdown Skill instructions and contracts, static HTML/CSS/vanilla JavaScript, JSON fixture, Python standard-library `unittest`.

---

## File structure

- Create: `chronic-disease-material-catalog-flash/SKILL.md` — execution flow, confirmation gate, safety and objective-only boundary.
- Create: `chronic-disease-material-catalog-flash/agents/openai.yaml` — Skill display metadata.
- Create: `chronic-disease-material-catalog-flash/references/catalog-contract.md` — exact `flash-1.0/material_catalog` schema and field constraints.
- Create: `chronic-disease-material-catalog-flash/references/output-checklist.md` — generation, JSON and HTML equality checks.
- Create: `chronic-disease-material-catalog-flash/assets/material-catalog-template.html` — self-contained report renderer with a single `flash-data` placeholder.
- Create: `chronic-disease-material-catalog-flash-acceptance/fixtures/valid-material-catalog.json` — canonical valid output with dated, undated and related materials.
- Create: `chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py` — acceptance tests for the public Skill surface, contract vocabulary, fixture and template data slot.

### Task 1: Establish failing acceptance tests

**Files:**
- Create: `chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "chronic-disease-material-catalog-flash"


class MaterialCatalogSkillTests(unittest.TestCase):
    def test_skill_defines_objective_cataloging_boundary(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("不读取认定标准", skill)
        self.assertIn("不输出通过或不通过结论", skill)
        self.assertIn("明确确认材料完整", skill)

    def test_contract_defines_catalog_mode_and_required_sections(self):
        contract = (SKILL_ROOT / "references/catalog-contract.md").read_text(encoding="utf-8")
        for expected in ("material_catalog", "sourceDocuments", "catalog", "timelines", "relationships", "confirmation"):
            self.assertIn(expected, contract)

    def test_template_has_exactly_one_data_slot(self):
        template = (SKILL_ROOT / "assets/material-catalog-template.html").read_text(encoding="utf-8")
        self.assertEqual(template.count("__FLASH_DATA_JSON__"), 1)
        self.assertIn('id="flash-data"', template)
        self.assertIn("JSON.parse", template)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py -v`

Expected: FAIL because the new Skill files do not exist.

- [ ] **Step 3: Commit the failing test**

```bash
git add chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py
git commit -m "test: define material catalog flash acceptance"
```

### Task 2: Define the standalone skill and output contract

**Files:**
- Create: `chronic-disease-material-catalog-flash/SKILL.md`
- Create: `chronic-disease-material-catalog-flash/agents/openai.yaml`
- Create: `chronic-disease-material-catalog-flash/references/catalog-contract.md`
- Create: `chronic-disease-material-catalog-flash/references/output-checklist.md`

- [ ] **Step 1: Write the failing contract assertion**

Extend `test_material_catalog_skill.py` with:

```python
    def test_contract_forbids_audit_and_eligibility_outputs(self):
        contract = (SKILL_ROOT / "references/catalog-contract.md").read_text(encoding="utf-8")
        self.assertIn("不得包含规则判断、资格结论、审核结论、风险、问题或建议字段", contract)
        self.assertIn("疑似重复只能使用待核对", contract)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py -v`

Expected: FAIL because the contract is absent or lacks the boundary statement.

- [ ] **Step 3: Add the minimal package content**

Implement these exact responsibilities:

```text
SKILL.md: inventory -> explicit completeness confirmation -> objective cataloging -> JSON self-check -> HTML generation.
catalog-contract.md: exact root keys, exact nested keys, source/canonical-field constraints, and the no-judgment prohibition.
output-checklist.md: one-source-per-document, fact traceability, timeline ordering, relationship safety, single placeholder and JSON/HTML equality checks.
openai.yaml: display name, short description and default prompt.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py -v`

Expected: existing acceptance assertions PASS; the template assertion remains failing until Task 3.

- [ ] **Step 5: Commit the package contract**

```bash
git add chronic-disease-material-catalog-flash
git commit -m "feat: define material catalog flash contract"
```

### Task 3: Add canonical fixture and fixture validation tests

**Files:**
- Create: `chronic-disease-material-catalog-flash-acceptance/fixtures/valid-material-catalog.json`
- Modify: `chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py`

- [ ] **Step 1: Write the failing fixture test**

```python
import json

FIXTURE = ROOT / "chronic-disease-material-catalog-flash-acceptance/fixtures/valid-material-catalog.json"

    def test_fixture_is_objective_and_traceable(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(data["schemaVersion"], "flash-1.0")
        self.assertEqual(data["mode"], "material_catalog")
        self.assertEqual(len(data["sourceDocuments"]), len(data["catalog"]))
        self.assertEqual(data["confirmation"]["confirmed"], True)
        self.assertEqual(data["relationships"][0]["status"], "待核对")
        self.assertIn("不构成资格", data["analysisRecord"]["preliminaryConclusion"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py -v`

Expected: FAIL because the fixture is missing.

- [ ] **Step 3: Add a minimal valid fixture**

Create JSON containing exactly two `patient_material` source documents: one dated outpatient record and one undated duplicate-like copy. Include one dated timeline item, one pending timeline item, and one `疑似重复` relationship with `status` equal to `待核对` and a source-based `basis`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py -v`

Expected: fixture assertions PASS; the template assertion remains failing until Task 4.

- [ ] **Step 5: Commit fixture coverage**

```bash
git add chronic-disease-material-catalog-flash-acceptance
git commit -m "test: cover material catalog fixture"
```

### Task 4: Build the offline report template and complete verification

**Files:**
- Create: `chronic-disease-material-catalog-flash/assets/material-catalog-template.html`
- Modify: `chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py`

- [ ] **Step 1: Write the failing HTML-section test**

```python
    def test_template_renders_catalog_specific_sections(self):
        template = (SKILL_ROOT / "assets/material-catalog-template.html").read_text(encoding="utf-8")
        for expected in ("材料目录", "时间线", "材料关联线索", "待核对项", "原始材料", "确认记录"):
            self.assertIn(expected, template)
        self.assertNotIn("五维检查", template)
        self.assertNotIn("审核质控报告", template)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py -v`

Expected: FAIL because the template is missing.

- [ ] **Step 3: Implement the fixed template**

Create a self-contained HTML file that:

```text
reads only #flash-data;
parses flash-1.0/material_catalog data;
renders overview, inventory, grouped catalog, confirmed/pending timeline, relationships, pending checks, analysis record, sources and confirmation;
uses textContent for user data;
renders only Chinese display labels;
contains __FLASH_DATA_JSON__ exactly once;
does not provide any rule judgment or audit-quality panel.
```

- [ ] **Step 4: Run focused verification**

Run: `python3 -m unittest chronic-disease-material-catalog-flash-acceptance/tests/test_material_catalog_skill.py -v`

Expected: all acceptance tests PASS.

- [ ] **Step 5: Run regression verification and inspect the artifact**

Run: `python3 -m unittest discover -v`

Expected: all discovered tests PASS. Then replace the template placeholder in a temporary copy with escaped fixture JSON, open it in a browser-capable validator if available, and confirm the document displays the expected seven sections.

- [ ] **Step 6: Commit the complete Skill**

```bash
git add chronic-disease-material-catalog-flash chronic-disease-material-catalog-flash-acceptance
git commit -m "feat: add material evidence catalog flash"
```
