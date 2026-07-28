# Chronic Disease Knowledge Retrieval Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a simple Codex Skill that recognizes chronic-disease knowledge questions, calls the published Tencent ADP `knowledge_qa` application over HTTP SSE, and returns model-friendly JSON for subsequent reasoning.

**Architecture:** Keep the runtime in one standard-library Python file. Read deployment differences from one JSON configuration file and read AppKey only from an environment variable. Parse legacy ADP SSE events into a stable result containing the final answer, knowledge/reference metadata, workflow outputs, and request metadata.

**Tech Stack:** Codex Skill markdown, Python 3 standard library (`argparse`, `json`, `os`, `urllib.request`, `uuid`), `unittest`, Tencent ADP HTTP SSE.

---

## File map

- Create `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/SKILL.md`: triggering conditions and model-facing workflow.
- Create `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/agents/openai.yaml`: UI metadata.
- Create `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/config/adp-config.template.json`: cloud/intranet replacement template without secrets.
- Create `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/references/internal-deployment.md`: four-step deployment instructions for Qwen 3.6-27B.
- Create `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/scripts/query_adp.py`: request construction, SSE parsing, result aggregation, CLI.
- Create `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py`: configuration, request, SSE, aggregation, error and redaction tests.

Do not modify existing Skills or unrelated untracked files.

### Task 1: Record baseline behavior before the Skill exists

**Files:**
- Read: `docs/superpowers/specs/2026-07-28-chronic-disease-knowledge-retrieval-skill-design.md`
- Do not create runtime files in this task.

- [ ] **Step 1: Run a baseline trigger scenario without the new Skill**

Use a fresh subagent with no new Skill context:

```text
用户问：请查一下尿毒症透析的门诊慢特病认定标准，并给出知识库依据。
请完成用户请求。不要假设任何尚未安装的新 Skill。
```

Expected baseline failure: the agent cannot call the intended ADP application, guesses from general knowledge, or asks for an unavailable integration.

- [ ] **Step 2: Run a baseline configuration scenario**

Use a fresh subagent:

```text
你收到一个调用腾讯 ADP 知识问答应用的 Skill 文件夹，但只知道云端和内网地址不同。
说明你会如何找到要替换的配置、如何提供 AppKey、如何执行一条查询。
```

Expected baseline failure: instructions are invented, scattered, or require understanding SDK internals.

- [ ] **Step 3: Record the exact failure patterns in the implementation notes**

Record only a concise local working note for the current execution. The final `SKILL.md` must directly prevent the observed failures: skipping retrieval, inventing sources, placing AppKey in files, or editing Python for intranet deployment.

### Task 2: Initialize the Skill scaffold

**Files:**
- Create: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/`

- [ ] **Step 1: Run the official Skill initializer**

```bash
python /Users/Tristan/.codex/skills/.system/skill-creator/scripts/init_skill.py \
  chronic-disease-knowledge-retrieval \
  --path 'SKILLS/慢病知识库检索' \
  --resources scripts,references \
  --interface 'display_name=慢病知识库检索' \
  --interface 'short_description=检索门诊慢特病认定标准、专家共识和临床指南' \
  --interface 'default_prompt=使用 $chronic-disease-knowledge-retrieval 查询慢病知识库，并根据检索依据继续处理我的问题。'
```

Expected: the Skill directory, template `SKILL.md`, and `agents/openai.yaml` are created.

- [ ] **Step 2: Create only the required additional directories**

```bash
mkdir -p \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/config' \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests'
```

Expected: `config/` and `tests/` exist. Do not add README or package boilerplate.

- [ ] **Step 3: Commit the scaffold**

```bash
git add -- 'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval'
git commit -m 'feat: scaffold chronic disease knowledge skill'
```

### Task 3: Write failing unit tests for the Python boundary

**Files:**
- Create: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py`
- Test: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py`

- [ ] **Step 1: Add tests for request construction and SSE parsing**

The test imports `scripts/query_adp.py` by file path and covers these exact contracts:

```python
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "query_adp.py"
SPEC = importlib.util.spec_from_file_location("query_adp", SCRIPT_PATH)
query_adp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(query_adp)


