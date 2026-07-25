# 门诊慢特病认定与审核质控 Flash 模式 1、模式 2 改版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 `flash-1.0` Schema、不增加外部运行时和运行文件的前提下，完成模式 1 逐层展开交互、模式 2 原审核结构化摘要与来源对比展示改版，并补强两种模式的生成契约和防呆校验。

**Architecture:** 运行时仍由 `SKILL.md`、三份 reference 和两个独立 HTML asset 组成。契约与检查清单约束模型生成，HTML 内置原生 JavaScript 负责固定展示、中文映射、轻量校验和安全降级；开发验收使用 Python `unittest`、Node.js `vm`/语法检查和浏览器检查，不成为 skill 运行依赖。

**Tech Stack:** Markdown、JSON、单文件 HTML/CSS/原生 JavaScript、Python 3 标准库 `unittest`、Node.js。

---

## File Map

**Runtime files to modify**

- `chronic-disease-certification-qc-flash/SKILL.md` — 阻断性歧义批量询问、逐份来源保存、两阶段隔离和材料确认门禁。
- `chronic-disease-certification-qc-flash/references/mode1-contract.md` — 规则拆分语义、连续原文引用、空编码和生成日期说明。
- `chronic-disease-certification-qc-flash/references/mode2-contract.md` — 逐份来源、标准规则码、材料 ID、结论优先级和非盲两阶段约束。
- `chronic-disease-certification-qc-flash/references/output-checklist.md` — 模式 1 十项检查、模式 2 材料 ID/方向/来源检查。
- `chronic-disease-certification-qc-flash/assets/certification-template.html` — 模式 1 层级树、中文提示、打印与键盘交互。
- `chronic-disease-certification-qc-flash/assets/qc-report-template.html` — 模式 2 章节重排、对比摘要、来源结构化展示和运行时校验。

**Development-only files to create or modify**

- Create `chronic-disease-certification-qc-flash-acceptance/tests/test_flash_contract_improvements.py` — 新契约和检查清单文本验收。
- Create `chronic-disease-certification-qc-flash-acceptance/tests/test_flash_mode1_improvements.py` — 模式 1 新模板行为验收。
- Create `chronic-disease-certification-qc-flash-acceptance/tests/test_flash_mode2_improvements.py` — 模式 2 新模板行为验收。
- Modify `chronic-disease-certification-qc-flash-acceptance/fixtures/valid-mode2.json` — 两份患者材料、正式标准规则码和可结构化原审核示例。
- Modify `chronic-disease-certification-qc-flash-acceptance/tests/test_flash_skill.py` — 仅更新既有 fixture 断言和通用 Node harness 输出，不在首轮并行任务中修改。

## Parallel Execution

首轮可并行执行 Task 1、Task 2、Task 3。三个任务不修改同一个文件：

- Agent A：Task 1，只改工作流、契约、清单及其独立测试。
- Agent B：Task 2，只改模式 1 模板及其独立测试。
- Agent C：Task 3，只改模式 2 模板及其独立测试。

首轮全部通过两阶段审查后，再顺序执行 Task 4 和 Task 5。这样可以使用三个实现代理，同时避免共享文件覆盖。

---

### Task 1: Strengthen Workflow Contracts and Checklists

**Files:**

- Modify: `chronic-disease-certification-qc-flash/SKILL.md`
- Modify: `chronic-disease-certification-qc-flash/references/mode1-contract.md`
- Modify: `chronic-disease-certification-qc-flash/references/mode2-contract.md`
- Modify: `chronic-disease-certification-qc-flash/references/output-checklist.md`
- Create: `chronic-disease-certification-qc-flash-acceptance/tests/test_flash_contract_improvements.py`

- [ ] **Step 1: Write failing documentation tests**

Create a focused `unittest` file with these exact assertions:

