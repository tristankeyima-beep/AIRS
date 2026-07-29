# ADP Async Workflow Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个通过 TC3 签名调用 `knowledge_qa` 异步工作流的慢病知识库 Skill。

**Architecture:** 保留现有 SSE Skill，新增独立目录。Python 标准库客户端先调用 `CreateWorkflowRun`，再轮询 `DescribeWorkflowRun`，把工作流输出转换为稳定 JSON；内网只需要修改一个 JSON 配置文件。

**Tech Stack:** Python 3 标准库、`unittest`、Codex Skill Markdown/JSON

---

### Task 1: 建立失败测试和配置契约

**Files:**
- Create: `SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/tests/test_query_adp_workflow.py`
- Create: `SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/config/adp-config.template.json`

- [ ] **Step 1: 编写失败测试**

覆盖配置必填字段、TC3 签名确定性、创建工作流请求、轮询成功、ADP 错误、失败状态和超时。

- [ ] **Step 2: 验证测试先失败**

Run:

```bash
python3 -m unittest discover -s "SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/tests" -v
```

Expected: FAIL，因为 `query_adp_workflow.py` 尚不存在。

- [ ] **Step 3: 提交测试基线**

```bash
git add "SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/tests" \
  "SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/config"
git commit -m "test: define async ADP workflow contract"
```

### Task 2: 实现 TC3 工作流客户端

**Files:**
- Create: `SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/scripts/query_adp_workflow.py`

- [ ] **Step 1: 实现配置读取和 TC3 签名**

使用 `hashlib`、`hmac`、`urllib` 和 UTC 日期生成 `Authorization`、`X-TC-Action`、`X-TC-Version`、`X-TC-Timestamp`、`X-TC-Region`。

- [ ] **Step 2: 实现创建和轮询**

`CreateWorkflowRun` 请求体发送 `AppBizId`、`RunEnv`、`Query`、`VisitorId`；读取 `WorkflowRunId` 后调用 `DescribeWorkflowRun`，直到 `State == 2`、失败状态或超时。

- [ ] **Step 3: 实现稳定输出和 CLI**

成功输出 `ok/query/answer/workflow/request_id`；失败输出 `ok/error`，支持 `--config` 和 `--query-stdin`。

- [ ] **Step 4: 运行测试**

Run:

```bash
python3 -W error::ResourceWarning -m unittest discover \
  -s "SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/tests" -v
```

Expected: PASS。

- [ ] **Step 5: 提交实现**

```bash
git add "SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/scripts" \
  "SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/tests"
git commit -m "feat: call ADP async workflow API"
```

### Task 3: 完成 Skill 指引和最小验收

**Files:**
- Create: `SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/SKILL.md`
- Create: `SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/agents/openai.yaml`
- Create: `SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/references/internal-deployment.md`
- Modify: `.gitignore`

- [ ] **Step 1: 编写 Qwen 可理解的调用说明**

明确触发范围、固定命令、标准输入方式、不可信证据处理和错误分类。

- [ ] **Step 2: 编写小白配置说明**

说明复制模板为 `adp-config.json`，填写 `api_host`、`app_id`、`secret_id`、`secret_key`，并解释 `run_env`。

- [ ] **Step 3: 忽略真实配置**

在 `.gitignore` 中加入新 Skill 的 `config/adp-config.json` 精确路径。

- [ ] **Step 4: 完整验证**

Run:

```bash
python3 -W error::ResourceWarning -m unittest discover \
  -s "SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/tests" -v
python3 -m py_compile \
  "SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow/scripts/query_adp_workflow.py"
git diff --check
```

Expected: 全部通过，仓库中没有真实内网密钥。

- [ ] **Step 5: 提交文档**

```bash
git add .gitignore "SKILLS/慢病知识库异步工作流/chronic-disease-knowledge-workflow"
git commit -m "docs: add async ADP workflow skill"
```
