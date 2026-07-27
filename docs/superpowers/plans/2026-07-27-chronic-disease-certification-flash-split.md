# 门诊慢特病 Flash Skill 拆分实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有二合一 Flash Skill 拆成独立的认定标准生成 Skill 和审核质控 Skill，并删除独立 acceptance 验收工程。

**Architecture:** 模式 2 沿用现有 `chronic-disease-certification-qc-flash` 目录并移除模式 1 文件；模式 1 新建 `chronic-disease-certification-standard-flash`，承接现有模式 1 契约和模板。两个 Skill 各自维护入口、UI 元数据和专用清单，不增加共享目录或兼容路由。

**Tech Stack:** Markdown Skill、YAML UI 元数据、单文件离线 HTML、Git、Shell/Python 一次性结构验证。

---

## 文件映射

### 新建

- `chronic-disease-certification-standard-flash/SKILL.md`：认定标准生成专用工作流。
- `chronic-disease-certification-standard-flash/agents/openai.yaml`：模式 1 的展示名称、简介和默认提示词。
- `chronic-disease-certification-standard-flash/references/output-checklist.md`：通用检查和模式 1 检查。

### 移动

- `chronic-disease-certification-qc-flash/references/mode1-contract.md` → `chronic-disease-certification-standard-flash/references/mode1-contract.md`
- `chronic-disease-certification-qc-flash/assets/certification-template.html` → `chronic-disease-certification-standard-flash/assets/certification-template.html`

### 修改

- `chronic-disease-certification-qc-flash/SKILL.md`：收窄为审核质控专用工作流。
- `chronic-disease-certification-qc-flash/agents/openai.yaml`：收窄为审核质控专用 UI 元数据。
- `chronic-disease-certification-qc-flash/references/output-checklist.md`：只保留通用检查和模式 2 检查。

### 删除

- `chronic-disease-certification-qc-flash-acceptance/`：删除全部测试、fixture 和验收记录。

## Task 1：建立拆分前失败基线

**Files:**
- Read: `chronic-disease-certification-qc-flash/`
- Expected missing: `chronic-disease-certification-standard-flash/`

- [ ] **Step 1：运行一次性拆分结构断言**

```bash
python3 - <<'PY'
from pathlib import Path

root = Path(".")
standard = root / "chronic-disease-certification-standard-flash"
qc = root / "chronic-disease-certification-qc-flash"
assert standard.is_dir(), "模式 1 独立 Skill 尚不存在"
assert qc.is_dir(), "模式 2 Skill 不存在"
PY
```

Expected: FAIL，错误为 `模式 1 独立 Skill 尚不存在`。该失败证明断言能识别尚未拆分的现状。

## Task 2：创建认定标准生成 Skill

**Files:**
- Create: `chronic-disease-certification-standard-flash/SKILL.md`
- Create: `chronic-disease-certification-standard-flash/agents/openai.yaml`
- Move: `chronic-disease-certification-qc-flash/references/mode1-contract.md`
- Move: `chronic-disease-certification-qc-flash/assets/certification-template.html`
- Create: `chronic-disease-certification-standard-flash/references/output-checklist.md`

- [ ] **Step 1：建立目录并移动模式 1 专用资源**

```bash
mkdir -p chronic-disease-certification-standard-flash/{agents,assets,references}
git mv chronic-disease-certification-qc-flash/references/mode1-contract.md \
  chronic-disease-certification-standard-flash/references/mode1-contract.md
git mv chronic-disease-certification-qc-flash/assets/certification-template.html \
  chronic-disease-certification-standard-flash/assets/certification-template.html
```

- [ ] **Step 2：创建模式 1 专用入口**

`SKILL.md` 的 frontmatter 固定为：

```yaml
---
name: chronic-disease-certification-standard-flash
description: 用于需要以轻量方式将门诊慢特病政策文件或自然语言认定条件转为结构化认定标准，并生成业务可读离线 HTML 的场景。
---
```

正文保留原模式 1 的十步工作流、适用的通用约束以及安全与错误处理；删除模式路由、模式 2、组合请求和对模式 2 契约的说明。

- [ ] **Step 3：创建模式 1 UI 元数据**

```yaml
interface:
  display_name: "门诊慢特病认定标准 Flash"
  short_description: "轻量生成门诊慢特病结构化认定标准与可视化 HTML"
  default_prompt: "使用 $chronic-disease-certification-standard-flash 生成门诊慢特病结构化认定标准与可视化 HTML。"
```

- [ ] **Step 4：拆出模式 1 自检清单**

新清单保留原 `## 通用` 和 `## 模式 1` 的全部适用检查项，将标题改为 `# 认定标准 Flash 成果自检`，删除 `## 模式 2` 及其结论语义自检。

## Task 3：将原目录收窄为审核质控 Skill

**Files:**
- Modify: `chronic-disease-certification-qc-flash/SKILL.md`
- Modify: `chronic-disease-certification-qc-flash/agents/openai.yaml`
- Modify: `chronic-disease-certification-qc-flash/references/output-checklist.md`

- [ ] **Step 1：重写模式 2 专用入口**

frontmatter 固定为：