```python
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "chronic-disease-certification-qc-flash"


def read(relative):
    return (SKILL_ROOT / relative).read_text(encoding="utf-8")


class FlashContractImprovementTests(unittest.TestCase):
    def test_mode1_batches_blocking_ambiguities_and_defines_rule_splitting(self):
        skill = read("SKILL.md")
        contract = read("references/mode1-contract.md")
        self.assertIn("一次性列出", skill)
        self.assertIn("全部阻断性歧义", skill)
        self.assertIn("全部必须满足", contract)
        self.assertIn("保留在同一条规则", contract)
        self.assertIn("任一满足即可", contract)
        self.assertIn("拆成多条规则", contract)

    def test_mode1_requires_contiguous_exact_source_quotes_and_generation_date(self):
        contract = read("references/mode1-contract.md")
        self.assertIn("连续原句", contract)
        self.assertIn("不得拼接", contract)
        self.assertIn("不得改写文字或标点", contract)
        self.assertIn("未提供编码", contract)
        self.assertIn("成果生成日期", contract)
        self.assertIn("不是政策发布日期", contract)

    def test_mode1_checklist_has_ten_atomic_delivery_checks(self):
        checklist = read("references/output-checklist.md")
        section = checklist.split("## 模式 1", 1)[1].split("## 模式 2", 1)[0]
        boxes = [line for line in section.splitlines() if line.startswith("- [ ]")]
        self.assertEqual(10, len(boxes))
        for phrase in (
            "JSON 可解析",
            "根字段",
            "逐份",
            "连续原句",
            "规则 ID",
            "提取项 ID",
            "逻辑树",
            "七个字段",
            "确认",
            "逐字段等值",
        ):
            self.assertIn(phrase, section)

    def test_mode2_requires_one_source_per_input_and_true_confirmation(self):
        skill = read("SKILL.md")
        contract = read("references/mode2-contract.md")
        for phrase in (
            "一份输入材料对应一条",
            "不得合并",
            "完整原文",
        ):
            self.assertIn(phrase, contract)
        self.assertIn("不得默认", skill)
        self.assertIn("不得生成正式 JSON 或 HTML", skill)

    def test_mode2_freezes_base_review_before_audit_comparison(self):
        contract = read("references/mode2-contract.md")
        self.assertIn("不得引用 `audit_result`", contract)
        self.assertIn("`baseReview` 完成后", contract)
        self.assertIn("才能读取", contract)

    def test_mode2_rule_ids_material_ids_and_risk_priority_are_explicit(self):
        contract = read("references/mode2-contract.md")
        checklist = read("references/output-checklist.md")
        self.assertIn("直接复用", contract)
        self.assertIn("标准规则码", contract)
        self.assertIn("材料 ID", contract)
        self.assertIn("至少为 `medium`", contract)
        self.assertIn("当且仅当五个维度全部", contract)
        self.assertIn("任何问题", contract)
        self.assertIn("problematic", contract)
        self.assertIn("risk=none", contract)
        self.assertIn("所有材料 ID", checklist)
        self.assertIn("先形成 `baseReview`", checklist)
        self.assertIn("仅有 `not_checked` 且没有实际问题", contract)
        self.assertIn("实际规则维护问题", contract)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python3 -m unittest \
  chronic-disease-certification-qc-flash-acceptance/tests/test_flash_contract_improvements.py \
  -v
```

Expected: FAIL on missing phrases and the mode 1 checklist item count.

- [ ] **Step 3: Update `SKILL.md` without increasing runtime file count**

Make these workflow changes:

```markdown
# Mode 1 step 4
检查 AND/OR、阈值、单位、持续时间、次数、适用范围、排除项、共享前提和来源冲突；一次性列出当前发现的全部阻断性歧义并统一询问。

# Mode 2 source and confirmation steps
逐份盘点患者材料、认定标准和原审核结果；一份输入材料对应一条来源记录，不得把多份材料合并成摘要。
用户未明确确认时不得默认材料完整，不得生成正式 JSON 或 HTML。

# Mode 2 stage boundary
先只依据患者材料和认定标准完成并冻结 baseReview；形成 materialFacts、ruleJudgments 和 preliminaryResult 时不得引用 audit_result。baseReview 完成后才能读取原审核结果形成 auditComparison。
```

Retain the existing slot injection, secret-stop and external-send safeguards.

- [ ] **Step 4: Update `mode1-contract.md`**

Add an explicit “规则拆分与来源定位” subsection containing:

```markdown
- 多个子条件全部必须满足时，可以保留在同一条规则的 `content` 中。
- 出现“任一满足即可”等 OR 备选分支时，必须拆成多条规则，再由 `logic` 的 OR 组组合。
- `sourceQuote` 必须是单一来源中的连续原句；不得拼接不连续片段，不得改写文字或标点。
- `diseaseCode` 为空时 HTML 显示“未提供编码”，不得据此判定标准无效。
- `VYYYYMMDD` 形式的交付版本表示成果生成日期，不是政策发布日期。
```

- [ ] **Step 5: Update `mode2-contract.md`**

Add exact requirements for:

```markdown
- 一份输入材料对应一条 `sourceDocuments`；不得合并多份材料，`content` 保存完整原文。
- 形成 `baseReview` 时不得引用 `audit_result`；`baseReview` 完成后才能读取原审核内容。
- `standardKind=structured` 时，`ruleJudgments.ruleId` 直接复用标准规则码，并覆盖标准逻辑引用的全部规则。
- 原审核引用的材料 ID 必须能在患者材料名称或完整原文中定位；不能定位时形成“证据提取准确性”问题，严重程度至少为 `medium`。
- 原审核引用的材料 ID 必须原样写入对应问题的 `sourceReference`，供模板高亮和定位。
- 当且仅当五个维度全部 `passed` 且 `issues` 为空时才能使用 `reliable`。
- 存在任何问题时必须使用 `problematic`；方向一致的局部问题允许 `risk=none`。
- 仅有 `not_checked` 且没有实际问题时保持 `uncertain + unknown`；结论信息受限但已确认存在实际规则维护问题时使用 `problematic + none`。
```

