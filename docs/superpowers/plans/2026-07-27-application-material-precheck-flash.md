# 申请材料预检与补件清单 Flash Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a standalone Flash Skill that turns a confirmed standard and confirmed patient materials into traceable evidence-precheck and supplement-list JSON plus offline HTML, without issuing a formal eligibility decision.

**Architecture:** The Skill owns a `flash-1.0/material_precheck` contract, a fixed HTML renderer, and a canonical fixture covering all four precheck states. Python standard-library acceptance tests validate the package surface and forbid audit-quality or final-decision semantics.

**Tech Stack:** Markdown, static HTML/CSS/vanilla JavaScript, JSON, Python `unittest`.

---

## File structure

- Create: `chronic-disease-material-precheck-flash/SKILL.md`
- Create: `chronic-disease-material-precheck-flash/agents/openai.yaml`
- Create: `chronic-disease-material-precheck-flash/references/precheck-contract.md`
- Create: `chronic-disease-material-precheck-flash/references/output-checklist.md`
- Create: `chronic-disease-material-precheck-flash/assets/material-precheck-template.html`
- Create: `chronic-disease-material-precheck-flash-acceptance/fixtures/valid-material-precheck.json`
- Create: `chronic-disease-material-precheck-flash-acceptance/tests/test_material_precheck_skill.py`

### Task 1: Write acceptance tests before the package

**Files:**
- Create: `chronic-disease-material-precheck-flash-acceptance/tests/test_material_precheck_skill.py`

- [ ] **Step 1: Write the failing package tests**

```python
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "chronic-disease-material-precheck-flash"

class MaterialPrecheckSkillTests(unittest.TestCase):
    def read_skill_file(self, relative_path):
        path = SKILL_ROOT / relative_path
        if not path.is_file():
            self.fail(f"missing required Skill file: {path}")
        return path.read_text(encoding="utf-8")

    def test_skill_requires_standard_and_material_confirmation(self):
        skill = self.read_skill_file("SKILL.md")
        self.assertIn("明确确认采用的标准", skill)
        self.assertIn("明确确认材料完整", skill)
        self.assertIn("不输出通过或不通过结论", skill)

    def test_contract_defines_four_precheck_states(self):
        contract = self.read_skill_file("references/precheck-contract.md")
        for state in ("已定位证据", "信息不足", "未定位证据", "材料形式待确认"):
            self.assertIn(state, contract)
        self.assertIn("不得包含原审核结果、风险或正式资格结论", contract)
```

- [ ] **Step 2: Verify red**

Run `python3 -m unittest discover -s chronic-disease-material-precheck-flash-acceptance/tests -p 'test_material_precheck_skill.py' -v`.

Expected: explicit missing-file assertion failures.

- [ ] **Step 3: Commit the failing test**

Commit message: `test: define material precheck flash acceptance`.

### Task 2: Implement the Skill contract

**Files:**
- Create: `chronic-disease-material-precheck-flash/SKILL.md`
- Create: `chronic-disease-material-precheck-flash/agents/openai.yaml`
- Create: `chronic-disease-material-precheck-flash/references/precheck-contract.md`
- Create: `chronic-disease-material-precheck-flash/references/output-checklist.md`
- Modify: `chronic-disease-material-precheck-flash-acceptance/tests/test_material_precheck_skill.py`

- [ ] **Step 1: Add the next failing assertion**

```python
    def test_contract_requires_traceable_supplement_items(self):
        contract = self.read_skill_file("references/precheck-contract.md")
        self.assertIn("supplementList", contract)
        self.assertIn("只能收录信息不足、未定位证据或材料形式待确认", contract)
        self.assertIn("不能凭空指定诊断证明、检查单或其他特定文件", contract)
```

- [ ] **Step 2: Verify red**

Run the Task 1 command. Expected: contract-file assertion failure.

- [ ] **Step 3: Implement the minimum contract**

`SKILL.md` must enforce: standard-adoption confirmation, then material-completeness confirmation, then one evidence precheck per standard extraction item. `precheck-contract.md` must define exact root fields, standard profile, standard/patient source documents, four-state precheck items, supplement subset, and dual confirmations. `output-checklist.md` must require source traceability, no-decision language, one placeholder and JSON/HTML equality. `openai.yaml` must provide the display metadata.

- [ ] **Step 4: Verify partial green**

Run the Task 1 command. Expected: all current Skill/contract assertions pass.

- [ ] **Step 5: Commit the contract**

Commit message: `feat: define material precheck flash contract`.

### Task 3: Add fixture, report template, and final verification

**Files:**
- Create: `chronic-disease-material-precheck-flash-acceptance/fixtures/valid-material-precheck.json`
- Create: `chronic-disease-material-precheck-flash/assets/material-precheck-template.html`
- Modify: `chronic-disease-material-precheck-flash-acceptance/tests/test_material_precheck_skill.py`

- [ ] **Step 1: Add failing fixture and template tests**

```python
import json
FIXTURE = ROOT / "chronic-disease-material-precheck-flash-acceptance/fixtures/valid-material-precheck.json"

    def test_fixture_covers_every_precheck_state_without_final_decision(self):
        if not FIXTURE.is_file():
            self.fail(f"missing required fixture: {FIXTURE}")
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        states = {item["status"] for item in data["precheckItems"]}
        self.assertEqual(states, {"已定位证据", "信息不足", "未定位证据", "材料形式待确认"})
        self.assertTrue(data["confirmation"]["standardConfirmed"])
        self.assertTrue(data["confirmation"]["materialsConfirmedComplete"])
        self.assertIn("不构成正式资格审核", data["analysisRecord"]["preliminaryConclusion"])

    def test_template_has_precheck_sections_and_one_data_slot(self):
        template = self.read_skill_file("assets/material-precheck-template.html")
        self.assertEqual(template.count("__FLASH_DATA_JSON__"), 1)
        self.assertIn('id="flash-data"', template)
        self.assertIn("条件—证据预检", template)
        self.assertIn("补充信息与补件清单", template)
        self.assertIn("材料形式待人工确认", template)
        self.assertNotIn("五维检查", template)
```

- [ ] **Step 2: Verify red**

Run the Task 1 command. Expected: fixture and template missing-file assertion failures.

- [ ] **Step 3: Implement fixture and template**

The fixture must contain one adopted structured standard, two patient materials, exactly four precheck items—one per state—and a supplement list containing only the final three states. Its material-form entry must request only confirmation of acceptable evidence type. The single-file template must read only `#flash-data`, validate `flash-1.0/material_precheck`, use `textContent` for all user data, and render adopted standard, material inventory, precheck matrix, supplement list, material-form confirmation list, standard logic, analysis, sources and dual confirmations. It must label the report as precheck advice, not a final eligibility decision.

- [ ] **Step 4: Verify green and injection round trip**

Run the Task 1 command. Then inject escaped fixture JSON into the template with Node, extract `#flash-data`, parse it and assert object equality. Expected output: `flash-data round-trip: OK`.

- [ ] **Step 5: Commit complete Skill**

Commit message: `feat: add material precheck flash`.
