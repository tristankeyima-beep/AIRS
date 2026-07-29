# ADP Inline Credentials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let intranet operators place AppKey, SecretId, and SecretKey directly in `adp-config.json`, while the current SSE request uses only AppKey and never leaks any credential.

**Architecture:** Replace the `app_key_env` indirection with a required `app_key` configuration field. Keep `secret_id` and `secret_key` beside it as optional V3-signature reserves; do not add them to the SSE body. Update the template, Skill instructions, deployment guide, tests, and Git ignore rule as one consistent configuration contract.

**Tech Stack:** Python 3 standard library, JSON, `unittest`, Markdown Skill instructions, Git.

---

## File map

- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/scripts/query_adp.py` — validate configuration and build the SSE body from `app_key`.
- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py` — lock the direct-credential contract and update existing fixtures.
- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/config/adp-config.template.json` — show the four direct deployment fields.
- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/SKILL.md` — classify missing configuration without referring to environment variables.
- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/references/internal-deployment.md` — give Qwen and operators a short copy-edit-test procedure.
- Modify: `.gitignore` — prevent the real runtime configuration from being committed.

### Task 1: Define the direct-credential contract in failing tests

**Files:**
- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py`
- Test: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py`

- [ ] **Step 1: Replace the configuration-loading contract tests**

Update the first configuration tests so a valid file contains:

```python
{
    "chat_url": "https://example.test/chat/sse",
    "app_key": "test-only-app-key",
    "secret_id": "test-only-secret-id",
    "secret_key": "test-only-secret-key",
}
```

Assert:

```python
self.assertEqual(config["app_key"], "test-only-app-key")
self.assertEqual(config["secret_id"], "test-only-secret-id")
self.assertEqual(config["secret_key"], "test-only-secret-key")
```

Add a test proving that blank `app_key` is rejected without exposing any supplied credential:

```python
def test_load_config_rejects_blank_app_key_without_leaking_credentials(self):
    config = {
        "chat_url": "https://example.test/chat/sse",
        "app_key": " ",
        "secret_id": "test-only-secret-id",
        "secret_key": "test-only-secret-key",
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "config.json"
        path.write_text(
            json.dumps(config, ensure_ascii=False),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            self.query_adp.ConfigError,
            "app_key",
        ) as raised:
            self.query_adp.load_config(path)

    message = str(raised.exception)
    self.assertNotIn("test-only-secret-id", message)
    self.assertNotIn("test-only-secret-key", message)
```

Add a compatibility test proving the signing reserves do not block SSE:

```python
def test_load_config_allows_missing_v3_signing_credentials(self):
    config = {
        "chat_url": "https://example.test/chat/sse",
        "app_key": "test-only-app-key",
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "config.json"
        path.write_text(
            json.dumps(config, ensure_ascii=False),
            encoding="utf-8",
        )
        loaded = self.query_adp.load_config(path)
    self.assertEqual(loaded["app_key"], "test-only-app-key")
    self.assertNotIn("secret_id", loaded)
    self.assertNotIn("secret_key", loaded)
```

- [ ] **Step 2: Replace the request-building contract tests**

Replace environment-based setup with a direct configuration:

```python
config = {
    "app_key": "test-only-app-key",
    "secret_id": "test-only-secret-id",
    "secret_key": "test-only-secret-key",
    "streaming_throttle": 10,
    "workflow_status": "enable",
    "search_network": "disable",
}
request = self.query_adp.build_request(
    config,
    "糖尿病的诊断标准是什么？",
)
```

Assert:

```python
self.assertEqual(request["bot_app_key"], "test-only-app-key")
self.assertNotIn("secret_id", request)
self.assertNotIn("secret_key", request)
self.assertNotIn("test-only-secret-id", json.dumps(request))
self.assertNotIn("test-only-secret-key", json.dumps(request))
```

Replace `test_build_request_trims_query_and_uses_default_app_key_env` with:

```python
def test_build_request_trims_query_without_environment_variables(self):
    with mock.patch.dict(os.environ, {}, clear=True):
        request = self.query_adp.build_request(
            {"app_key": "test-only-app-key"},
            "  test query  ",
        )
    self.assertEqual(request["content"], "test query")
    self.assertEqual(request["bot_app_key"], "test-only-app-key")
```

Replace the missing-environment test with:

```python
def test_build_request_without_app_key_raises_safe_config_error(self):
    with self.assertRaisesRegex(
        self.query_adp.ConfigError,
        "app_key",
    ) as raised:
        self.query_adp.build_request({}, "test query")
    self.assertNotIn("test-only-secret", str(raised.exception))
```

- [ ] **Step 3: Mechanically update remaining test fixtures**

In every test configuration dictionary, replace:

```python
"app_key_env": "TEST_ADP_KEY"
```

with:

```python
"app_key": "test-only-app-key"
```

Remove `mock.patch.dict(os.environ, ...)` blocks that exist only to provide the ADP AppKey. Keep `os` imports and environment patches used by subprocess or unrelated safety tests.

- [ ] **Step 4: Run the focused tests and verify RED**

Run:

```bash
/Users/Tristan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py'
```

Expected: FAIL because `load_config()` still requires `app_key_env` and `build_request()` still reads `ADP_APP_KEY`.

- [ ] **Step 5: Commit the failing contract**

```bash
git add 'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py'
git commit -m 'test: define inline ADP credential contract'
```

### Task 2: Read AppKey directly without sending signing credentials

**Files:**
- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/scripts/query_adp.py`
- Test: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py`

- [ ] **Step 1: Change required configuration validation**

In `load_config()`, replace:

```python
for name in ("chat_url", "app_key_env"):
```

with:

```python
for name in ("chat_url", "app_key"):
```

Leave `secret_id` and `secret_key` optional because the current SSE request does not use V3 signing.

- [ ] **Step 2: Change AppKey resolution in `build_request()`**

Replace the environment-variable block with:

```python
app_key = config.get("app_key")
if not isinstance(app_key, str) or not app_key.strip():
    raise ConfigError("配置缺少有效字段: app_key")
app_key = app_key.strip()
```

Keep the request body field:

```python
"bot_app_key": app_key,
```

Do not add `secret_id` or `secret_key` to the request body, headers, debug output, result JSON, or exception messages.

- [ ] **Step 3: Remove the unused production import**

If `scripts/query_adp.py` no longer uses `os`, remove:

```python
import os
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Task 1 test command.

Expected: all target tests PASS.

- [ ] **Step 5: Run strict Python checks**

```bash
PYTHONWARNINGS=error::ResourceWarning \
  /Users/Tristan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py'

/Users/Tristan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m py_compile \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/scripts/query_adp.py'
```

Expected: tests PASS with no warnings; compilation succeeds.

- [ ] **Step 6: Commit the implementation**

```bash
git add \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/scripts/query_adp.py' \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py'
git commit -m 'feat: read ADP credentials from config'
```

### Task 3: Make the template and operator instructions consistent

**Files:**
- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/config/adp-config.template.json`
- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/SKILL.md`
- Modify: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/references/internal-deployment.md`
- Modify: `.gitignore`
- Test: `SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py`

- [ ] **Step 1: Add a failing template contract test**

Add:

```python
def test_config_template_uses_direct_credentials(self):
    template_path = (
        SCRIPT_PATH.parents[1]
        / "config"
        / "adp-config.template.json"
    )
    template = json.loads(template_path.read_text(encoding="utf-8"))

    self.assertEqual(template["chat_url"], "")
    self.assertEqual(template["app_key"], "")
    self.assertEqual(template["secret_id"], "")
    self.assertEqual(template["secret_key"], "")
    self.assertNotIn("app_key_env", template)
```

Run the target tests.

Expected: FAIL because the current template still contains `app_key_env`.

- [ ] **Step 2: Replace the template**

Set `config/adp-config.template.json` to:

```json
{
  "chat_url": "",
  "app_key": "",
  "secret_id": "",
  "secret_key": "",
  "timeout_seconds": 120,
  "streaming_throttle": 10,
  "workflow_status": "enable",
  "search_network": "disable"
}
```

- [ ] **Step 3: Update `SKILL.md`**

Keep the invocation command unchanged. Change the configuration failure sentence to:

```markdown
配置文件缺失或 `chat_url`、`app_key` 未填写为“未配置”（`config`）。
```

Do not teach the calling model to echo, print, or inspect credential values.

- [ ] **Step 4: Replace the deployment guide with four simple steps**

Document exactly:

1. Copy `adp-config.template.json` to `adp-config.json`.
2. Fill `chat_url`, `app_key`, `secret_id`, and `secret_key` directly in that file.
3. Explain that SSE sends only AppKey; SecretId and SecretKey are reserved for V3 signing and currently do not block SSE when blank.
4. Run the existing `--query-stdin` self-test.

Include:

```markdown
真实 `adp-config.json` 只放在内网运行机器，不提交 Git，不复制到聊天或日志。
```

Remove all instructions about `ADP_APP_KEY`, environment variables, systemd environment files, or external secret managers.

- [ ] **Step 5: Ignore the runtime configuration**

Append this exact repository-relative entry to `.gitignore`:

```gitignore
SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/config/adp-config.json
```

Verify:

```bash
git check-ignore -v \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/config/adp-config.json'
```

Expected: `.gitignore` reports the exact matching rule.

- [ ] **Step 6: Run tests and Skill validation**

```bash
/Users/Tristan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py'

PYTHONPATH=/Users/Tristan/Library/Python/3.13/lib/python/site-packages \
  /Users/Tristan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/Tristan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval'
```

Expected: all tests PASS and output contains `Skill is valid!`.

- [ ] **Step 7: Commit documentation and template**

```bash
git add \
  .gitignore \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/config/adp-config.template.json' \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/SKILL.md' \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/references/internal-deployment.md' \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval/tests/test_query_adp.py'
git commit -m 'docs: simplify intranet ADP credential setup'
```

### Task 4: Final verification and cloud regression

**Files:**
- Verify: all files changed since `9b49892`

- [ ] **Step 1: Run the full local verification**

```bash
RUNTIME_PY=/Users/Tristan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
SKILL_DIR='SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval'

PYTHONWARNINGS=error::ResourceWarning "$RUNTIME_PY" \
  -m unittest "$SKILL_DIR/tests/test_query_adp.py"

"$RUNTIME_PY" \
  -m unittest 'SKILLS/开发验证（非 Skill）/test_skill_layout.py'

PYTHONPATH=/Users/Tristan/Library/Python/3.13/lib/python/site-packages \
  "$RUNTIME_PY" \
  /Users/Tristan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  "$SKILL_DIR"

"$RUNTIME_PY" -m py_compile "$SKILL_DIR/scripts/query_adp.py"
find "$SKILL_DIR" -type d -name __pycache__ -prune -exec rm -r {} +
git diff --check
git status --short
```

Expected: target tests and four layout tests PASS, Skill validation succeeds, compilation succeeds, and the worktree is clean after committed changes.

- [ ] **Step 2: Scan the deliverable for real credentials**

```bash
! rg -n --hidden \
  '(AKID[0-9A-Za-z]{12,}|bot_app_key[\"'\"'\"' ]*[:=][\"'\"'\"' ]*[0-9A-Za-z]{16,}|secret_(id|key)[\"'\"'\"' ]*[:=][\"'\"'\"' ]*[0-9A-Za-z]{16,})' \
  'SKILLS/慢病知识库检索/chronic-disease-knowledge-retrieval'
```

Expected: no real-looking credential values.

- [ ] **Step 3: Run one cloud smoke test without persisting credentials**

In a trusted local TTY, run this command. It prompts without echo, creates a
mode-`0600` configuration outside the repository, calls the real CLI entry
point, and deletes the file in `finally`:

```bash
/Users/Tristan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -c '
import getpass
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile

script_path = Path(
    "SKILLS/慢病知识库检索/"
    "chronic-disease-knowledge-retrieval/scripts/query_adp.py"
).resolve()
spec = importlib.util.spec_from_file_location("query_adp", script_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

config = {
    "chat_url": "https://wss.lke.cloud.tencent.com/v1/qbot/chat/sse",
    "app_key": getpass.getpass("AppKey: "),
    "secret_id": "",
    "secret_key": "",
    "timeout_seconds": 120,
    "streaming_throttle": 10,
    "workflow_status": "enable",
    "search_network": "disable",
}

descriptor, config_path = tempfile.mkstemp(
    prefix="adp-smoke-",
    suffix=".json",
    text=True,
)
try:
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, allow_nan=False)
    sys.stdin = io.StringIO("尿毒症透析认定标准\n")
    exit_code = module.main(
        ["--config", config_path, "--query-stdin"]
    )
finally:
    Path(config_path).unlink(missing_ok=True)

raise SystemExit(exit_code)
'
```

Do not print the AppKey, temporary configuration, request body, environment, or shell history.

Expected: exit code `0`; stdout is strict UTF-8 JSON; `ok` is `true`; `answer` is non-empty and not equal to the query.

- [ ] **Step 4: Request an independent final review**

Ask a reviewer to inspect:

- direct credential loading;
- absence of environment-variable dependency;
- SecretId/SecretKey exclusion from SSE;
- log and error redaction;
- ignored runtime configuration;
- consistency between template, Skill, and deployment guide;
- all verification evidence.

Expected: `Approved` with no Critical or Important issues.

- [ ] **Step 5: Commit any review-only corrections and re-run Step 1**

If review finds a defect, add a failing regression test first, implement the smallest correction, commit it, and repeat the complete verification. Do not weaken tests to obtain approval.