Keep the `natural_language` `TMP-R001` branch. Update the conclusion-only branch so actual issue records always produce `problematic`; retain `uncertain + unknown` only for incomplete checks with no confirmed issue.

- [ ] **Step 6: Replace the mode 1 checklist with ten atomic items and extend mode 2**

Use exactly ten mode 1 checkboxes matching Step 1. Add mode 2 checkboxes for:

```markdown
- [ ] 每份输入材料各占一条来源记录，完整原文未被摘要替代。
- [ ] `baseReview` 已在读取和比较原审核主张、证据、推理及结论之前形成。
- [ ] 结构化标准的逐规则复核直接复用标准规则码并覆盖全部标准规则。
- [ ] 原审核结果中出现的所有材料 ID 均已对照患者材料名称和完整原文核验；无法定位的引用已形成至少中等严重程度的问题。
- [ ] 只有五维全部通过且没有问题时才使用“可靠”；方向一致但有局部问题时使用“存在问题 + 无方向性风险”。
```

- [ ] **Step 7: Run focused and existing documentation tests**

Run:

```bash
python3 -m unittest \
  chronic-disease-certification-qc-flash-acceptance/tests/test_flash_contract_improvements.py \
  -v
python3 -m unittest discover \
  -s chronic-disease-certification-qc-flash-acceptance/tests \
  -p 'test_*.py' -v
```

Expected: the focused tests PASS. The existing suite remains green because this task changes documentation only.

- [ ] **Step 8: Commit Task 1**

```bash
git add chronic-disease-certification-qc-flash/SKILL.md \
  chronic-disease-certification-qc-flash/references/mode1-contract.md \
  chronic-disease-certification-qc-flash/references/mode2-contract.md \
  chronic-disease-certification-qc-flash/references/output-checklist.md \
  chronic-disease-certification-qc-flash-acceptance/tests/test_flash_contract_improvements.py
git commit -m "feat: strengthen flash generation contracts"
```

---

### Task 2: Build the Mode 1 Hierarchical Rule and Extraction View

**Files:**

- Modify: `chronic-disease-certification-qc-flash/assets/certification-template.html`
- Create: `chronic-disease-certification-qc-flash-acceptance/tests/test_flash_mode1_improvements.py`

- [ ] **Step 1: Write failing template tests**

The focused test must read only the mode 1 template and assert:

```python
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "chronic-disease-certification-qc-flash/assets/certification-template.html"


class FlashMode1ImprovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")
        cls.renderer = re.findall(
            r"<script(?:\\s[^>]*)?>(.*?)</script>",
            cls.html,
            re.S | re.I,
        )[1]

    def test_flat_extraction_cards_are_removed(self):
        self.assertNotIn("extraction-grid", self.html)
        self.assertNotIn("extraction-card", self.html)

    def test_renderer_declares_group_rule_and_extraction_layers(self):
        for marker in (
            "logic-group",
            "logic-rule",
            "logic-extraction",
            "取证与判断指引",
            "expectedEvidence",
            "negativeEvidence",
            "unknownWhen",
            "preferredSource",
        ):
            self.assertIn(marker, self.renderer)

    def test_rule_and_extraction_summaries_include_business_fields(self):
        self.assertIn("rule.content", self.renderer)
        self.assertIn("item.name", self.renderer)
        self.assertIn("item.dataType", self.renderer)

    def test_preliminary_conclusion_and_empty_code_labels_are_chinese(self):
        self.assertIn("本次标准整理初步结论", self.renderer)
        self.assertIn("analysisRecord.preliminaryConclusion", self.renderer)
        self.assertIn("未提供编码", self.renderer)

    def test_source_quote_warning_is_nonblocking(self):
        self.assertIn("来源原文中未精确定位", self.renderer)
        self.assertIn("source-warning", self.html)

    def test_print_opens_nested_business_content(self):
        self.assertRegex(
            self.html,
            r"@media print[\\s\\S]*details:not\\(\\[open\\]\\)[\\s\\S]*display:\\s*block",
        )

    def test_renderer_has_valid_javascript(self):
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as handle:
            handle.write(self.renderer)
            handle.flush()
            result = subprocess.run(
                ["node", "--check", handle.name],
                capture_output=True,
                text=True,
            )
        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python3 -m unittest \
  chronic-disease-certification-qc-flash-acceptance/tests/test_flash_mode1_improvements.py \
  -v
```

Expected: FAIL because flat extraction classes still exist and the nested layer markers are absent.

- [ ] **Step 3: Replace flat extraction CSS with nested tree CSS**

Remove `.extraction-grid` and `.extraction-card`. Add focused classes:

```css
.logic-group { display: grid; gap: 0.75rem; }
.logic-group-children {
  display: grid;
  gap: 0.75rem;
  margin-left: 1rem;
  padding-left: 1rem;
  border-left: 2px solid var(--line-strong);
}
.logic-rule,
.logic-extraction { border: 1px solid var(--line); border-radius: 14px; }
.logic-rule > summary,
.logic-extraction > summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  cursor: pointer;
}
.source-warning {
  color: var(--danger);
  background: var(--danger-soft);
  border-left: 3px solid var(--danger);
  padding: 0.75rem 1rem;
}
```