class QueryAdpTests(unittest.TestCase):
    def test_build_request_uses_query_and_environment_app_key(self):
        config = {
            "app_key_env": "ADP_APP_KEY",
            "streaming_throttle": 10,
            "workflow_status": "enable",
            "search_network": "disable",
        }
        with patch.dict(os.environ, {"ADP_APP_KEY": "test-only-key"}, clear=True):
            body = query_adp.build_request(config, "查询尿毒症透析认定标准")
        self.assertEqual(body["content"], "查询尿毒症透析认定标准")
        self.assertEqual(body["bot_app_key"], "test-only-key")
        self.assertEqual(body["session_id"], body["visitor_biz_id"])
        self.assertTrue(body["request_id"])
        self.assertEqual(body["workflow_status"], "enable")

    def test_missing_app_key_names_environment_variable_without_leaking_value(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(query_adp.ConfigError, "ADP_APP_KEY"):
                query_adp.build_request({"app_key_env": "ADP_APP_KEY"}, "问题")

    def test_read_sse_accepts_legacy_array_events(self):
        stream = io.BytesIO(
            b'data: [\"reply\", {\"type\":\"reply\",\"payload\":{\"content\":\"final\",'
            b'\"is_final\":true,\"request_id\":\"req-1\"}}]\\n\\n'
            b'data: [\"reference\", {\"type\":\"reference\",\"payload\":{\"references\":'
            b'[{\"type\":2,\"doc_name\":\"standard.docx\",\"name\":\"standard\",\"url\":\"\"}]}}]\\n\\n'
        )
        events = list(query_adp.read_sse(stream))
        self.assertEqual([item[0] for item in events], ["reply", "reference"])

    def test_collect_result_keeps_answer_reference_and_workflow_separate(self):
        events = [
            (
                "reply",
                {
                    "payload": {
                        "content": "认定标准回答",
                        "is_final": True,
                        "request_id": "req-1",
                        "session_id": "session-1",
                        "knowledge": [{"id": "seg-1", "type": 2}],
                        "work_flow": {
                            "workflow_name": "慢病检索",
                            "workflow_run_id": "run-1",
                            "outputs": ["检索输出"],
                        },
                    }
                },
            ),
            (
                "reference",
                {
                    "payload": {
                        "references": [
                            {
                                "type": 2,
                                "doc_name": "尿毒症透析标准.docx",
                                "name": "尿毒症透析标准",
                                "url": "",
                            }
                        ]
                    }
                },
            ),
            ("token_stat", {"payload": {"status_summary": "success"}}),
        ]
        result = query_adp.collect_result("问题", events)
        self.assertTrue(result["ok"])
        self.assertEqual(result["answer"], "认定标准回答")
        self.assertEqual(result["knowledge"][0]["title"], "尿毒症透析标准.docx")
        self.assertEqual(result["workflow"]["run_id"], "run-1")
        self.assertEqual(result["workflow"]["outputs"], ["检索输出"])
        self.assertEqual(result["meta"]["request_id"], "req-1")

    def test_collect_result_rejects_error_and_empty_answer(self):
        with self.assertRaises(query_adp.AdPError):
            query_adp.collect_result(
                "问题",
                [("error", {"payload": {"message": "认证失败"}})],
            )
        with self.assertRaises(query_adp.AdPError):
            query_adp.collect_result("问题", [("token_stat", {"payload": {"status_summary": "success"}})])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python -m unittest \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py' \
  -v
```

Expected: FAIL because `scripts/query_adp.py` does not exist or required functions are missing.

- [ ] **Step 3: Commit the failing tests**

```bash
git add -- 'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py'
git commit -m 'test: define ADP SSE query contract'
```

### Task 4: Implement the simple standard-library ADP client

**Files:**
- Create: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/scripts/query_adp.py`
- Test: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py`

- [ ] **Step 1: Implement configuration and request construction**

Implement:

```python
class ConfigError(Exception):
    pass


class AdPError(Exception):
    pass


def load_config(path):
    with open(path, "r", encoding="utf-8") as file:
        config = json.load(file)
    for name in ("chat_url", "app_key_env"):
        if not isinstance(config.get(name), str) or not config[name].strip():
            raise ConfigError("配置缺少有效字段: " + name)
    return config


def build_request(config, query):
    query = query.strip()
    if not query:
        raise ConfigError("查询内容不能为空")
    env_name = config.get("app_key_env", "ADP_APP_KEY")
    app_key = os.environ.get(env_name, "").strip()
    if not app_key:
        raise ConfigError("请设置环境变量: " + env_name)
    session_id = str(uuid.uuid4())
    return {
        "request_id": str(uuid.uuid4()),
        "session_id": session_id,
        "visitor_biz_id": session_id,
        "bot_app_key": app_key,
        "content": query,
        "incremental": False,
        "streaming_throttle": int(config.get("streaming_throttle", 10)),
        "visitor_labels": [],
        "custom_variables": {},
        "search_network": config.get("search_network", "disable"),
        "stream": "enable",
        "workflow_status": config.get("workflow_status", "enable"),
    }
```

- [ ] **Step 2: Implement SSE parsing**

`read_sse(stream)` must:

- decode UTF-8;
- ignore blank lines and comment lines beginning with `:`;
- collect only `data:` lines;
- parse legacy arrays shaped as `[event_name, event_object]`;
- also accept objects containing `type` and `payload`;
- raise `AdPError("SSE 事件不是有效 JSON")` for malformed JSON.

Use a small `flush_data(lines)` helper instead of classes or async code.

- [ ] **Step 3: Implement stable result aggregation**

`collect_result(query, events)` must:

- keep the latest non-empty `reply.payload.content`;
- copy `request_id` and `session_id` when present;
- map reference type `1` to `qa`, type `2` to `document`, and type `4` to `web`;
- use `doc_name` first, then `name`, for `knowledge[].title`;
- keep `content` empty when the event does not supply source text;
- merge workflow name, run ID, and outputs from `reply.payload.work_flow`;
- treat `error` events or `token_stat.status_summary == "failed"` as `AdPError`;
- reject a completed stream with no final answer;
- never include `bot_app_key` or environment values in the result.

- [ ] **Step 4: Implement HTTP and CLI**

`query_adp(config, query)` must POST UTF-8 JSON using `urllib.request.Request`, set `Content-Type: application/json` and `Accept: text/event-stream`, then pass the response to `read_sse()` and `collect_result()`.

`main()` must accept:

```text
--config PATH
--query TEXT
--debug
```

Default behavior prints one UTF-8 JSON object to standard output. Known configuration, HTTP, timeout, SSE and empty-answer failures print:

```json
{"ok": false, "error_type": "config|auth|network|timeout|sse|empty_result", "message": "不含密钥的中文提示"}
```

and exit with status `1`. `--debug` may print event names to standard error, but never request bodies, headers, environment contents, or full exception objects that can contain URLs with secrets.

- [ ] **Step 5: Run the unit tests and verify GREEN**

Run:

```bash
python -m unittest \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py' \
  -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit the client**

```bash
git add -- \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/scripts/query_adp.py' \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py'
git commit -m 'feat: query ADP knowledge app over SSE'
```

### Task 5: Write the Skill, template, and intranet guide

**Files:**
- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/SKILL.md`
- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/agents/openai.yaml`
- Create: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/config/adp-config.template.json`
- Create: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/references/internal-deployment.md`

- [ ] **Step 1: Replace the generated `SKILL.md`**

Use only `name` and `description` in frontmatter. The description must mention concrete triggers: 门诊慢特病、慢病知识库、认定标准、准入条件、专家共识、临床指南、诊疗规范、知识依据、来源和版本。

The body must use short numbered instructions:

1. Determine whether external knowledge is required.
2. Read `references/internal-deployment.md` only for configuration or deployment work.
3. Run `scripts/query_adp.py` once with the original user question.
4. Read `answer`, `knowledge`, and `workflow` separately.
5. Continue the user's requested analysis using returned evidence.
6. Never invent missing sources or silently answer from memory when retrieval failed.
7. State that retrieval evidence is for business discussion and not a patient diagnosis or final医保 qualification.

- [ ] **Step 2: Add the secret-free configuration template**

Create exactly:

```json
{
  "chat_url": "https://替换为实际的ADP-SSE地址",
  "app_key_env": "ADP_APP_KEY",
  "timeout_seconds": 120,
  "streaming_throttle": 10,
  "workflow_status": "enable",
  "search_network": "disable"
}
```

- [ ] **Step 3: Write the Qwen-friendly intranet guide**

Keep the guide under 120 lines and use four sections:

1. 复制模板为 `config/adp-config.json`;
2. 把 `chat_url` 改为内网 SSE 地址;
3. 在系统环境中设置模板指定的 `ADP_APP_KEY`;
4. 运行一条自检命令并检查 `ok=true`.

Explicitly state:

- do not paste AppKey into JSON, Python, SKILL.md, logs, or chat;
- if intranet field names differ, compare with the supplied V3.4.1.0 interface document and edit only `build_request()`;
- do not add SecretId/SecretKey for this SSE scheme;
- preserve UTF-8.

- [ ] **Step 4: Regenerate and verify `agents/openai.yaml`**

Run:

```bash
python /Users/Tristan/.codex/skills/.system/skill-creator/scripts/generate_openai_yaml.py \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval' \
  --interface 'display_name=慢病知识库检索' \
  --interface 'short_description=检索门诊慢特病认定标准、专家共识和临床指南' \
  --interface 'default_prompt=使用 $chronic-disease-knowledge-retrieval 查询慢病知识库，并根据检索依据继续处理我的问题。'
```

Expected: metadata matches `SKILL.md` and contains no credentials.

- [ ] **Step 5: Commit the Skill instructions**

```bash
git add -- 'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval'
git commit -m 'docs: teach models to retrieve chronic disease knowledge'
```

### Task 6: Validate locally before any cloud call

**Files:**
- Test: complete Skill directory.

- [ ] **Step 1: Run Skill validation**

```bash
python /Users/Tristan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval'
```

Expected: validation succeeds.

- [ ] **Step 2: Run unit and repository layout tests**

```bash
python -m unittest \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py' \
  'SKILLS/开发验证（非 Skill）/test_skill_layout.py' \
  -v
```

Expected: all tests PASS.

- [ ] **Step 3: Verify missing-secret behavior**

Copy the template to a temporary directory, point `chat_url` to the cloud endpoint, leave `ADP_APP_KEY` unset, and run the CLI.

Expected: exit `1`, JSON `ok=false`, message names `ADP_APP_KEY`, and no network request occurs.

- [ ] **Step 4: Scan for supplied credential values and secret-shaped literals**

Search the new Skill and staged diff for the exact values supplied by the user and for suspicious `AKID`, long AppKey, Authorization, or SecretKey literals.

Expected: no real credentials appear. Variable names and explanatory words are allowed.

### Task 7: Run the cloud minimum closed loop

**Files:**
- Create only a temporary runtime config outside the Skill, then delete it after the test.
- Do not commit runtime configuration or output containing sensitive identifiers.

- [ ] **Step 1: Prepare temporary cloud configuration**

Use:

```json
{
  "chat_url": "https://wss.lke.cloud.tencent.com/v1/qbot/chat/sse",
  "app_key_env": "ADP_APP_KEY",
  "timeout_seconds": 120,
  "streaming_throttle": 10,
  "workflow_status": "enable",
  "search_network": "disable"
}
```

Inject the user-supplied cloud AppKey only into the child process environment. Do not export it globally, write it to shell history, or echo it.

- [ ] **Step 2: Run one narrow knowledge query**

Query:

```text
尿毒症透析的门诊慢特病认定标准是什么？请给出知识库依据。
```

Expected:

- HTTP connection succeeds;
- at least one `reply` event is received;
- output is valid JSON with `ok=true`;
- `answer` is non-empty;
- `knowledge` or `workflow.outputs` contains retrievable provenance when the application returns it;
- no credentials appear in stdout or stderr.

- [ ] **Step 3: Diagnose before changing code if the call fails**

Classify the failure as endpoint, AppKey, published-app status, SSE schema, timeout, or empty knowledge. Do not switch to `CreateWorkflowRun` or add SecretId/SecretKey. Update the parser only when raw event shape proves a compatibility gap, then add a failing fixture before the fix.

### Task 8: Expand to the full cloud closed loop

**Files:**
- Modify tests only if real SSE reveals a schema variant.
- Do not write real response content into committed fixtures unless it is non-sensitive and necessary.

- [ ] **Step 1: Test three query classes**

Run:

```text
1. 尿毒症透析的门诊慢特病认定标准是什么？请给出知识库依据。
2. 请检索慢病知识库中与白血病相关的专家共识或临床指南，并说明来源。
3. 请依据知识库解释器官移植后抗排异治疗的认定要点，并区分标准依据和业务解读。
```

If a named disease has no result, replace only that test query with another disease confirmed by the first response or repository context. Do not weaken the three categories: recognition standard, consensus/guideline, and evidence-based interpretation.

- [ ] **Step 2: Verify model-facing output quality**

For each result verify:

- original query preserved;
- final answer not mixed into reference metadata;
- each returned title and URL copied exactly;
- missing source content remains empty rather than invented;
- workflow outputs remain an array;
- Chinese UTF-8 is readable;
- only one ADP call is made per question.

- [ ] **Step 3: Forward-test the completed Skill**

Use a fresh subagent with only the Skill path and one natural-language question:

```text
Use $chronic-disease-knowledge-retrieval at
SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval
to answer: 请查找糖尿病门诊慢特病认定所依据的标准，并概括业务讨论时需要注意的条件。
```

Expected: it loads the Skill, calls the script once, uses returned evidence, distinguishes retrieval from interpretation, and does not invent missing sources.

- [ ] **Step 4: Forward-test intranet configuration comprehension**

Use a fresh subagent:

```text
阅读该 Skill。现在要从云端切换到省局内网，请只说明需要修改哪些配置、如何提供 AppKey、如何自检。不要改程序。
```

Expected: four simple steps, no SDK explanation, no SecretId/SecretKey, and no suggestion to paste AppKey into files.

### Task 9: Final verification and handoff

**Files:**
- Verify all new Skill files.

- [ ] **Step 1: Run the complete verification set**

```bash
python -m unittest \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py' \
  'SKILLS/开发验证（非 Skill）/test_skill_layout.py' \
  -v
python /Users/Tristan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval'
git diff --check
```

Expected: tests and validation pass; `git diff --check` has no output.

- [ ] **Step 2: Review the final diff and credential scan**

Confirm:

- only intended Skill and plan files changed;
- no runtime config or response dump is staged;
- no real AppKey, SecretId, or SecretKey appears;
- `SKILL.md` stays concise and imperative;
- the intranet guide remains understandable without reading Python.

- [ ] **Step 3: Commit final refinements**

```bash
git add -- 'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval'
git commit -m 'test: verify ADP knowledge retrieval skill'
```

Skip the commit if no tracked refinements remain.
