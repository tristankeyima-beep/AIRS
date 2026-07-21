# ADP 最高相关知识提取节点 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 LLM 前筛出 ADP 检索结果中相关性最高的有效 DOC，仅输出其正文 `knowledgeContent`。

**Architecture:** Python 节点统一解析对象或 JSON 文本，过滤有效 DOC 并稳定地按 `Confidence` 选最高项。LLM 配置改为接收已筛选的字符串正文，不再处理检索列表。

**Tech Stack:** Python 3 标准库（`json`）、腾讯智能体平台代码节点。

---

## File structure

- Create: `对接ADP知识库/将检索结果转为rule_repository/代码-提取相关性最高的知识库结果.py` — 选择最高相关有效 DOC 的实现。
- Create: `对接ADP知识库/将检索结果转为rule_repository/【代码出入参说明】代码-提取相关性最高的知识库结果.md` — 平台变量契约、示例和错误说明。
- Modify: `对接ADP知识库/将检索结果转为rule_repository/【LLM节点配置说明】将检索结果转为rule_repository.md` — 输入变量和提示词改用 `knowledgeContent`。

### Task 1: 实现并验证最高相关 DOC 选择节点

**Files:**

- Create: `对接ADP知识库/将检索结果转为rule_repository/代码-提取相关性最高的知识库结果.py`

- [ ] **Step 1: 写出失败的导入验证**

```bash
python3 - <<'PY'
import importlib.util
from pathlib import Path
path = Path('对接ADP知识库/将检索结果转为rule_repository/代码-提取相关性最高的知识库结果.py')
spec = importlib.util.spec_from_file_location('node', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PY
```

预期：目标文件尚不存在而失败。

- [ ] **Step 2: 实现节点函数**

写入 `main(knowledge_result=None, **kwargs) -> dict`。实现必须：

```text
接受对象、JSON 字符串，及包含 knowledge_result 的平台整体参数对象。
要求顶层对象的 KnowledgeList 为数组。
只保留 KnowledgeType=DOC、Content 为非空字符串且 Confidence 可转 float 的条目。
以 max(enumerate(...), key=(Confidence, -原始位置)) 选择最高分，确保同分选最先出现的条目。
无有效候选、JSON 无法解析或顶层结构错误时抛 ValueError。
仅返回 {"knowledgeContent": 选中条目的 Content}。
```

- [ ] **Step 3: 执行对象、字符串、QA 和同分验证**

```bash
python3 - <<'PY'
import importlib.util
import json
from pathlib import Path
path = Path('对接ADP知识库/将检索结果转为rule_repository/代码-提取相关性最高的知识库结果.py')
spec = importlib.util.spec_from_file_location('node', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

payload = {'KnowledgeList': [
    {'KnowledgeType': 'QA', 'Content': '不得选中', 'Confidence': 0.99},
    {'KnowledgeType': 'DOC', 'Content': '第二条 DOC', 'Confidence': 0.7},
    {'KnowledgeType': 'DOC', 'Content': '第一条 DOC', 'Confidence': 0.9},
]}
assert module.main(payload) == {'knowledgeContent': '第一条 DOC'}
assert module.main(json.dumps(payload, ensure_ascii=False)) == {'knowledgeContent': '第一条 DOC'}
tie = {'KnowledgeList': [
    {'KnowledgeType': 'DOC', 'Content': '同分第一条', 'Confidence': 0.8},
    {'KnowledgeType': 'DOC', 'Content': '同分第二条', 'Confidence': 0.8},
]}
assert module.main(tie) == {'knowledgeContent': '同分第一条'}
for invalid, message in [
    ({'KnowledgeList': []}, '未找到'),
    ({'KnowledgeList': {}}, '必须是数组'),
    ('not-json', '合法 JSON'),
]:
    try:
        module.main(invalid)
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError('expected ValueError')
PY
```

预期：退出码为 0，无输出。

### Task 2: 更新 LLM 契约与编写节点文档

**Files:**

- Create: `对接ADP知识库/将检索结果转为rule_repository/【代码出入参说明】代码-提取相关性最高的知识库结果.md`
- Modify: `对接ADP知识库/将检索结果转为rule_repository/【LLM节点配置说明】将检索结果转为rule_repository.md`

- [ ] **Step 1: 编写前置节点出入参说明**

说明 `knowledge_result: obj` 输入、`knowledgeContent: str` 输出、最高 DOC 选择规则、同分顺序、忽略 QA/空内容/无效置信度及错误行为。用 `output (1).json` 的尿毒症 DOC 作为测试示例。

- [ ] **Step 2: 将 LLM 输入改为 knowledgeContent**

将输入表中的 `knowledge_result: obj` 改为 `knowledgeContent: str`，绑定前置代码节点输出；提示词中的“知识库检索结果”改为“已筛选的知识库 DOC 正文”，并删除 LLM 自行筛选 DOC、忽略 QA、去重多 DOC 的规则。保留病种名称、病种编码和全部通用规则/逻辑树约束。

### Task 3: 最终验证与提交

**Files:**

- Create: `对接ADP知识库/将检索结果转为rule_repository/代码-提取相关性最高的知识库结果.py`
- Create: `对接ADP知识库/将检索结果转为rule_repository/【代码出入参说明】代码-提取相关性最高的知识库结果.md`
- Modify: `对接ADP知识库/将检索结果转为rule_repository/【LLM节点配置说明】将检索结果转为rule_repository.md`

- [ ] **Step 1: 运行 Task 1 的验证命令和 py_compile**

```bash
python3 -m py_compile '对接ADP知识库/将检索结果转为rule_repository/代码-提取相关性最高的知识库结果.py'
```

预期：全部退出码为 0。

- [ ] **Step 2: 检查变更范围与字段迁移**

```bash
git diff --check
rg -n 'knowledgeContent|knowledge_result' '对接ADP知识库/将检索结果转为rule_repository'
```

预期：前置节点使用 `knowledge_result`；LLM 说明只使用 `knowledgeContent`；格式检查无输出。

- [ ] **Step 3: 提交交付文件**

```bash
git add '对接ADP知识库/将检索结果转为rule_repository'
git commit -m 'feat: select top ADP knowledge result before LLM'
```

预期：提交只包含新增节点、其说明及更新后的 LLM 说明。

## Self-review

- Spec coverage：Task 1 覆盖选择算法和失败边界；Task 2 覆盖前置节点及 LLM 契约；Task 3 覆盖验证与提交。
- Placeholder scan：没有 TODO、TBD 或未定义字段。
- Type consistency：前置输入是 `knowledge_result`，其唯一输出为 `knowledgeContent`；LLM 只接收 `knowledgeContent`。