Reuse existing colors and typography variables; do not introduce remote assets or motion libraries.

- [ ] **Step 4: Render the logical overview and hierarchical rule tree**

Replace the existing compact `renderLogic`, flat `renderRules` and flat `renderExtractions` with one recursive hierarchical renderer. Do not keep a second compact topology view. Its core interfaces are:

```javascript
const renderExtraction = item => {
  const details = node("details", null, "logic-extraction");
  const summary = node("summary");
  add(
    summary,
    node("strong", `${text(item.id)} · ${text(item.name)}`),
    makeBadge(item.dataType)
  );
  const body = node("div", null, "detail-body");
  add(
    body,
    detail("预期证据", item.expectedEvidence),
    detail("反向证据", item.negativeEvidence),
    detail("无法判断条件", item.unknownWhen),
    detail("优先材料来源", item.preferredSource)
  );
  add(details, summary, node("span", "取证与判断指引", "label"), body);
  return details;
};

const add = (parent, ...children) => {
  parent.append(...children);
  return parent;
};

const text = value => displayValue(value);

const makeBadge = value => node(
  "span",
  LABELS[value] || displayValue(value),
  "badge"
);

const detail = (label, value) => {
  const wrap = node("div", null, "detail");
  add(wrap, node("span", label, "label"), node("p", text(value)));
  return wrap;
};

const renderRule = (rule, sourceDocuments) => {
  const details = node("details", null, "logic-rule");
  const summary = node("summary");
  add(
    summary,
    node("strong", `${text(rule.id)} · ${text(rule.content)}`),
    node("span", `${rule.extractionItems.length} 个提取项`, "count")
  );
  const body = node("div", null, "detail-body");
  add(body, detail("规则内容", rule.content), detail("来源原文", rule.sourceQuote));
  if (!sourceDocuments.some(source => source.content.includes(rule.sourceQuote))) {
    add(body, node("p", "警告：来源原文中未精确定位该引用，请人工核对。", "source-warning"));
  }
  rule.extractionItems.forEach(item => body.append(renderExtraction(item)));
  add(details, summary, body);
  return details;
};

const renderRuleTree = (logic, ruleMap, sourceDocuments) => {
  if (logic.type === "rule") {
    return renderRule(ruleMap.get(logic.ruleId), sourceDocuments);
  }
  const group = node("div", null, "logic-group");
  add(group, makeBadge(logic.operator), node("span", logic.operator === "AND" ? "且" : "或", "operator-cn"));
  const children = node("div", null, "logic-group-children");
  logic.children.forEach(child => children.append(
    renderRuleTree(child, ruleMap, sourceDocuments)
  ));
  add(group, children);
  return group;
};
```

Keep the existing `node`, `displayValue`, `appendRows` and `LABELS` helpers. Add the complete `add`, `text`, `makeBadge` and `detail` helpers shown above before the hierarchical renderer.

- [ ] **Step 5: Add preliminary conclusion, disease code fallback and anchors**

In `renderOverview`, render:

```javascript
const diseaseCode = data.meta.diseaseCode.trim()
  ? data.meta.diseaseCode
  : "未提供编码";
```

At the top of the logic section render:

```javascript
makeValueCard(
  "本次标准整理初步结论",
  data.analysisRecord.preliminaryConclusion
)
```

Keep left navigation usable. “逻辑关系” points to static section `#logic`. Remove the two old sibling flat sections. Assign `id="rules"` and `tabindex="-1"` to the first rendered rule `<details>`, and assign `id="extractions"` and `tabindex="-1"` to the first rendered extraction `<details>`; validation already guarantees both exist in a formal report. Pass a shared `{ruleAnchorAssigned: false, extractionAnchorAssigned: false}` state through the recursive renderer so each ID appears exactly once. `renderReport` must call the hierarchical renderer once, producing logical group → rule `<details>` → extraction `<details>` without duplicate topology or flat views.

- [ ] **Step 6: Make print, focus and reduced-motion behavior deterministic**

Ensure print CSS reveals all descendants of closed `details`, focus-visible outlines remain present, and no new animation runs when `prefers-reduced-motion: reduce`.

- [ ] **Step 7: Run focused mode 1 and existing template tests**

Run:

```bash
python3 -m unittest \
  chronic-disease-certification-qc-flash-acceptance/tests/test_flash_mode1_improvements.py \
  -v
python3 -m unittest discover \
  -s chronic-disease-certification-qc-flash-acceptance/tests \
  -p 'test_*.py' -v
```

Expected: focused tests PASS. The only permitted temporary failures in the existing suite are the superseded assertions that require `rules` and `extractions` to be sibling `<section>` elements; list their exact test names for Task 4. Security, slot, hostile-input and formal-delivery-gate tests must remain green.

