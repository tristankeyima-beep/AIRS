# 门诊慢特病审核质控 Skill 优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让模式 2 正确处理外部四位编码标准，生成语义一致、诊断友好且中文可导航的质控报告。

**Architecture:** 保留模式 1 的正式标准验证器，给模式 2 增加独立的可执行性检查口径。模型生成业务草稿，确定性准备工具负责材料键归一、三处哈希和未执行检查生成，严格渲染器负责最终验证与文本/HTML 输出。

**Tech Stack:** Python 3 标准库、`unittest`、离线 HTML/CSS、Markdown Skill 文档。

---

### Task 1: 模式 2 外部标准兼容检查

**Files:**
- Modify: `chronic-disease-certification-qc/scripts/inspect_standard.py`
- Modify: `chronic-disease-certification-qc/tests/test_inspect_standard.py`
- Modify: `chronic-disease-certification-qc/SKILL.md`

- [ ] **Step 1: 写四位/五位/统一字母数字编码通过，重复/混用/悬空引用失败的测试**

测试通过 `inspect_standard(value, profile="qc")` 调用兼容口径，并断言模式 1 默认口径仍拒绝非正式五位编码。

- [ ] **Step 2: 运行定向测试并确认失败**

Run: `python3 -m unittest chronic-disease-certification-qc/tests/test_inspect_standard.py -v`

Expected: FAIL，原因是 `inspect_standard` 尚不接受 `profile`。

- [ ] **Step 3: 实现 QC 兼容检查**

新增：

```python
def inspect_standard(value, profile="canonical"):
    if profile not in {"canonical", "qc"}:
        raise ValueError("profile must be canonical or qc")
    ...

def _validate_qc_standard(standard):
    # 非空且唯一的 ruleCode
    # 统一编码方案，不要求固定长度
    # RULE_REF 全部可解析且不重复
    # ruleContent 非空，guide 可归属
    # 正式来源字段差异记 warning，不阻断 executable
```

CLI 增加 `--profile canonical|qc`，模式 2 的 Skill 指令改为 `--profile qc`。

- [ ] **Step 4: 运行定向测试并确认通过**

Run: `python3 -m unittest chronic-disease-certification-qc/tests/test_inspect_standard.py -v`

Expected: PASS。

### Task 2: 确定性的质控报告准备工具

**Files:**
- Create: `chronic-disease-certification-qc/scripts/prepare_qc_report.py`
- Create: `chronic-disease-certification-qc/tests/test_prepare_qc_report.py`
- Modify: `chronic-disease-certification-qc/SKILL.md`

- [ ] **Step 1: 写材料键归一、三处哈希和未执行检查生成测试**

核心断言：

```python
prepared = prepare_report(draft)
assert prepared["rawInput"]["materials"][0]["content"] == "正文"
assert prepared["unperformedChecks"] == [
    {"name": "审核条件与结论一致性", "reason": "标准逻辑不可执行"}
]
validate_qc_report(prepared)
```

并覆盖 `materialContent`、`text`、`rawText` 到 `content` 的适配，以及正文键冲突时 fail-closed。

- [ ] **Step 2: 运行测试并确认失败**

Run: `python3 -m unittest chronic-disease-certification-qc/tests/test_prepare_qc_report.py -v`

Expected: FAIL，原因是模块不存在。

- [ ] **Step 3: 实现准备工具**

准备工具只做确定性工作：

```python
def prepare_report(draft):
    report = normalize_material_content(copy.deepcopy(draft))
    report["unperformedChecks"] = [
        {"name": item["name"], "reason": item["reason"]}
        for item in report["capabilities"]
        if item["status"] == "not_run"
    ]
    inventory = report["inputScope"]["inventory"]
    inventory["rawInputSha256"] = compute_raw_input_sha256(report["rawInput"])
    report["inputScope"]["confirmation"]["inventorySha256"] = compute_inventory_sha256(inventory)
    artifact = report["inputScope"]["independentReview"]["artifact"]
    report["inputScope"]["independentReview"]["artifactSha256"] = compute_independent_review_sha256(artifact)
    return validate_qc_report(report)
```

