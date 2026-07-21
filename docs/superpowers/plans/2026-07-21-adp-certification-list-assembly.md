# ADP certification_list 组装 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 ADP 检索分支输出确定性文档名，并将病种、规则库和逻辑树组装为完整 `certification_list`。

**Architecture:** 最高相关 DOC 选择节点在选择正文时同步输出 `documentName`。新增 Python 节点接收病种元信息、文档名、`ruleRepository` 和 `logicTopology`，校验引用并生成完整认证标准对象。

**Tech Stack:** Python 3 标准库（`json`、`datetime`）、腾讯智能体平台代码节点。

---

### Task 1: 扩展最高相关 DOC 节点

**Files:**

- Modify: `对接ADP知识库/将检索结果转为rule_repository/代码-提取相关性最高的知识库结果.py`
- Modify: `对接ADP知识库/将检索结果转为rule_repository/【代码出入参说明】代码-提取相关性最高的知识库结果.md`

- [ ] **Step 1: 写出 `DocName` 输出的失败验证**

构造最高置信度 DOC 带 `DocName` 的输入，断言当前结果缺少 `documentName`。

- [ ] **Step 2: 仅在选中 DOC 时同时保存文档名**

按以下顺序取名：`DocName` 非空字符串；否则从 `Content` 的多行首个 `文档名：` 或 `文档名:` 行提取；两者都没有时抛出 `ValueError`。返回：

```python
{
    "knowledgeContent": selected_content,
    "documentName": selected_document_name,
}
```

- [ ] **Step 3: 验证 DocName 优先、正文回退及无文档名失败**

使用对象、平台 `Output` 包装、`DocName` 为空但正文含文档名、以及两处均缺失四种输入断言结果。

- [ ] **Step 4: 更新出入参说明**

说明新增 `documentName: str` 输出、优先级和后续组装节点绑定。

### Task 2: 新增 certification_list 组装节点

**Files:**

- Create: `对接ADP知识库/将检索结果转为rule_repository/代码-组装certification_list.py`
- Create: `对接ADP知识库/将检索结果转为rule_repository/【代码出入参说明】代码-组装certification_list.md`

- [ ] **Step 1: 写出失败验证**

调用尚不存在的 `main(chronicDiseaseName, chronicDiseaseCode, documentName, ruleRepository, logicTopology)`，预期导入失败。

- [ ] **Step 2: 实现组装与校验**

实现必须：

```text
兼容 ruleRepository、logicTopology 为对象、数组或 JSON 字符串，并兼容其位于上游 Output 包装中。
要求病种名称、编码、文档名非空；规则库非空；逻辑树为对象。
递归校验 GROUP 的 AND/OR 和非空 children，RULE_REF 的 ruleCode 必须在规则库中。
version = "ADP-" + 去除 documentName 的 .md 后缀。
sourceFile = 第一条规则的非空 ruleSource，否则 "ADP知识库检索结果"。
createdAt = date.today().isoformat()；description 固定为“由 ADP 知识库检索结果生成”。
输出唯一顶层字段 certification_list。
```

- [ ] **Step 3: 验证完整输出与悬空引用失败**

用 `M07801`、`尿毒症透析-认定标准-v20260517.md`、两条规则和 AND 树断言版本、日期、来源和树均被保留；再传 `RULE_REF=99999` 断言 `ValueError`。

- [ ] **Step 4: 编写节点说明**

说明五个输入变量、`certification_list: obj` 输出 Schema、文档名到版本号映射、规则来源回退及下游审核节点绑定方式。

### Task 3: 更新 LLM 说明与最终验证

**Files:**

- Modify: `对接ADP知识库/将检索结果转为rule_repository/【LLM节点配置说明】将检索结果转为rule_repository.md`
- Modify/Create: Task 1 与 Task 2 的文件。

- [ ] **Step 1: 补充分支连线说明**

LLM 说明写明 `knowledgeContent` 继续供 LLM 使用，`documentName` 直接引用到最终组装节点，不需要传入 LLM。

- [ ] **Step 2: 运行新增节点验证与 py_compile**

运行两个节点的对象、JSON 字符串、平台包装、错误边界验证，并执行：

```bash
python3 -m py_compile '对接ADP知识库/将检索结果转为rule_repository/代码-提取相关性最高的知识库结果.py'
python3 -m py_compile '对接ADP知识库/将检索结果转为rule_repository/代码-组装certification_list.py'
```

- [ ] **Step 3: 运行现有 unittest 与格式检查**

运行两个现有 `unittest` 脚本和 `git diff --check`。

- [ ] **Step 4: 提交节点与说明**

```bash
git add '对接ADP知识库/将检索结果转为rule_repository'
git commit -m 'feat: assemble ADP certification list'
```

## Self-review

- Spec coverage：Task 1 传递确定性文档名；Task 2 组装完整标准并校验；Task 3 更新连线、验证和提交。
- Placeholder scan：没有 TODO、TBD 或未定义字段。
- Type consistency：`documentName` 由选择节点输出，版本组装节点消费；最终输出字段固定为 `certification_list`。