- [ ] **Step 8: Commit Task 2**

```bash
git add chronic-disease-certification-qc-flash/assets/certification-template.html \
  chronic-disease-certification-qc-flash-acceptance/tests/test_flash_mode1_improvements.py
git commit -m "feat: add hierarchical flash mode1 view"
```

---

### Task 3: Redesign the Mode 2 Report and Add Safe Structured Source Views

**Files:**

- Modify: `chronic-disease-certification-qc-flash/assets/qc-report-template.html`
- Create: `chronic-disease-certification-qc-flash-acceptance/tests/test_flash_mode2_improvements.py`

- [ ] **Step 1: Write failing mode 2 template tests**

Create focused tests that assert:

```python
def test_sections_move_sources_to_number_three(self):
    expected = [
        ("01", "summary", "结论总览"),
        ("02", "scope", "输入范围"),
        ("03", "sources", "原始材料"),
        ("04", "dimensions", "五维检查"),
        ("05", "issues", "问题清单"),
        ("06", "rules", "逐规则复核"),
        ("07", "recommendations", "建议"),
        ("08", "analysis", "分析记录"),
        ("09", "confirmation", "确认记录"),
    ]
    positions = []
    for number, section_id, title in expected:
        marker = f'<section id="{section_id}"'
        self.assertIn(marker, self.html)
        self.assertIn(f'<span class="number">{number}</span>', self.html)
        self.assertIn(title, self.html)
        positions.append(self.html.index(marker))
    self.assertEqual(sorted(positions), positions)

def test_plain_method_label_and_current_qc_fact_label_exist(self):
    self.assertIn("两阶段复核：先独立判断，再对照原审核", self.renderer)
    self.assertIn("原审核结果在同一任务中可见", self.renderer)
    self.assertIn("本次质控提取的患者材料事实", self.renderer)
    self.assertIn("不代表原审核结论", self.renderer)

def test_source_renderer_has_json_text_and_fallback_paths(self):
    for marker in (
        "renderStructuredValue",
        "segmentAuditText",
        "renderAuditSummary",
        "查看完整原文",
        "无法自动结构化",
    ):
        self.assertIn(marker, self.renderer)

def test_summary_compares_two_directions(self):
    for marker in (
        "本次独立复核",
        "原审核结论",
        "方向判断",
        "方向一致",
        "方向相反",
    ):
        self.assertIn(marker, self.renderer)

def test_material_id_and_temp_rule_warnings_are_chinese(self):
    self.assertIn("引用材料未在本报告材料清单中", self.renderer)
    self.assertIn("本次质控临时规则，非正式业务标准", self.renderer)

def test_risk_validator_prioritizes_negative_conclusions(self):
    negative = self.renderer.index('text.includes("不通过")')
    positive = self.renderer.index('text.includes("通过")')
    self.assertLess(negative, positive)
    self.assertIn("风险方向与复核结论不一致", self.renderer)

def test_not_checked_reason_has_dedicated_class(self):
    self.assertIn("not-checked-reason", self.html)
    self.assertIn("本项因输入受限未核查", self.renderer)
```

The test file must also extract the second script and run `node --check` exactly as Task 2 does.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python3 -m unittest \
  chronic-disease-certification-qc-flash-acceptance/tests/test_flash_mode2_improvements.py \
  -v
```

Expected: FAIL because sources are section 08 and the new helpers/labels do not exist.

- [ ] **Step 3: Reorder static sections and navigation**

Move the existing `sources` section and navigation item to position 03, then renumber every following section. Do not duplicate or rename renderer target IDs.

- [ ] **Step 4: Normalize directions and validate risk**

Add these helpers before `validate`:

```javascript
const normalizeOriginalDirection = value => {
  const text = String(value || "").replace(/\s+/g, "");
  if (
    text.includes("不通过")
    || text.includes("不予通过")
    || text.includes("拒绝")
  ) return "does_not_meet";
  if (text.includes("通过")) return "meets";
  return "uncertain";
};

