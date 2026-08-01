# 黄斑病变药品报销审核资料拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将黄斑病变的病种认定与眼内注射药品报销审核拆为两个独立、可追溯的版本化资料集。

**Architecture:** 原 `v20260728` 病种认定仅保留四类疾病范围（AMD、DME、CNV、RVO）的 OR 关系。新增 `药品报销审核/v20260728`，在一个资料集中呈现三种药品适应范围分支、共用首次支付条件和共用支数限额；材料缺失输出“无法判断／待补材料”，不直接判定不符合。年度限额采用业务确认的“每个年度最多支付4支”，Excel“第1年度最多5支”仅作来源留存。

**Tech Stack:** JSON 规则资料、Markdown 来源留存、HTML 可视化、`validate_certification.py`、`render_certification_html.py`。

---

### Task 1: 收敛黄斑病变病种认定资料

**Files:**
- Modify: `病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/v20260728/眼内注射治疗黄斑病变-certification_list-v20260728.json`
- Modify: `病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/v20260728/眼内注射治疗黄斑病变-认定标准-v20260728.md`
- Modify: `病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/v20260728/眼内注射治疗黄斑病变-认定标准可视化-v20260728.html`

- [ ] **Step 1: 写出结构校验断言**

```bash
python3 - <<'PY'
import json
p = '病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/v20260728/眼内注射治疗黄斑病变-certification_list-v20260728.json'
d = json.load(open(p))
assert [r['ruleCode'] for r in d['ruleRepository']] == ['05001', '05002', '05003', '05004']
assert d['logicTopology']['operator'] == 'OR'
PY
```

- [ ] **Step 2: 运行断言，确认当前资料仍含支付影像规则而失败**

Run: 上述命令。
Expected: `AssertionError`，因为当前资料还含 `05005`、`05006`、`05007`。

- [ ] **Step 3: 修改 JSON 和 Markdown**

删除 `05005`、`05006`、`05007` 及其 AND 逻辑组；将根逻辑改为 `05001`–`05004` 的 OR。Markdown 明确说明：首次申请影像、处方机构、视力阈值、事前审核和支数限额已迁至“药品报销审核”。

- [ ] **Step 4: 运行断言和标准校验**

Run:

```bash
python3 - <<'PY'
import json
p = '病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/v20260728/眼内注射治疗黄斑病变-certification_list-v20260728.json'
d = json.load(open(p))
assert [r['ruleCode'] for r in d['ruleRepository']] == ['05001', '05002', '05003', '05004']
assert d['logicTopology']['operator'] == 'OR'
PY
python3 'SKILLS/门诊慢特病认定标准与审核质控助手（完整版）/chronic-disease-certification-qc/scripts/validate_certification.py' validate '病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/v20260728/眼内注射治疗黄斑病变-certification_list-v20260728.json'
```

Expected: 断言通过，验证脚本报告通过。

- [ ] **Step 5: 重新生成 HTML**

Run:

```bash
python3 'SKILLS/门诊慢特病认定标准与审核质控助手（完整版）/chronic-disease-certification-qc/scripts/render_certification_html.py' '病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/v20260728/眼内注射治疗黄斑病变-certification_list-v20260728.json' '病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/v20260728/眼内注射治疗黄斑病变-认定标准可视化-v20260728.html'
```

### Task 2: 新建统一的药品报销审核版本

**Files:**
- Create: `病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/药品报销审核/v20260728/黄斑病变眼内注射药品-报销审核规则-v20260728.json`
- Create: `病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/药品报销审核/v20260728/黄斑病变眼内注射药品-报销审核规则-v20260728.md`
- Create: `病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/药品报销审核/v20260728/黄斑病变眼内注射药品-报销审核规则可视化-v20260728.html`

- [ ] **Step 1: 写出资料结构断言**

```bash
python3 - <<'PY'
import json
p = '病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/药品报销审核/v20260728/黄斑病变眼内注射药品-报销审核规则-v20260728.json'
d = json.load(open(p))
codes = {r['ruleCode'] for r in d['ruleRepository']}
assert {'P05001', 'P05002', 'P05003', 'P05004', 'P05005', 'P05006', 'P05007', 'P05008'} == codes
PY
```

- [ ] **Step 2: 运行断言，确认新增资料尚不存在而失败**

Run: 上述命令。
Expected: `FileNotFoundError`。

- [ ] **Step 3: 创建统一规则资料**

建立三药品适应范围分支：雷珠单抗（AMD/DME/CNV/RVO）、康柏西普（AMD/DME/CNV/RVO，RVO注明 BRVO/CRVO）、阿柏西普（AMD/DME）。建立共用处方机构、首次处方视力、事前审核与首次影像、每眼累计／首年度限额和合并计数规则；注明材料缺失结果为“无法判断／待补材料”。

- [ ] **Step 4: 运行结构断言并进行 JSON 解析校验**

Run:

```bash
python3 - <<'PY'
import json
p = '病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/药品报销审核/v20260728/黄斑病变眼内注射药品-报销审核规则-v20260728.json'
d = json.load(open(p))
codes = {r['ruleCode'] for r in d['ruleRepository']}
assert {'P05001', 'P05002', 'P05003', 'P05004', 'P05005', 'P05006', 'P05007', 'P05008'} == codes
print('payment-rule structure passed')
PY
```

Expected: `payment-rule structure passed`。

- [ ] **Step 5: 生成并人工核验可视化**

生成 HTML，确认页面按“药品适应范围”“共用支付条件”“支付限额和合并计数”“审核结论”分区呈现，且不把材料缺失显示为“不符合”。

### Task 3: 交叉核验与提交

**Files:**
- Verify: Task 1 与 Task 2 所列全部文件

- [ ] **Step 1: 交叉检索支付要素归属**

Run:

```bash
rg -n '血管造影|OCT血管成像|基线矫正视力|每眼累计|第1年度' '病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/药品报销审核/v20260728'
python3 - <<'PY'
import json
p = '病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变/v20260728/眼内注射治疗黄斑病变-certification_list-v20260728.json'
d = json.load(open(p))
text = json.dumps(d, ensure_ascii=False)
for term in ('血管造影', '基线矫正视力', '每眼累计', '第1年度'):
    assert term not in text, term
PY
```

Expected: 支付要素在 `药品报销审核/v20260728` 可检索；病种认定 JSON 的活动规则和逻辑中不存在这些支付要素。病种认定 Markdown 可保留迁移说明，但不复述支付规则正文。

- [ ] **Step 2: 检查工作区改动范围**

Run:

```bash
git status --short -- '病症认定标准清单/省局项目/05_眼内注射治疗黄斑病变' 'docs/superpowers/plans/2026-07-28-macular-drug-reimbursement-audit.md'
```

Expected: 仅包含本计划所列资料和计划文件。
