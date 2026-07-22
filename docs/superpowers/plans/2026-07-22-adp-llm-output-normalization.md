# 腾讯 ADP LLM 出参结构化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在智能审核迭代子流程的精解和逐条认定 LLM 后加入 Qwen2.5 格式化节点，并保持既有代码节点与下游变量契约不变。

**Architecture:** 两个新增 LLM 节点接收上游业务 LLM 的完整 Output 文本，使用腾讯 ADP 的结构化 Output Schema 生成稳定 JSON。原代码节点分别接收 `extraction_data` 或完整审核结论 Output，继续处理排序、容错、数组封装和下游变量输出。

**Tech Stack:** Markdown、腾讯 ADP LLM 节点、Qwen2.5、既有 Python 代码节点。

---

## 文件结构

- 创建 `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/1精解/02借助LLM将出参结构化处理/【LLM节点配置说明】借助LLM将出参结构化处理.md`：精解原始出参到 `extraction_data` 的 Qwen2.5 配置、Schema、提示词与案例。
- 移动 `.../1精解/02精解结果结构化/` 到 `.../1精解/03精解结果结构化/`：表达其位于新增 LLM 后；只更新其 Markdown 绑定说明，不修改 Python。
- 创建 `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/2逐条认定/02借助LLM将出参结构化处理/【LLM节点配置说明】借助LLM将出参结构化处理.md`：逐条认定原始出参到审核结论 JSON 的 Qwen2.5 配置、Schema、提示词与案例。
- 移动 `.../2逐条认定/02单条标准审核结果结构化/` 到 `.../2逐条认定/03单条标准审核结果结构化/`，并移动 `.../03提取推理过程/` 到 `.../04提取推理过程/`：表达新节点插入后的实际顺序；只更新代码节点绑定说明，不修改 Python。

### Task 1: 增加精解 Qwen2.5 格式化节点说明

**Files:**
- Create: `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/1精解/02借助LLM将出参结构化处理/【LLM节点配置说明】借助LLM将出参结构化处理.md`
- Move: `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/1精解/02精解结果结构化/` → `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/1精解/03精解结果结构化/`
- Modify: `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/1精解/03精解结果结构化/【代码出入参说明】代码-将精解结果结构化.md`

- [ ] **Step 1: 写入精解格式化节点的配置合同**

  在新建说明中规定模型为省局内已部署的 Qwen2.5；输入变量为 `raw_llm_output: str`，绑定 `01使用LLM精解.Output`；结构化 Output 为 `extraction_data: [obj]`。说明每个提取对象与 `results` 子对象的完整字段、类型和空值规则。

- [ ] **Step 2: 写入可复制的精解格式化提示词和完整案例**

  提示词要求模型只将 `raw_llm_output` 中可证实的数据映射至 Schema，不补造信息，去除 Markdown/说明文字，只输出 JSON。包含 `found=true` 的完整 `extraction_data` 案例和 `found=false, results=[]` 的空证据案例。

- [ ] **Step 3: 调整既有精解代码节点的顺序与绑定说明**

  移动目录为 `03精解结果结构化`。将其入参绑定从“1精解 LLM 的 Output”改为“02借助LLM将出参结构化处理.Output.extraction_data”，保留入参名 `extraction_data: str` 与出参 `extractionList`。

- [ ] **Step 4: 运行文档结构检查**

  Run:

  ```bash
  rg -n 'Qwen2\.5|raw_llm_output|extraction_data|03精解结果结构化' \
    '智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/1精解'
  ```

  Expected: 新说明含 Qwen2.5、输入变量和 Schema；代码说明只引用新增结构化节点。

### Task 2: 增加逐条认定 Qwen2.5 格式化节点说明

**Files:**
- Create: `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/2逐条认定/02借助LLM将出参结构化处理/【LLM节点配置说明】借助LLM将出参结构化处理.md`
- Move: `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/2逐条认定/02单条标准审核结果结构化/` → `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/2逐条认定/03单条标准审核结果结构化/`
- Move: `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/2逐条认定/03提取推理过程/` → `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/2逐条认定/04提取推理过程/`
- Modify: `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/2逐条认定/03单条标准审核结果结构化/【代码出入参说明】单条标准审核结果结构化.md`

- [ ] **Step 1: 写入逐条认定格式化节点的配置合同**

  在新建说明中规定模型为 Qwen2.5；输入变量 `raw_llm_output: str` 绑定 `01通过LLM逐条认定.Output`。结构化 Output 依次为 `ruleCode: str`、`ruleResult: str`、`ruleContent: str`、`suspicionList: [obj]`，其中来源字段为 `materialName`、`materialId`、`refContent`。

- [ ] **Step 2: 写入可复制的逐条认定格式化提示词和完整案例**

  提示词只转换已有结论和证据，不改变“通过/不通过”判断；当输出缺少有效结论时，固定输出“信息缺失”的不通过结构。包含完整不通过案例、通过案例以及 `suspicionList` 的空来源规则。

- [ ] **Step 3: 调整既有逐条认定代码节点的顺序与绑定说明**

  将审核结果代码节点移动为 `03单条标准审核结果结构化`，推理过程节点移动为 `04提取推理过程`。代码节点的 `ruleResult` 改绑定 `02借助LLM将出参结构化处理.Output`，而 `items` 继续绑定 `开始.iterator_selector`，以保留规则字段兜底。

- [ ] **Step 4: 运行文档结构检查**

  Run:

  ```bash
  rg -n 'Qwen2\.5|raw_llm_output|ruleCode|suspicionList|04提取推理过程' \
    '智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/2逐条认定'
  ```

  Expected: 新说明含模型、输入和完整 Schema；代码说明绑定新节点；推理过程目录编号为 04。

### Task 3: 验证交付物与既有代码兼容性

**Files:**
- Verify: `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/1精解/03精解结果结构化/代码-将精解结果结构化.py`
- Verify: `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/2逐条认定/03单条标准审核结果结构化/单条标准审核结果结构化.py`

- [ ] **Step 1: 执行 Python 语法检查**

  Run:

  ```bash
  python3 -m py_compile \
    '智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/1精解/03精解结果结构化/代码-将精解结果结构化.py' \
    '智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/2逐条认定/03单条标准审核结果结构化/单条标准审核结果结构化.py'
  ```

  Expected: 无输出，退出码为 0。

- [ ] **Step 2: 验证精解 Schema 可被既有代码消费**

  Run:

  ```bash
  python3 -c "import importlib.util; p='智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/1精解/03精解结果结构化/代码-将精解结果结构化.py'; s=importlib.util.spec_from_file_location('m',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.main({'extraction_data':'[{\\\"keywordCode\\\":\\\"1002001001\\\",\\\"found\\\":true,\\\"results\\\":[]}]'}))"
  ```

  Expected: 输出含 `extractionList` 的对象，且第一项 `keywordCode` 为 `1002001001`。

- [ ] **Step 3: 检查 Git 变更并提交**

  Run:

  ```bash
  git diff --check
  git status --short
  git add '智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj' docs/superpowers/plans/2026-07-22-adp-llm-output-normalization.md
  git commit -m 'docs: add ADP LLM output normalization nodes'
  ```

  Expected: 文档路径、节点顺序和绑定说明均已提交；既有 Python 文件只随目录移动，不改变内容。