const validateRiskDirection = data => {
  const preliminary = data.baseReview.preliminaryResult;
  const comparison = data.auditComparison;
  const original = normalizeOriginalDirection(comparison.originalConclusion);

  if (comparison.qcConclusion === "uncertain") {
    if (comparison.risk !== "unknown") {
      throw new Error("风险方向与复核结论不一致");
    }
    return;
  }
  if (comparison.qcConclusion === "reliable") {
    if (comparison.risk !== "none") {
      throw new Error("风险方向与复核结论不一致");
    }
    return;
  }
  if (original === "meets" && preliminary === "does_not_meet") {
    if (comparison.risk !== "false_approval") {
      throw new Error("风险方向与复核结论不一致");
    }
    return;
  }
  if (original === "does_not_meet" && preliminary === "meets") {
    if (comparison.risk !== "false_rejection") {
      throw new Error("风险方向与复核结论不一致");
    }
    return;
  }
  if (
    original !== "uncertain"
    && preliminary !== "uncertain"
    && original === preliminary
    && comparison.risk !== "none"
  ) {
    throw new Error("风险方向与复核结论不一致");
  }
  if (
    (original === "uncertain" || preliminary === "uncertain")
    && ["false_approval", "false_rejection", "both"].includes(comparison.risk)
  ) {
    throw new Error("风险方向与复核结论不一致");
  }
};
```

Call `validateRiskDirection(data)` only after the `qcConclusion`、`auditDetail` and conclusion-only degradation checks. Update those checks first: conclusion-only “方向一致 + uncertain/unknown” is valid only when the inspected dimensions contain no confirmed issue; any confirmed rule-maintenance or other issue must use `problematic + none`. This preserves valid incomplete-without-issue reports while enforcing the approved “any actual issue means problematic” rule.

- [ ] **Step 5: Redesign summary and scope**

In `renderSummary`, add cards for `baseReview.preliminaryResult`, `auditComparison.originalConclusion`, computed direction, `qcConclusion` and `risk`.

In `renderScope`:

- change the method label to “两阶段复核：先独立判断，再对照原审核”;
- add the non-blind explanation;
- remove the duplicated `materialFacts` card.

- [ ] **Step 6: Render current-QC facts and temporary rule labels**

At the top of `renderRules` use:

```javascript
node("h3", "本次质控提取的患者材料事实"),
node(
  "p",
  "以下内容由本次质控根据患者材料归纳形成，用于独立复核，不代表原审核结论；原始依据以“原始材料”中的完整原文为准。",
  "section-note"
)
```

When `judgment.ruleId.startsWith("TMP-")`, append:

```javascript
node("small", "本次质控临时规则，非正式业务标准", "temp-rule-note")
```

- [ ] **Step 7: Add structured audit-result summaries with exact raw fallback**

Implement three bounded helpers:

```javascript
const renderStructuredValue = (
  value,
  key = "",
  state = { nodes: 0 },
  depth = 0
) => {
  const wrap = node("div", null, "structured-value");
  if (key) wrap.appendChild(node("span", key, "label"));
  state.nodes += 1;
  if (depth > 8 || state.nodes > 500) {
    wrap.appendChild(node("p", "内容较多，请查看完整原文。", "source-warning"));
    return wrap;
  }
  if (Array.isArray(value)) {
    const list = node("ol", null, "structured-list");
    value.forEach((item, index) => {
      const entry = node("li");
      entry.appendChild(
        renderStructuredValue(item, `第 ${index + 1} 项`, state, depth + 1)
      );
      list.appendChild(entry);
    });
    wrap.appendChild(list);
    return wrap;
  }
  if (value && typeof value === "object") {
    Object.entries(value).forEach(([childKey, childValue]) => {
      wrap.appendChild(
        renderStructuredValue(childValue, childKey, state, depth + 1)
      );
    });
    return wrap;
  }
  wrap.appendChild(node("p", text(value)));
  return wrap;
};

const segmentAuditText = content => {
  const definitions = [
    ["最终审核结论", /(?:finalResult|最终结论)\s*[:=：]\s*/i],
    ["逐规则审核结果", /(?:ruleResults|逐规则(?:审核)?结果)\s*[:=：]\s*/i],
    ["原审核建议", /(?:advice|审核建议)\s*[:=：]\s*/i],
  ];
  const hits = definitions.flatMap(([label, pattern]) => {
    const match = pattern.exec(content);
    return match ? [{
      label,
      index: match.index,
      valueStart: match.index + match[0].length,
    }] : [];
  }).sort((left, right) => left.index - right.index);
  if (hits.length < 2) return [];
  return hits.map((hit, index) => ({
    label: hit.label,
    value: content.slice(
      hit.valueStart,
      index + 1 < hits.length ? hits[index + 1].index : content.length
    ).trim().replace(/[；;]\s*$/, ""),
  })).filter(segment => segment.value);
};

const renderSegmentCards = segments => {
  const root = node("div", null, "audit-summary-grid");
  segments.forEach(segment => {
    const card = node("article", null, "audit-summary-card");
    add(card, node("h4", segment.label));
    if (segment.label === "逐规则审核结果") {
      const rules = segmentRuleResults(segment.value);
      if (rules.length) {
        rules.forEach(rule => card.appendChild(renderAuditRule(rule)));
      } else {
        card.appendChild(node("p", segment.value));
      }
    } else {
      card.appendChild(node("p", segment.value));
    }
    root.appendChild(card);
  });
  return root;
};

const segmentExtractionItems = content => {
  const pattern = /(\d{3,}_\d{2})\s*[:：]?\s*/g;
  const hits = Array.from(content.matchAll(pattern));
  return hits.map((match, index) => ({
    id: match[1],
    value: content.slice(
      match.index + match[0].length,
      index + 1 < hits.length ? hits[index + 1].index : content.length
    ).trim().replace(/^[（(]|[）)]$/g, ""),
  })).filter(item => item.value);
};

