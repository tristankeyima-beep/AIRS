# Skill Directory Naming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将六个可交付 Skill 调整为各自独立、业务名称清晰的一级目录。

**Architecture:** 只变更 `SKILLS` 内的父目录名称，保留每个 Skill 的英文技术目录名和内部文件。目录测试作为单一约束源，完整审核质控测试用于确认移动后行为不变。

**Tech Stack:** Git、Python `unittest`。

---

### Task 1: 固化一级目录约束

**Files:**
- Modify: `SKILLS/验证/test_skill_layout.py`
- Test: `SKILLS/验证/test_skill_layout.py`

- [x] **Step 1: 更新预期路径**

将五个 Flash 路径改为：

```python
EXPECTED_SKILLS = {
    "认定标准生成（Flash）/chronic-disease-certification-standard-flash",
    "审核质控（Flash）/chronic-disease-certification-qc-flash",
    "申请材料预检与补件清单（Flash）/chronic-disease-material-precheck-flash",
    "材料证据编目与归位（Flash）/chronic-disease-material-catalog-flash",
    "认定标准版本比对与影响分析（Flash）/chronic-disease-standard-version-impact-flash",
}
COMPLETE_QC_SKILL = "门诊慢特病认定标准与审核质控助手（完整版）/chronic-disease-certification-qc"
```

- [x] **Step 2: 运行测试确认旧结构不满足新约束**

Run: `python3 -m unittest SKILLS/验证/test_skill_layout.py -v`

Expected: FAIL，提示新目录尚不存在。

- [x] **Step 3: 提交测试变更**

```bash
git add SKILLS/验证/test_skill_layout.py
git commit -m "test: define descriptive skill directory layout"
```

### Task 2: 移动六个业务目录和开发验证目录

**Files:**
- Move: `SKILLS/完整版/` → `SKILLS/门诊慢特病认定标准与审核质控助手（完整版）/`
- Move: `SKILLS/认定标准/` → `SKILLS/认定标准生成（Flash）/`
- Move: `SKILLS/审核质控/` → `SKILLS/审核质控（Flash）/`
- Move: `SKILLS/材料管理/chronic-disease-material-precheck-flash/` → `SKILLS/申请材料预检与补件清单（Flash）/chronic-disease-material-precheck-flash/`
- Move: `SKILLS/材料管理/chronic-disease-material-catalog-flash/` → `SKILLS/材料证据编目与归位（Flash）/chronic-disease-material-catalog-flash/`
- Move: `SKILLS/版本管理/` → `SKILLS/认定标准版本比对与影响分析（Flash）/`
- Move: `SKILLS/验证/` → `SKILLS/开发验证（非 Skill）/`

- [x] **Step 1: 用 `git mv` 完成移动**

保留各 Skill 末级英文目录名；删除移动后为空的 `SKILLS/材料管理/`。

- [x] **Step 2: 运行目录测试**

Run: `python3 -m unittest 'SKILLS/开发验证（非 Skill）/test_skill_layout.py' -v`

Expected: PASS（3 项）。

- [x] **Step 3: 运行完整版审核质控回归**

Run: `python3 -m unittest discover -s 'SKILLS/门诊慢特病认定标准与审核质控助手（完整版）/chronic-disease-certification-qc/tests' -p 'test_*.py' -v`

Expected: PASS（216 项）。

- [x] **Step 4: 检查差异并提交**

```bash
git diff --check
git add SKILLS docs/superpowers/specs/2026-07-28-skill-directory-naming-design.md docs/superpowers/plans/2026-07-28-skill-directory-naming.md
git diff --cached --check
git commit -m "refactor: name each skill directory clearly"
```