```yaml
---
name: chronic-disease-certification-qc-flash
description: 用于需要以轻量方式根据患者申请材料、门诊慢特病认定标准和原审核结果复核智能审核质量，并生成文本质控结果与离线 HTML 报告的场景。
---
```

正文保留原模式 2 的十一步工作流、适用的通用约束以及安全与错误处理；删除模式路由、模式 1、组合请求和对模式 1 契约的说明。

- [ ] **Step 2：更新模式 2 UI 元数据**

```yaml
interface:
  display_name: "门诊慢特病审核质控 Flash"
  short_description: "轻量复核患者材料、认定标准与智能审核结果"
  default_prompt: "使用 $chronic-disease-certification-qc-flash 复核患者材料、门诊慢特病认定标准与原审核结果。"
```

- [ ] **Step 3：收窄模式 2 自检清单**

保留原 `## 通用`、`## 模式 2` 和 `### 模式 2 结论语义自检（生成前必做）` 的全部适用检查项，将标题改为 `# 审核质控 Flash 成果自检`，删除 `## 模式 1`。

## Task 4：验证两个 Skill 的独立结构

**Files:**
- Verify: `chronic-disease-certification-standard-flash/`
- Verify: `chronic-disease-certification-qc-flash/`

- [ ] **Step 1：运行完整结构与引用断言**

```bash
python3 - <<'PY'
from pathlib import Path

root = Path(".")
expected = {
    "chronic-disease-certification-standard-flash": {
        "SKILL.md",
        "agents/openai.yaml",
        "assets/certification-template.html",
        "references/mode1-contract.md",
        "references/output-checklist.md",
    },
    "chronic-disease-certification-qc-flash": {
        "SKILL.md",
        "agents/openai.yaml",
        "assets/qc-report-template.html",
        "references/mode2-contract.md",
        "references/output-checklist.md",
    },
}
for name, wanted in expected.items():
    base = root / name
    actual = {
        str(path.relative_to(base))
        for path in base.rglob("*")
        if path.is_file()
    }
    assert actual == wanted, (name, actual ^ wanted)

standard_text = "\n".join(
    path.read_text(encoding="utf-8")
    for path in (root / "chronic-disease-certification-standard-flash").rglob("*")
    if path.is_file() and path.suffix in {".md", ".yaml"}
)
qc_text = "\n".join(
    path.read_text(encoding="utf-8")
    for path in (root / "chronic-disease-certification-qc-flash").rglob("*")
    if path.is_file() and path.suffix in {".md", ".yaml"}
)
assert "mode2-contract.md" not in standard_text
assert "qc-report-template.html" not in standard_text
assert "mode1-contract.md" not in qc_text
assert "certification-template.html" not in qc_text

for skill, template in (
    ("chronic-disease-certification-standard-flash", "assets/certification-template.html"),
    ("chronic-disease-certification-qc-flash", "assets/qc-report-template.html"),
):
    html = (root / skill / template).read_text(encoding="utf-8")
    assert html.count("__FLASH_DATA_JSON__") == 1, skill

print("split_structure=ok")
PY
```

Expected: PASS，并输出 `split_structure=ok`。

- [ ] **Step 2：分别运行 Skill 格式校验**

```bash
python3 /Users/Tristan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  chronic-disease-certification-standard-flash
python3 /Users/Tristan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  chronic-disease-certification-qc-flash
```

Expected: 两次均输出 `Skill is valid!`。

- [ ] **Step 3：检查文本与补丁质量**

```bash
rg -n '组合请求|根据用户请求选择模式|mode2-contract|qc-report-template' \
  chronic-disease-certification-standard-flash
rg -n '组合请求|根据用户请求选择模式|mode1-contract|certification-template' \
  chronic-disease-certification-qc-flash
git diff --check
```

Expected: 两次 `rg` 均无匹配，`git diff --check` 退出码为 0。

- [ ] **Step 4：提交双 Skill 拆分**

```bash
git add chronic-disease-certification-standard-flash \
  chronic-disease-certification-qc-flash
git commit -m "refactor: split flash skills by mode"
```

## Task 5：删除 acceptance 工程并最终验证

**Files:**
- Delete: `chronic-disease-certification-qc-flash-acceptance/`

- [ ] **Step 1：删除明确指定的验收工程**

```bash
git rm -r chronic-disease-certification-qc-flash-acceptance
```

- [ ] **Step 2：验证删除范围**

```bash
test ! -e chronic-disease-certification-qc-flash-acceptance
git status --short
```

Expected: `test` 退出码为 0；`git status` 只显示该验收工程的删除记录。

- [ ] **Step 3：重新运行 Task 4 的结构断言和两次 Skill 格式校验**

Expected: 结构断言输出 `split_structure=ok`，两次格式校验均输出 `Skill is valid!`。

- [ ] **Step 4：提交验收工程删除**

```bash
git add -u chronic-disease-certification-qc-flash-acceptance
git commit -m "chore: remove flash acceptance project"
```

- [ ] **Step 5：最终核对**

```bash
git diff --check HEAD~2..HEAD
git status --short --branch
git log -3 --oneline
```

Expected: 补丁检查通过，工作区干净，最近提交包含双 Skill 拆分和验收工程删除。