const segmentRuleResults = content => {
  const pattern = /(?:^|[；;\n])\s*(\d{3,})\s*(通过|不通过)\s*/g;
  const hits = Array.from(content.matchAll(pattern));
  return hits.map((match, index) => {
    const value = content.slice(
      match.index + match[0].length,
      index + 1 < hits.length ? hits[index + 1].index : content.length
    ).trim();
    return {
      id: match[1],
      result: match[2],
      value,
      extractionItems: segmentExtractionItems(value),
    };
  });
};

const renderAuditRule = rule => {
  const details = node("details", null, "audit-rule");
  add(
    details,
    node("summary", `${rule.id} · ${rule.result}`)
  );
  if (!rule.extractionItems.length) {
    details.appendChild(node("p", rule.value));
    return details;
  }
  rule.extractionItems.forEach(item => {
    const card = node("article", null, "audit-extraction");
    add(card, node("h5", item.id), node("p", item.value));
    details.appendChild(card);
  });
  return details;
};

const renderAuditSummary = content => {
  try {
    return renderStructuredValue(JSON.parse(content));
  } catch (_error) {
    const segments = segmentAuditText(content);
    if (segments.length) return renderSegmentCards(segments);
    return node(
      "p",
      "原审核结果无法自动结构化，以下按原文展示。",
      "source-warning"
    );
  }
};
```

For every `audit_result`, render the summary first and then a nested `<details>` labelled “查看完整原文”. The full-original `<pre>` must use the unmodified `source.content`. The structured renderer must not use `innerHTML`, `eval` or dynamic code. If the `ruleResults` segment has unambiguous `1001 不通过` and `1001_01`-style delimiters, split it into rule and extraction-item cards; otherwise keep the whole segment as “逐规则审核结果” without semantic guessing.

- [ ] **Step 8: Add material-ID highlighting and source links**

Use the conservative pattern `/\b\d{8,}\b/g`. Build an index from the concatenated `name` and `content` of each `patient_material` source. When an ID in issue fields matches, link to the corresponding source `<details id="source-N">`; when it does not match, append `引用材料未在本报告材料清单中`. This is a display warning and must not create or change `issues`.

- [ ] **Step 9: Strengthen not-checked presentation**

When a dimension is `not_checked`, render:

```javascript
node("strong", "本项因输入受限未核查", "not-checked-title"),
node("p", dimension.notCheckedReason, "not-checked-reason")
```

Add dedicated high-contrast CSS while keeping print output readable.

- [ ] **Step 10: Run focused and existing mode 2 tests**

Run:

```bash
python3 -m unittest \
  chronic-disease-certification-qc-flash-acceptance/tests/test_flash_mode2_improvements.py \
  -v
python3 -m unittest discover \
  -s chronic-disease-certification-qc-flash-acceptance/tests \
  -p 'test_*.py' -v
```

Expected: focused tests PASS. The only permitted temporary failures in the existing suite are exact section-order or summary-shape assertions superseded by the approved design; list their exact test names for Task 4. Bad JSON, data-slot, hostile-source and formal-delivery-gate tests must remain green.

- [ ] **Step 11: Commit Task 3**

```bash
git add chronic-disease-certification-qc-flash/assets/qc-report-template.html \
  chronic-disease-certification-qc-flash-acceptance/tests/test_flash_mode2_improvements.py
git commit -m "feat: redesign flash mode2 report"
```

---

### Task 4: Align Fixtures, Cross-Field Validators, and Existing Acceptance Tests

**Files:**

- Modify: `chronic-disease-certification-qc-flash-acceptance/fixtures/valid-mode2.json`
- Modify: `chronic-disease-certification-qc-flash-acceptance/tests/test_flash_skill.py`

- [ ] **Step 1: Write failing fixture-level assertions**

Extend the canonical fixture test, not the generic validator, to require:

```python
patient_sources = [
    source for source in fixture["sourceDocuments"]
    if source["type"] == "patient_material"
]
test_case.assertEqual(2, len(patient_sources))
test_case.assertTrue(all(
    re.search(r"\d{8,}", source["name"])
    for source in patient_sources
))
if fixture["inputProfile"]["standardKind"] == "structured":
    test_case.assertTrue(all(
        not judgment["ruleId"].startswith("R")
        and not judgment["ruleId"].startswith("TMP-")
        for judgment in fixture["baseReview"]["ruleJudgments"]
))
```

Keep `assert_valid_mode2` usable for generic structured-standard prose that does not expose a machine-readable rule-code set. Add a canonical-fixture assertion proving its explicit standard rule `1001` maps to `ruleJudgments.ruleId == "1001"`. Retain the existing missing-inventory mutation test.

- [ ] **Step 2: Run the affected tests and verify RED**

Run:

```bash
python3 -m unittest \
  chronic-disease-certification-qc-flash-acceptance.tests.test_flash_skill.Mode2FixtureContractTests \
  -v