不得修改用户确认语句、revision、医学事实、问题严重程度和结论。

- [ ] **Step 4: 运行定向测试并确认通过**

Run: `python3 -m unittest chronic-disease-certification-qc/tests/test_prepare_qc_report.py -v`

Expected: PASS。

### Task 3: 单根因问题与风险一致性

**Files:**
- Modify: `chronic-disease-certification-qc/scripts/render_qc_html.py`
- Modify: `chronic-disease-certification-qc/references/report-contract.md`
- Modify: `chronic-disease-certification-qc/references/qc-rubric.md`
- Modify: `chronic-disease-certification-qc/tests/test_render_qc_html.py`

- [ ] **Step 1: 写新契约测试**

覆盖：

- `issueId` 唯一。
- `relatedCapabilities` 只允许五项能力、不得包含主 `category`、不得重复。
- 旧问题对象不带新字段仍通过。
- `ruleCode/keywordCode=""` 时页面显示“不适用”。
- 中/高等级问题存在时根风险不得为“未发现明显风险”。
- 一个问题跨能力只计一次。

- [ ] **Step 2: 运行定向测试并确认失败**

Run: `python3 -m unittest chronic-disease-certification-qc/tests/test_render_qc_html.py -v`

Expected: FAIL，原因是新字段被视为未知字段或风险约束尚不存在。

- [ ] **Step 3: 实现向后兼容契约**

问题必填字段保持不变，可选字段为：

```python
optional_issue_fields = {"issueId", "relatedCapabilities"}
```

风险一致性新增：

```python
if report["issues"] and any(i["severity"] in {"medium", "high"} for i in report["issues"]):
    if report["riskDirection"] == "未发现明显风险":
        _error("riskDirection", "cannot be 未发现明显风险 when medium/high issues exist")
```

问题索引以 `issueId` 为优先，否则使用稳定序号。

- [ ] **Step 4: 运行定向测试并确认通过**

Run: `python3 -m unittest chronic-disease-certification-qc/tests/test_render_qc_html.py -v`

Expected: PASS。

### Task 4: 渲染器诊断与回归夹具

**Files:**
- Modify: `chronic-disease-certification-qc/scripts/render_qc_html.py`
- Create: `chronic-disease-certification-qc/references/render-qc-html-constraints.md`
- Create: `chronic-disease-certification-qc/tests/fixtures/valid-qc-report-mode2-structured-complete-external.json`
- Create: `chronic-disease-certification-qc/tests/fixtures/valid-qc-report-mode2-structured-incomplete.json`
- Modify: `chronic-disease-certification-qc/tests/test_render_qc_html.py`
- Modify: `chronic-disease-certification-qc/tests/test_fixture_contracts.py`

- [ ] **Step 1: 写诊断文案和合法/非法变异测试**

断言错误包含：

- `materialEvidence must be an array; use [] ...`
- SHA 报错中的 `expected=` 与 `actual=`
- reason 两侧内容
- `rawInput.materials[].content`
- category 的双向修正建议

- [ ] **Step 2: 运行定向测试并确认失败**

Run: `python3 -m unittest chronic-disease-certification-qc/tests/test_render_qc_html.py chronic-disease-certification-qc/tests/test_fixture_contracts.py -v`

Expected: FAIL，旧文案不含完整修正信息且缺少新夹具。

- [ ] **Step 3: 实现 P0/P1/P2 诊断增强**

先检查 `materialEvidence` 是否为数组，再做状态耦合检查；三处哈希统一显示期望与实际；`--explain` 打印不含患者数据的稳定约束摘要。

- [ ] **Step 4: 将补充材料整理为仓库内约束文档**

以 `render-qc-html-constraints.md` 为唯一维护手册，删除与代码不一致的表述；合法 `structured_incomplete` 基线必须使用真正的执行缺陷，而不是四位编码。

- [ ] **Step 5: 运行定向测试并确认通过**

Run: `python3 -m unittest chronic-disease-certification-qc/tests/test_render_qc_html.py chronic-disease-certification-qc/tests/test_fixture_contracts.py -v`

Expected: PASS。

### Task 5: 中文化、左侧目录和区块顺序

**Files:**
- Modify: `chronic-disease-certification-qc/scripts/render_qc_html.py`
- Modify: `chronic-disease-certification-qc/assets/qc-report-template.html`
- Modify: `chronic-disease-certification-qc/tests/test_render_qc_html.py`

- [ ] **Step 1: 写 HTML 结构和中文标签测试**

覆盖：

- 状态、严重程度、置信度、证据状态、标准类型、审核类型和复核模式不显示英文枚举。
- 页面存在 `nav`、全部锚点、每个能力的“查看”链接。
- “建议”紧随“影响最终结论的问题”。
- 相关能力链接到同一 `issueId`。
- 打印隐藏目录，移动端目录可用，`scroll-margin` 与 `:target` 存在。

- [ ] **Step 2: 运行定向测试并确认失败**

Run: `python3 -m unittest chronic-disease-certification-qc/tests/test_render_qc_html.py -v`

Expected: FAIL，当前 HTML 显示英文枚举且无目录。

- [ ] **Step 3: 实现统一中文标签**

新增只负责显示的映射：

```python
CAPABILITY_STATUS_LABELS = {"completed": "已完成", "partial": "部分完成", "not_run": "未执行"}
SEVERITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
STANDARD_KIND_LABELS = {
    "structured_complete": "完整结构化标准",
    "structured_incomplete": "不完整结构化标准",
    "natural_language": "自然语言标准",
    "absent": "未提供标准",
}
```

文本和 HTML 共用映射。

- [ ] **Step 4: 实现离线导航布局**

页面使用：

```html
<a class="skip-link" href="#qc-report-main">跳至正文</a>
<div class="page-shell">
  <nav class="section-nav" aria-label="报告目录">...</nav>
  <main id="qc-report-main">...</main>
</div>
```

能力卡片使用 `href="#section-evidence-accuracy"` 等稳定锚点。桌面固定左栏，移动端顶部横向目录，打印隐藏。

- [ ] **Step 5: 运行定向测试并确认通过**

Run: `python3 -m unittest chronic-disease-certification-qc/tests/test_render_qc_html.py -v`

Expected: PASS。

### Task 6: Skill 流程、集成测试与最终验证

**Files:**
- Modify: `chronic-disease-certification-qc/SKILL.md`
- Modify: `chronic-disease-certification-qc/references/input-adapters.md`
- Modify: `chronic-disease-certification-qc/references/report-contract.md`
- Modify: `chronic-disease-certification-qc/tests/test_skill_contract.py`
- Modify: `chronic-disease-certification-qc/tests/test_integration.py`

- [ ] **Step 1: 写 Skill 契约与端到端失败测试**

断言模式 2：

- 使用 `inspect_standard.py --profile qc`。
- 使用准备工具生成正式规范对象。
- 不把四位编码当结构缺陷。
- 一处根因只生成一条 issue。
- 推荐区块顺序与 HTML 一致。

- [ ] **Step 2: 运行测试并确认失败**

Run: `python3 -m unittest chronic-disease-certification-qc/tests/test_skill_contract.py chronic-disease-certification-qc/tests/test_integration.py -v`

Expected: FAIL，现有 Skill 尚未声明新流程。

- [ ] **Step 3: 更新 Skill 和参考文档**

将模式 2 调整为：

```text
QC 兼容分类 → inventory 确认 → 独立复核冻结
→ 单根因比较 → 准备工具生成规范对象 → 严格渲染
```

模式 1 步骤和正式五位编码契约保持不变。

- [ ] **Step 4: 运行全量测试**

Run: `python3 -m unittest discover -s chronic-disease-certification-qc/tests -p 'test_*.py' -v`

Expected: 全部 PASS。

- [ ] **Step 5: 运行内容扫描与差异检查**

Run:

```bash
python3 chronic-disease-certification-qc/scripts/check_skill_content.py --root chronic-disease-certification-qc
git diff --check
```

Expected: 退出码 0，无禁用内容、无空白错误。