```

Expected: FAIL on the current single patient source and `R001`.

- [ ] **Step 3: Update the canonical mode 2 fixture**

Use two separate generic patient sources with long IDs in their names, for example:

```json
{
  "name": "患者材料-门诊记录-2079388752224174082",
  "type": "patient_material",
  "content": "材料ID 2079388752224174082：患者材料明确记载证据 A。"
},
{
  "name": "患者材料-检查报告-2079388752224174083",
  "type": "patient_material",
  "content": "材料ID 2079388752224174083：检查报告补充记载证据 A。"
}
```

Make the standard source explicitly declare rule `1001`, change `ruleJudgments.ruleId` to `1001`, use an original-audit content string containing `finalResult`、`ruleResults` and `advice`, and update `confirmation.inventoryShown` exactly.

- [ ] **Step 4: Update the generic validator and Node harness outputs**

Keep all old schema checks. Add structured-rule prefix rejection only to structured test scenarios that contain an explicit standard rule code; do not guess codes from arbitrary natural-language standards.

Update the superseded conclusion-only tests:

- rename `test_direction_consistent_rule_issue_remains_uncertain` to assert `problematic + none`;
- replace `test_rejects_problematic_none_for_direction_consistent_rule_issue` with a test that rejects `uncertain + unknown` when an actual issue exists;
- retain a separate test proving direction-consistent `not_checked` dimensions without any actual issue remain `uncertain + unknown`.

Update the mode 1 exact-section tests so `rules` and `extractions` are unique runtime anchors on the first rule and extraction nodes rather than static sibling sections. Extend the Node harness with stable traversal data proving the DOM path is group → rule `<details>` → extraction `<details>`.

Extend the Node harness output only with stable values needed by new behavioral tests, such as:

```javascript
summaryText: collectText(summary),
rulesText: collectText(rules),
sourcesText: collectText(elements.get("sources-content"))
```

Also expose `logicTreeShape`, `ruleNodeCount`, `extractionNodeCount` and material-link targets from the harness. Do not change runtime files in this task.

- [ ] **Step 5: Run all Flash acceptance tests**

Run:

```bash
python3 -m unittest discover \
  -s chronic-disease-certification-qc-flash-acceptance/tests \
  -p 'test_*.py' -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add chronic-disease-certification-qc-flash-acceptance/fixtures/valid-mode2.json \
  chronic-disease-certification-qc-flash-acceptance/tests
git commit -m "test: align flash improvement fixtures"
```

---

### Task 5: Full Regression, Browser Verification, and Final Review

**Files:**

- Modify only if verification exposes a defect: files already listed in Tasks 1–4.
- Do not modify: `chronic-disease-certification-qc/` runtime files.

- [ ] **Step 1: Validate the runtime skill package**

Run:

```bash
python3 /Users/Tristan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  chronic-disease-certification-qc-flash
```

Expected: the skill is valid and runtime layout still contains exactly seven files.

- [ ] **Step 2: Run the complete Flash suite**

Run:

```bash
python3 -m unittest discover \
  -s chronic-disease-certification-qc-flash-acceptance/tests \
  -p 'test_*.py' -v
```

Expected: all Flash tests PASS.

- [ ] **Step 3: Run the standard skill regression suites**

Run:

```bash
python3 -m unittest discover \
  -s chronic-disease-certification-qc/tests \
  -p 'test_*.py' -v
python3 -m unittest discover \
  -s chronic-disease-certification-qc-acceptance/tests \
  -p 'test_*.py' -v
```

Expected: both suites PASS without modifying the standard skill.

- [ ] **Step 4: Generate browser fixtures from the canonical JSON**

Copy each template to a temporary directory, safely replace its single `__FLASH_DATA_JSON__` slot using the same `<`、`>`、`&` Unicode escaping rule, and verify the extracted slot round-trips to the source fixture. Do not write generated artifacts into the seven-file runtime directory.

- [ ] **Step 5: Inspect both generated pages in a real browser**

Mode 1 checks:

- left navigation reaches logic, rules and extraction layers;
- rules and extraction items progressively open;
- rule content is visible in the rule summary;
- the preliminary conclusion and empty-code fallback render in Chinese;
- print preview exposes folded content.

Mode 2 checks:

- original materials are section 03;
- independent and original conclusions appear side by side;
- each source is separate;
- original audit summary is structured and full raw text expands;
- missing material IDs and `not_checked` reasons are conspicuous;
- mobile-width navigation and keyboard focus work.

- [ ] **Step 6: Request two-stage final review**

Dispatch a specification-compliance reviewer against the approved design, then a code-quality reviewer against the resulting diff. Fix every confirmed issue and rerun the smallest relevant test followed by all three full suites.

- [ ] **Step 7: Confirm clean diff and commit any review fixes**

Run:

```bash
git diff --check
git status --short
git log -6 --oneline
```

Expected: no whitespace errors, only intended changes, and all implementation commits present. If review fixes were required:

```bash
git add chronic-disease-certification-qc-flash \
  chronic-disease-certification-qc-flash-acceptance
git commit -m "fix: address flash improvement review"
```
