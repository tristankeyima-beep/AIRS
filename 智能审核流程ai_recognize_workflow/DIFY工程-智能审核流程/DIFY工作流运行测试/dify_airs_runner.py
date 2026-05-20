#!/usr/bin/env python3
import argparse
import html
import json
import re
import ssl
import subprocess
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
README_PATH = SCRIPT_DIR / "README.md"
ENV_CONFIG_PATH = SCRIPT_DIR / "dify_envs.local.json"
DEFAULT_API_BASE = "https://dify.hzmarvel.com/v1"
DEFAULT_RESPONSE_MODE = "streaming"
DEFAULT_USER = "dify-airs-workflow-test"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
INPUT_FILE_NAME = "入参.json"
DEFAULT_ENV = "test"
QC_REPORT_TEMPLATE_VERSION = 9


class PrepareResult:
    def __init__(self, case_dir, patient_name, disease_name, input_path, terminal_command):
        self.case_dir = case_dir
        self.patient_name = patient_name
        self.disease_name = disease_name
        self.input_path = input_path
        self.terminal_command = terminal_command


def parse_local_time(value):
    return datetime.fromisoformat(value).astimezone(LOCAL_TZ)


def now_local():
    return datetime.now(LOCAL_TZ)


def compact_timestamp(value):
    return value.astimezone(LOCAL_TZ).strftime("%Y%m%d-%H%M%S")


def display_timestamp(value):
    return value.astimezone(LOCAL_TZ).isoformat(timespec="seconds")


def read_json_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json_file(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_maybe_json(value):
    if isinstance(value, str):
        text = value.strip()
        if text and text[0] in "[{":
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
    return value


def stringify_for_dify(value):
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def sanitize_path_part(value, fallback):
    text = str(value or "").strip() or fallback
    text = re.sub(r'[/\\:*?"<>|\r\n\t]+', " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback


def extract_disease_name(raw_input, certification):
    if isinstance(certification, dict):
        disease = certification.get("meta", {}).get("chronicDiseaseName")
        if disease:
            return str(disease)
    return str(raw_input.get("chronicDiseaseName") or "未知病种")


def extract_patient_name(raw_input, materials):
    for key in ("patientName", "patient_name", "姓名"):
        value = raw_input.get(key)
        if value:
            return str(value)

    if isinstance(materials, list):
        for material in materials:
            if not isinstance(material, dict):
                continue
            content = str(material.get("materialContent") or "")
            match = re.search(r"姓名\s*[:： ]\s*([^\s，,。；;|]+)", content)
            if match:
                return match.group(1).strip()
    return "未知患者"


def normalize_inputs(raw_input):
    raw_inputs = raw_input.get("inputs") if isinstance(raw_input.get("inputs"), dict) else raw_input
    certification = parse_maybe_json(raw_inputs.get("certification_list"))
    materials = parse_maybe_json(raw_inputs.get("material_list"))

    normalized = dict(raw_inputs)
    if "certification_list" in normalized:
        normalized["certification_list"] = stringify_for_dify(certification)
    if "material_list" in normalized:
        normalized["material_list"] = stringify_for_dify(materials)

    for key in ("response_mode", "user", "conversation_id", "query"):
        normalized.pop(key, None)

    patient_name = extract_patient_name(raw_inputs, materials)
    disease_name = extract_disease_name(raw_inputs, certification)
    return normalized, patient_name, disease_name, certification, materials


def read_api_key_from_readme(readme_path=README_PATH):
    text = Path(readme_path).read_text(encoding="utf-8")
    match = re.search(r'DIFY_API_KEY\s*=\s*"([^"]+)"', text)
    if not match:
        match = re.search(r"DIFY_API_KEY\s*=\s*'([^']+)'", text)
    if not match:
        raise RuntimeError("README.md 中未找到 DIFY_API_KEY=\"app-...\"。")
    return match.group(1)


def load_environment(env_key=DEFAULT_ENV, config_path=ENV_CONFIG_PATH):
    env_key = env_key or DEFAULT_ENV
    path = Path(config_path)
    if path.exists():
        config = read_json_file(path)
        if env_key not in config:
            available = ", ".join(sorted(config.keys())) or "无"
            raise RuntimeError(f"环境 {env_key} 未配置。可用环境：{available}")
        env = dict(config[env_key])
    elif env_key == DEFAULT_ENV:
        env = {
            "label": "测试环境",
            "api_base": DEFAULT_API_BASE,
            "api_key": read_api_key_from_readme(),
        }
    else:
        raise RuntimeError(f"未找到环境配置文件：{path}")
    env["key"] = env_key
    env.setdefault("label", env_key)
    env.setdefault("api_base", DEFAULT_API_BASE)
    env.setdefault("verify_ssl", True)
    if not env.get("api_key"):
        raise RuntimeError(f"环境 {env_key} 未配置 api_key。")
    return env


def mask_secret_value(value):
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return text[:4] + "***" + text[-4:]


def shell_quote(value):
    text = str(value)
    if re.match(r"^[A-Za-z0-9_./:=@%+\-]+$", text):
        return text
    return '"' + re.sub(r'(["\\$`])', r"\\\1", text) + '"'


def build_run_command(case_dir, env_key=""):
    relative_case = case_dir
    try:
        relative_case = case_dir.relative_to(SCRIPT_DIR)
    except ValueError:
        pass
    env_arg = f" --env {shell_quote(env_key)}" if env_key else ""
    return (
        f"cd {shell_quote(SCRIPT_DIR)} && "
        f"python3 dify_airs_runner.py run{env_arg} --case-dir {shell_quote(relative_case)}"
    )


def prepare_input_file(input_path, output_root=None, now=None, env_key=""):
    input_path = Path(input_path)
    output_root = Path(output_root) if output_root else SCRIPT_DIR / "userinput"
    now = now or now_local()
    raw_input = read_json_file(input_path)
    inputs, patient_name, disease_name, certification, materials = normalize_inputs(raw_input)

    safe_patient = sanitize_path_part(patient_name, "未知患者")
    safe_disease = sanitize_path_part(disease_name, "未知病种")
    case_dir = output_root / f"{safe_patient}_{safe_disease}_{compact_timestamp(now)}"
    case_dir.mkdir(parents=True, exist_ok=True)
    terminal_command = build_run_command(case_dir, env_key)
    payload = {
        "metadata": {
            "patientName": patient_name,
            "diseaseName": disease_name,
            "recordedAt": display_timestamp(now),
            "timeZone": "Asia/Shanghai",
            "sourceInput": str(input_path),
            "environment": env_key or "",
        },
        "raw_input": raw_input,
        "parsed_input": {
            "certification_list": certification,
            "material_list": materials,
        },
        "dify_payload": {
            "inputs": inputs,
            "response_mode": DEFAULT_RESPONSE_MODE,
            "user": DEFAULT_USER,
        },
        "terminal_command": terminal_command,
    }
    input_record_path = case_dir / INPUT_FILE_NAME
    write_json_file(input_record_path, payload)
    return PrepareResult(case_dir, patient_name, disease_name, input_record_path, terminal_command)


def load_case_input(case_dir):
    case_dir = Path(case_dir)
    if not case_dir.is_absolute():
        case_dir = SCRIPT_DIR / case_dir
    input_path = case_dir / INPUT_FILE_NAME
    return case_dir, read_json_file(input_path)


def mask_headers(headers):
    return {
        key: ("Bearer ***" if key.lower() == "authorization" else value)
        for key, value in headers.items()
    }


def create_ssl_context():
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        context = ssl.create_default_context()
    if hasattr(ssl, "OP_IGNORE_UNEXPECTED_EOF"):
        context.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
    return context


def parse_sse_block(block):
    event_type = ""
    data_lines = []
    for line in block.splitlines():
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if not data_lines:
        return None
    data_text = "\n".join(data_lines)
    try:
        payload = json.loads(data_text)
    except json.JSONDecodeError:
        payload = data_text
    return {"type": event_type or "message", "payload": payload, "raw": block}


def collect_event_summary(record, event):
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    name = payload.get("event") or event.get("type") or "unknown"
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

    if name == "node_started":
        record["nodeRuns"].append({
            "id": data.get("id") or data.get("node_id") or "",
            "title": data.get("title") or data.get("node_type") or "unknown",
            "type": data.get("node_type") or "",
            "status": "running",
            "inputs": None,
            "outputs": None,
        })
    elif name == "node_finished":
        title = data.get("title") or data.get("node_type") or "unknown"
        target = None
        for node in reversed(record["nodeRuns"]):
            if node.get("title") == title and node.get("status") == "running":
                target = node
                break
        if target is None:
            target = {"id": data.get("id") or data.get("node_id") or "", "title": title, "type": data.get("node_type") or ""}
            record["nodeRuns"].append(target)
        target.update({
            "status": data.get("status") or "finished",
            "elapsedSeconds": data.get("elapsed_time"),
            "inputs": data.get("inputs"),
            "processData": data.get("process_data"),
            "outputs": data.get("outputs"),
        })
    elif name == "workflow_finished":
        record["finalOutputs"] = data.get("outputs")


def call_dify_workflow(case_record, api_base, api_key, response_mode, transport="curl"):
    started = now_local()
    url = api_base.rstrip("/") + "/workflows/run"
    body = dict(case_record["dify_payload"])
    body["response_mode"] = response_mode
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    record = {
        "startedAt": display_timestamp(started),
        "endedAt": "",
        "timeZone": "Asia/Shanghai",
        "caseMetadata": case_record.get("metadata", {}),
        "terminalCommand": case_record.get("terminal_command", ""),
        "request": {"method": "POST", "url": url, "headers": mask_headers(headers), "body": body},
        "response": None,
        "events": [],
        "nodeRuns": [],
        "finalOutputs": None,
        "error": None,
    }
    if transport == "curl":
        call_dify_with_curl(record, url, headers, body)
        record["endedAt"] = display_timestamp(now_local())
        return record

    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        open_kwargs = {"timeout": 180}
        if url.startswith("https://"):
            open_kwargs["context"] = create_ssl_context()
        with urllib.request.urlopen(request, **open_kwargs) as response:
            response_headers = dict(response.headers.items())
            record["response"] = {
                "status": response.status,
                "reason": response.reason,
                "headers": response_headers,
                "body": None,
            }
            content_type = response_headers.get("Content-Type", "")
            if response_mode == "streaming" or "text/event-stream" in content_type:
                buffer = ""
                for chunk in response:
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n\n" in buffer:
                        block, buffer = buffer.split("\n\n", 1)
                        event = parse_sse_block(block)
                        if event:
                            record["events"].append(event)
                            collect_event_summary(record, event)
                event = parse_sse_block(buffer)
                if event:
                    record["events"].append(event)
                    collect_event_summary(record, event)
            else:
                text = response.read().decode("utf-8", errors="replace")
                try:
                    record["response"]["body"] = json.loads(text)
                except json.JSONDecodeError:
                    record["response"]["body"] = text
    except Exception as exc:
        record["error"] = {"type": exc.__class__.__name__, "message": str(exc)}
        if hasattr(exc, "code"):
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                error_body = ""
            record["response"] = {"status": exc.code, "reason": getattr(exc, "reason", ""), "headers": {}, "body": error_body}
    finally:
        record["endedAt"] = display_timestamp(now_local())
    return record


def call_dify_with_curl(record, url, headers, body):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=True) as body_file:
        json.dump(body, body_file, ensure_ascii=False, separators=(",", ":"))
        body_file.flush()
        command = [
            "curl",
            "-sS",
            "-N",
            "--max-time",
            "300",
            "-X",
            "POST",
            url,
            "-H",
            f"Authorization: {headers['Authorization']}",
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            f"@{body_file.name}",
            "-w",
            "\n__DIFY_HTTP_STATUS__:%{http_code}\n",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=330,
                check=False,
            )
        except Exception as exc:
            record["error"] = {"type": exc.__class__.__name__, "message": str(exc)}
            return
    collect_curl_response(record, completed.stdout, completed.stderr)
    if completed.returncode != 0 and record.get("error") is None:
        record["error"] = {
            "type": "CurlError",
            "message": completed.stderr.strip() or f"curl exited with {completed.returncode}",
        }


def collect_curl_response(record, stdout, stderr):
    match = re.search(r"\n__DIFY_HTTP_STATUS__:(\d{3})\s*$", stdout)
    status = int(match.group(1)) if match else 0
    body_text = stdout[: match.start()] if match else stdout
    record["response"] = {
        "status": status,
        "reason": "",
        "headers": {},
        "body": None,
        "stderr": stderr.strip(),
    }
    if status >= 400 or not body_text.lstrip().startswith("data:"):
        try:
            record["response"]["body"] = json.loads(body_text)
        except json.JSONDecodeError:
            record["response"]["body"] = body_text
        if status >= 400:
            record["error"] = {
                "type": "HTTPError",
                "message": f"HTTP Error {status}",
            }
        return

    for block in body_text.split("\n\n"):
        event = parse_sse_block(block)
        if not event:
            continue
        record["events"].append(event)
        collect_event_summary(record, event)


def call_dify_json(api_base, api_key, path, params=None, timeout=120, verify_ssl=True):
    query = urllib.parse.urlencode(params or {})
    url = api_base.rstrip("/") + path
    if query:
        url += "?" + query
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="GET",
    )
    open_kwargs = {"timeout": timeout}
    if url.startswith("https://"):
        open_kwargs["context"] = create_ssl_context() if verify_ssl else ssl._create_unverified_context()
    with urllib.request.urlopen(request, **open_kwargs) as response:
        text = response.read().decode("utf-8", errors="replace")
    return json.loads(text) if text.strip() else {}


def parse_dify_time(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), LOCAL_TZ)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text), LOCAL_TZ)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(LOCAL_TZ)


def workflow_log_run(log_item):
    if not isinstance(log_item, dict):
        return {}
    for key in ("workflow_run", "workflowRun", "run", "workflow_run_detail"):
        if isinstance(log_item.get(key), dict):
            merged = dict(log_item)
            merged.update(log_item[key])
            return merged
    if isinstance(log_item.get("data"), dict) and (
        log_item["data"].get("id") or log_item["data"].get("workflow_run_id")
    ):
        merged = dict(log_item)
        merged.update(log_item["data"])
        return merged
    return log_item


def workflow_run_id_from_log(log_item):
    run = workflow_log_run(log_item)
    for key in ("workflow_run_id", "workflowRunId", "id"):
        if run.get(key):
            return str(run[key])
    return ""


def is_log_within_range(log_item, start_time, end_time):
    run = workflow_log_run(log_item)
    created = parse_dify_time(run.get("created_at") or run.get("createdAt"))
    if created is None:
        return True
    return start_time <= created <= end_time


def fetch_workflow_logs(env, start_time, end_time, page_size=100):
    logs = []
    page = 1
    while True:
        payload = call_dify_json(
            env["api_base"],
            env["api_key"],
            "/workflows/logs",
            {"page": page, "limit": page_size},
            verify_ssl=env.get("verify_ssl", True),
        )
        data = payload.get("data") if isinstance(payload, dict) else []
        if not isinstance(data, list) or not data:
            break
        for item in data:
            if is_log_within_range(item, start_time, end_time):
                logs.append(item)
        if len(data) < page_size or page >= 50:
            break
        page += 1
    return logs


def fetch_workflow_run_detail(env, run_id):
    try:
        payload = call_dify_json(
            env["api_base"],
            env["api_key"],
            f"/workflows/run/{urllib.parse.quote(run_id)}",
            verify_ssl=env.get("verify_ssl", True),
        )
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            return payload["data"]
        return payload
    except Exception:
        return {}


def find_workflow_run_id(record):
    for event in record.get("events", []):
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        run_id = payload.get("workflow_run_id")
        if run_id:
            return str(run_id)
        data = payload.get("data")
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
    body = record.get("response", {}).get("body") if isinstance(record.get("response"), dict) else None
    if isinstance(body, dict):
        for key in ("workflow_run_id", "id"):
            if body.get(key):
                return str(body[key])
    return "no-workflowrunid"


def write_result_record(case_dir, record, call_time=None):
    case_dir = Path(case_dir)
    call_time = call_time or now_local()
    run_id = sanitize_path_part(find_workflow_run_id(record), "no-workflowrunid")
    stamp = compact_timestamp(call_time)
    output_dir = case_dir / f"{stamp}_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"{stamp}_{run_id}_raw-result.json"
    html_path = output_dir / f"{stamp}_{run_id}_result.html"
    events_path = output_dir / f"{stamp}_{run_id}_events.ndjson"
    write_json_file(raw_path, record)
    if record.get("events"):
        events_path.write_text(
            "\n".join(json.dumps(event, ensure_ascii=False) for event in record["events"]) + "\n",
            encoding="utf-8",
        )
    html_path.write_text(render_html(case_dir, record, run_id), encoding="utf-8")
    return output_dir, raw_path, html_path


def get_run_error_hint(record):
    response = record.get("response") if isinstance(record.get("response"), dict) else {}
    body = response.get("body") or ""
    if response.get("status") == 401 or "Access token is invalid" in str(body):
        return "API Key 无效。请更新 README.md 中的 DIFY_API_KEY，或运行时用 --api-key 传入正确 Key。"
    return ""


def get_case_metadata(case_dir):
    try:
        return read_json_file(Path(case_dir) / INPUT_FILE_NAME)
    except Exception:
        return {}


def escape(value):
    return html.escape(json.dumps(value, ensure_ascii=False, indent=2) if not isinstance(value, str) else value)


def status_class(value):
    text = str(value or "")
    if "不通过" in text or "失败" in text or "异常" in text:
        return "bad"
    if "通过" in text or "成功" in text or text == "200" or text == "succeeded":
        return "good"
    return "warn"


def finished_nodes(record):
    return [node for node in record.get("nodeRuns", []) if node.get("status") and node.get("status") != "running"]


def render_evidence_rows(results):
    if not results:
        return "<p class=\"empty\">没有精解命中证据。</p>"
    rows = []
    for item in results:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('materialName', '')))}<div class=\"meta\">{escape(str(item.get('materialId', '')))}</div></td>"
            f"<td><span class=\"value-pill\">{escape(str(item.get('value', '')))}</span></td>"
            f"<td class=\"evidence-text\">{escape(str(item.get('rawText') or item.get('refContent') or ''))}</td>"
            "</tr>"
        )
    return "<table class=\"evidence-table\"><thead><tr><th>材料</th><th>取值</th><th>证据原文</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def render_keyword_guides(rule):
    guides = rule.get("ruleKeywordGuide") if isinstance(rule, dict) else []
    if not isinstance(guides, list) or not guides:
        return "<p class=\"empty\">没有提取规则与精解结果。</p>"
    cards = []
    for guide in guides:
        if not isinstance(guide, dict):
            continue
        found = "已命中" if guide.get("found") else "未命中"
        cards.append(
            "<details class=\"keyword-card\" open>"
            f"<summary><span>{escape(str(guide.get('keywordCode', '提取项')))}</span><span class=\"pill {status_class(found)}\">{escape(found)}</span></summary>"
            f"{render_evidence_rows(guide.get('results') or [])}"
            "</details>"
        )
    return "".join(cards)


def render_suspicion_list(rule):
    suspicions = rule.get("suspicionList") if isinstance(rule, dict) else []
    if not isinstance(suspicions, list) or not suspicions:
        return "<p class=\"empty\">没有疑点说明。</p>"
    blocks = []
    for suspicion in suspicions:
        if not isinstance(suspicion, dict):
            continue
        source_items = []
        for source in suspicion.get("sources") or []:
            if isinstance(source, dict):
                source_items.append(
                    "<li>"
                    f"<strong>{escape(str(source.get('materialName', '')))}</strong>"
                    f"<span class=\"meta\">{escape(str(source.get('materialId', '')))}</span>"
                    f"<p>{escape(str(source.get('refContent', '')))}</p>"
                    "</li>"
                )
        blocks.append(
            "<article class=\"suspicion-card\">"
            f"<h4>{escape(str(suspicion.get('suspicionType', '疑点')))}</h4>"
            f"<p>{escape(str(suspicion.get('detail', '')))}</p>"
            f"<ul class=\"source-list\">{''.join(source_items)}</ul>"
            "</article>"
        )
    return "".join(blocks)


def rule_decision_summary(rule):
    if not isinstance(rule, dict):
        return "未识别模型判断依据。"
    suspicions = rule.get("suspicionList")
    if isinstance(suspicions, list):
        for suspicion in suspicions:
            if isinstance(suspicion, dict) and suspicion.get("detail"):
                return str(suspicion.get("detail"))
    reasoning = str(rule.get("reasoningContent") or "").strip()
    if not reasoning:
        return "未识别模型判断依据。"
    compact = re.sub(r"\s+", " ", reasoning)
    if len(compact) > 280:
        return compact[:280].rstrip() + "..."
    return compact


def operator_label(operator):
    normalized = str(operator or "").upper()
    if normalized == "AND":
        return "AND · 全部条件满足"
    if normalized == "OR":
        return "OR · 任一条件满足"
    return normalized or "未识别关系"


def find_rule_relation(logic_node, rule_code, ancestors=None):
    ancestors = ancestors or []
    if not isinstance(logic_node, dict):
        return []
    node_type = str(logic_node.get("type") or "").upper()
    if node_type == "RULE_REF" and str(logic_node.get("ruleCode") or "") == str(rule_code):
        return ancestors
    operator = logic_node.get("operator")
    next_ancestors = ancestors + [operator] if operator else ancestors
    for child in logic_node.get("children") or []:
        found = find_rule_relation(child, rule_code, next_ancestors)
        if found:
            return found
    return []


def rule_repository_by_code(certification):
    repository = certification.get("ruleRepository") if isinstance(certification, dict) else []
    if not isinstance(repository, list):
        return {}
    return {
        str(rule.get("ruleCode")): rule
        for rule in repository
        if isinstance(rule, dict) and rule.get("ruleCode")
    }


def rule_results_by_code(rules):
    if not isinstance(rules, list):
        return {}
    return {
        str(rule.get("ruleCode")): rule
        for rule in rules
        if isinstance(rule, dict) and rule.get("ruleCode")
    }


def rule_maintenance_issue(rule_repo):
    if not isinstance(rule_repo, dict) or not rule_repo:
        return "未在 ruleRepository 中维护该规则。"
    guides = rule_repo.get("ruleKeywordGuide")
    if not isinstance(guides, list) or not guides:
        return "未维护提取项说明，规则库配置不完整。"
    return ""


def render_rule_maintenance_alert(rule_map, result_map):
    issues = []
    for rule_code in result_map:
        issue = rule_maintenance_issue(rule_map.get(rule_code))
        if issue:
            title = ""
            rule = rule_map.get(rule_code)
            if isinstance(rule, dict):
                title = rule.get("ruleContent") or ""
            issues.append(
                "<li>"
                f"<strong>规则 {escape(rule_code)}</strong>"
                f"<span>{escape(str(title))}</span>"
                f"<em>{escape(issue)}</em>"
                "</li>"
            )
    if not issues:
        return ""
    return (
        "<div class=\"maintenance-alert\">"
        "<h4>规则维护告警</h4>"
        "<p>以下规则没有维护完整，会影响规则可解释性和质控追溯。</p>"
        f"<ul>{''.join(issues)}</ul>"
        "</div>"
    )


def render_overview_rule_detail(rule_code, rule, rule_map, relation_text, open_by_default=False):
    rule = rule if isinstance(rule, dict) else {}
    rule_repo = rule_map.get(rule_code) or {}
    result = str(rule.get("ruleResult") or rule.get("reviewResult") or "未识别")
    rule_title = rule.get("ruleContent") or rule_repo.get("ruleContent") or ""
    open_attr = " open" if open_by_default else ""
    maintenance_issue = rule_maintenance_issue(rule_repo)
    maintenance_class = " maintenance-missing" if maintenance_issue else ""
    maintenance_badge = (
        f"<span class=\"maintenance-inline\">规则维护不完整：{escape(maintenance_issue)}</span>"
        if maintenance_issue
        else ""
    )
    return (
        f"<details class=\"overview-rule logic-rule-detail{maintenance_class}\"{open_attr}>"
        "<summary>"
        "<span>"
        f"<strong>规则 {escape(rule_code)}</strong>"
        f"<em>{escape(relation_text)}</em>"
        f"<span class=\"logic-rule-title\">规则原文：{escape(str(rule_title))}</span>"
        f"{maintenance_badge}"
        "</span>"
        "<span class=\"summary-actions\">"
        f"<span class=\"pill {status_class(result)}\">{escape(result)}</span>"
        f"<button type=\"button\" class=\"process-link\" data-rule-code=\"{escape(rule_code)}\">查看审核过程</button>"
        "</span>"
        "</summary>"
        "<div class=\"overview-rule-body\">"
        f"{render_rule_repository_detail(rule_repo)}"
        "</div>"
        "</details>"
    )


def render_logic_topology_node(node, rule_map, result_map, logic_topology):
    if not isinstance(node, dict):
        return ""
    node_type = str(node.get("type") or "").upper()
    if node_type == "RULE_REF":
        rule_code = str(node.get("ruleCode") or "")
        operators = find_rule_relation(logic_topology, rule_code)
        relation_text = " / ".join(operator_label(item) for item in operators) if operators else "未识别关系"
        return (
            "<li class=\"logic-rule-ref logic-rule-item\">"
            f"{render_overview_rule_detail(rule_code, result_map.get(rule_code), rule_map, relation_text)}"
            "</li>"
        )
    children = node.get("children") if isinstance(node.get("children"), list) else []
    operator = str(node.get("operator") or "")
    child_html = "".join(render_logic_topology_node(child, rule_map, result_map, logic_topology) for child in children)
    return (
        "<li class=\"logic-group\">"
        f"<div class=\"logic-operator\">{escape(operator_label(operator))}</div>"
        f"<ul>{child_html}</ul>"
        "</li>"
    )


def render_logic_topology(logic_topology, rule_map, result_map):
    if not isinstance(logic_topology, dict) or not logic_topology:
        return "<p class=\"empty\">没有逻辑拓扑。</p>"
    return (
        "<section class=\"logic-topology\">"
        "<h4>逻辑拓扑</h4>"
        "<p class=\"sub\">按入参 logicTopology 展示规则之间的且或关系。</p>"
        f"<ul class=\"logic-tree\">{render_logic_topology_node(logic_topology, rule_map, result_map, logic_topology)}</ul>"
        "</section>"
    )


def render_keyword_definition_rows(guides):
    if not isinstance(guides, list) or not guides:
        return (
            "<div class=\"maintenance-alert compact\">"
            "<h4>规则维护不完整</h4>"
            "<p>未维护提取项说明。请补充每一条提取项的数据结构，包括编号、内容、数据类型、是否必须等字段。</p>"
            "</div>"
        )
    rows = []
    for index, guide in enumerate(guides, 1):
        if not isinstance(guide, dict):
            continue
        code = guide.get("keywordCode") or guide.get("code") or f"提取项{index}"
        content = guide.get("keywordContent") or guide.get("content") or guide.get("name") or ""
        data_type = guide.get("dataType") or guide.get("type") or ""
        required = "是" if guide.get("required") is True else "否" if guide.get("required") is False else str(guide.get("required") or "")
        rows.append(
            "<tr>"
            f"<td>{escape(str(code))}</td>"
            f"<td>{escape(str(content))}</td>"
            f"<td>{escape(str(data_type))}</td>"
            f"<td>{escape(required)}</td>"
            f"<td><pre>{escape(guide)}</pre></td>"
            "</tr>"
        )
    return (
        "<table class=\"keyword-definition-table\">"
        "<thead><tr><th>编号</th><th>内容</th><th>数据类型</th><th>是否必须</th><th>完整数据结构</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_rule_repository_detail(rule_repo):
    if not isinstance(rule_repo, dict) or not rule_repo:
        return "<div class=\"repo-detail\"><h4>规则库详情</h4><p class=\"empty\">未在 ruleRepository 中找到对应规则。</p></div>"
    return (
        "<div class=\"repo-detail\">"
        "<h4>规则库详情</h4>"
        "<div class=\"repo-grid\">"
        "<div><h4>政策原文</h4>"
        f"<p>{escape(str(rule_repo.get('ruleContent', '')))}</p></div>"
        "<div><h4>政策依据</h4>"
        f"<p>{escape(str(rule_repo.get('ruleSource', '')))}</p></div>"
        "<div><h4>经验标准</h4>"
        f"<p>{escape(str(rule_repo.get('experience', '')))}</p></div>"
        "</div>"
        "<h4>提取项说明</h4>"
        f"{render_keyword_definition_rows(rule_repo.get('ruleKeywordGuide'))}"
        "<details class=\"raw-block dev-data\"><summary>展开完整数据结构</summary>"
        f"<pre>{escape(rule_repo)}</pre></details>"
        "</div>"
    )


def render_rule_overview(final_outputs, certification):
    rules = final_outputs.get("ruleResults") if isinstance(final_outputs, dict) else []
    if not isinstance(rules, list) or not rules:
        return "<p class=\"empty\">没有规则判定总览。</p>"
    logic_topology = certification.get("logicTopology") if isinstance(certification, dict) else {}
    rule_map = rule_repository_by_code(certification)
    result_map = rule_results_by_code(rules)
    if isinstance(logic_topology, dict) and logic_topology:
        return render_logic_topology(logic_topology, rule_map, result_map)
    cards = []
    for index, rule in enumerate(rules, 1):
        if not isinstance(rule, dict):
            continue
        rule_code = str(rule.get("ruleCode") or f"规则{index}")
        operators = find_rule_relation(logic_topology, rule_code)
        relation_text = " / ".join(operator_label(item) for item in operators) if operators else "未识别关系"
        cards.append(render_overview_rule_detail(rule_code, rule, rule_map, relation_text, open_by_default=True))
    return "<div class=\"rule-overview-list\">" + "".join(cards) + "</div>"


def render_rule_cards(final_outputs):
    rules = final_outputs.get("ruleResults") if isinstance(final_outputs, dict) else []
    if not isinstance(rules, list) or not rules:
        return "<section id=\"rules\" class=\"panel\"><h2>AI判断过程</h2><p class=\"empty\">没有规则审核明细。</p></section>"
    cards = []
    for index, rule in enumerate(rules, 1):
        if not isinstance(rule, dict):
            continue
        rule_code = str(rule.get("ruleCode") or f"规则{index}")
        result = str(rule.get("ruleResult") or rule.get("reviewResult") or "未识别")
        reasoning = str(rule.get("reasoningContent") or "").strip()
        reasoning_block = ""
        if reasoning:
            reasoning_block = (
                "<details class=\"reasoning-detail\">"
                "<summary>AI判断过程</summary>"
                f"<pre>{escape(reasoning)}</pre>"
                "</details>"
            )
        cards.append(
            f"<details class=\"rule-card\" id=\"rule-{escape(rule_code)}\" open>"
            "<summary class=\"rule-head\"><div>"
            f"<p class=\"eyebrow\">规则 {escape(rule_code)}</p>"
            f"<h3>{escape(str(rule.get('ruleContent', '')))}</h3>"
            "</div>"
            f"<span class=\"pill {status_class(result)}\">{escape(result)}</span></summary>"
            "<div class=\"rule-grid\">"
            "<section class=\"sub-panel\"><h4>提取规则（以下内容由AI根据申请材料得出）</h4>"
            f"{render_keyword_guides(rule)}</section>"
            "<section class=\"sub-panel\"><h4>逐条认定（以下内容由AI给出）</h4>"
            "<div class=\"decision-box\">"
            "<div class=\"decision-line\"><span>认定结果</span>"
            f"<span class=\"pill {status_class(result)}\">{escape(result)}</span></div>"
            f"<p>{escape(rule_decision_summary(rule))}</p>"
            "</div>"
            f"{reasoning_block}</section>"
            "<section class=\"sub-panel\"><h4>疑点说明（以下内容由AI给出）</h4>"
            f"{render_suspicion_list(rule)}</section>"
            "</div></details>"
        )
    return "<section id=\"rules\" class=\"panel\"><h2>AI判断过程</h2><p class=\"sub\">按规则查看：规则定义、提取证据、逐条认定和疑点来源。</p>" + "".join(cards) + "</section>"


def format_duration(seconds):
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "-"
    if value >= 60:
        return f"{value / 60:.1f} 分钟"
    return f"{value:.2f} 秒"


def node_search_text(node):
    try:
        return json.dumps(node, ensure_ascii=False)
    except TypeError:
        return str(node)


def infer_rule_code_from_node(node):
    text = node_search_text(node)
    for pattern in (
        r'"ruleCode"\s*:\s*"([^"]+)"',
        r"ruleCode['\"]?\s*[:=]\s*['\"]([^'\"]+)",
        r'"keywordCode"\s*:\s*"([^"_]+)_',
        r"\b([0-9]{3,})_[0-9]{2}\b",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def is_rule_process_node(node):
    title = str(node.get("title") or "")
    rule_titles = (
        "原文精解",
        "精解结果结构化",
        "逐条认定",
        "单条标准审核结果结构化",
        "提取审核时的推理过程并结构化",
        "单次迭代出参聚合",
    )
    return title in rule_titles


def group_rule_process_nodes(nodes):
    groups = {}
    for node in nodes:
        if not is_rule_process_node(node):
            continue
        rule_code = infer_rule_code_from_node(node) or "未识别规则"
        groups.setdefault(rule_code, []).append(node)
    return groups


def render_parallel_rule_nodes(nodes):
    groups = group_rule_process_nodes(nodes)
    if not groups:
        return "<p class=\"empty\">没有识别到按规则并行处理的节点。</p>"
    max_elapsed = max(
        (float(node.get("elapsedSeconds") or 0) for group in groups.values() for node in group),
        default=1,
    ) or 1
    lanes = []
    for rule_code, group in groups.items():
        total = sum(float(node.get("elapsedSeconds") or 0) for node in group)
        steps = []
        for node in group:
            elapsed = float(node.get("elapsedSeconds") or 0)
            width = max(8, min(100, elapsed / max_elapsed * 100))
            status = str(node.get("status") or "unknown")
            steps.append(
                "<article class=\"node-step\">"
                "<div class=\"node-step-head\">"
                f"<strong>{escape(str(node.get('title', '')))}</strong>"
                f"<span class=\"pill {status_class(status)}\">{escape(status)}</span>"
                "</div>"
                f"<div class=\"duration-bar\"><span style=\"width:{width:.1f}%\"></span></div>"
                f"<p class=\"meta\">{escape(str(node.get('type', '')))} · {escape(format_duration(elapsed))}</p>"
                "</article>"
            )
        lanes.append(
            "<details class=\"rule-lane\" open>"
            "<summary>"
            f"<span><strong>规则 {escape(rule_code)}</strong><em>并行分支处理链路</em></span>"
            f"<span class=\"lane-total\">累计 {escape(format_duration(total))}</span>"
            "</summary>"
            f"<div class=\"node-steps\">{''.join(steps)}</div>"
            "</details>"
        )
    return "<div class=\"parallel-lanes\">" + "".join(lanes) + "</div>"


def render_node_rows(nodes):
    if not nodes:
        return "<tr><td colspan=\"5\" class=\"empty\">没有节点记录。</td></tr>"
    return "".join(
        "<tr>"
        f"<td>{escape(str(node.get('title', '')))}</td>"
        f"<td>{escape(str(node.get('type', '')))}</td>"
        f"<td>{escape(str(node.get('status', '')))}</td>"
        f"<td>{escape(str(node.get('elapsedSeconds', '')))}</td>"
        f"<td><pre>{escape(node.get('outputs'))}</pre></td>"
        "</tr>"
        for node in nodes
    )


def render_html(case_dir, record, workflow_run_id):
    case = get_case_metadata(case_dir)
    metadata = case.get("metadata", {})
    raw_input = case.get("raw_input", {})
    parsed_input = case.get("parsed_input", {})
    certification = parsed_input.get("certification_list") if isinstance(parsed_input, dict) else {}
    structured_input = case.get("dify_payload", {})
    command = case.get("terminal_command") or record.get("terminalCommand", "")
    response = record.get("response") if isinstance(record.get("response"), dict) else {}
    nodes = finished_nodes(record)
    final_outputs = record.get("finalOutputs") if isinstance(record.get("finalOutputs"), dict) else {}
    final_result = str(final_outputs.get("finalResult") or ("运行失败" if record.get("error") else "未识别"))
    rule_results = final_outputs.get("ruleResults") if isinstance(final_outputs.get("ruleResults"), list) else []
    failed_count = sum(1 for rule in rule_results if isinstance(rule, dict) and "不通过" in str(rule.get("ruleResult", "")))
    node_rows = render_node_rows(nodes)
    rule_overview = render_rule_overview(final_outputs, certification)
    parallel_nodes = render_parallel_rule_nodes(nodes)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AIRS 智能审核 Dify 调用记录</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: oklch(0.965 0.008 235);
      --surface: oklch(0.992 0.004 235);
      --surface-2: oklch(0.976 0.007 235);
      --surface-3: oklch(0.947 0.01 235);
      --ink: oklch(0.245 0.026 244);
      --muted: oklch(0.515 0.027 244);
      --faint: oklch(0.665 0.02 244);
      --line: oklch(0.883 0.015 235);
      --line-strong: oklch(0.81 0.018 235);
      --accent: oklch(0.49 0.105 238);
      --accent-ink: oklch(0.31 0.086 238);
      --accent-soft: oklch(0.93 0.035 238);
      --good: oklch(0.46 0.095 154);
      --good-soft: oklch(0.94 0.04 154);
      --bad: oklch(0.51 0.15 28);
      --bad-soft: oklch(0.94 0.045 28);
      --warn: oklch(0.58 0.11 72);
      --warn-soft: oklch(0.95 0.045 72);
      --shadow: 0 18px 44px oklch(0.34 0.03 240 / 0.08);
      --shadow-tight: 0 8px 22px oklch(0.34 0.03 240 / 0.06);
      --radius: 10px;
      --radius-sm: 7px;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background:
        linear-gradient(180deg, oklch(0.982 0.008 235), var(--bg) 360px);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      line-height: 1.56;
      text-rendering: optimizeLegibility;
    }}
    .page {{ width: min(1480px, calc(100% - 36px)); margin: 0 auto; padding: 22px 0 56px; }}
    .hero, .panel, .metric, .side-nav, .rule-card, .sub-panel {{
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
      box-shadow: var(--shadow-tight);
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0,1fr) auto;
      gap: 20px;
      align-items: center;
      padding: 22px 24px;
    }}
    h1,h2,h3,h4,p {{ margin: 0; }}
    h1 {{ font-size: 25px; line-height: 1.2; font-weight: 780; letter-spacing: 0; }}
    h2 {{ font-size: 19px; line-height: 1.25; margin-bottom: 8px; font-weight: 760; }}
    h3 {{ font-size: 16px; line-height: 1.42; font-weight: 730; }}
    h4 {{ font-size: 13px; line-height: 1.3; margin-bottom: 8px; font-weight: 760; }}
    .section-subtitle {{ margin-top:18px; }}
    .sub,.meta,.eyebrow {{ color: var(--muted); font-size: 13px; }}
    .eyebrow {{ font-weight: 800; letter-spacing: .01em; }}
    .status-card {{
      min-width: 178px;
      display: grid;
      align-content: center;
      gap: 4px;
      padding: 16px 18px;
      border-radius: var(--radius);
      background: var(--surface-2);
      border: 1px solid var(--line-strong);
    }}
    .status-card span {{ color: var(--muted); font-size: 13px; font-weight: 760; }}
    .status-card strong {{ font-size: 30px; line-height: 1.05; letter-spacing: 0; }}
    .status-card.good {{ background: var(--good-soft); border-color: oklch(0.78 0.07 154); }}
    .status-card.good strong {{ color: var(--good); }}
    .status-card.bad {{ background: var(--bad-soft); border-color: oklch(0.82 0.08 28); }}
    .status-card.bad strong {{ color: var(--bad); }}
    .status-card.warn strong {{ color: var(--warn); }}
    .layout {{ display: grid; grid-template-columns: 216px minmax(0,1fr); gap: 16px; margin-top: 16px; align-items: start; }}
    .side-nav {{ position: sticky; top: 16px; padding: 10px; display: grid; gap: 4px; box-shadow: none; }}
    .nav-group {{ display:grid; gap:4px; }}
    .nav-group + .nav-group {{ margin-top:12px; padding-top:12px; border-top:1px solid var(--line); }}
    .nav-group-title {{ padding:6px 10px 4px; color:var(--muted); font-size:12px; font-weight:820; }}
    .side-nav a {{
      display: block;
      padding: 10px 11px;
      border-radius: var(--radius-sm);
      color: var(--muted);
      text-decoration: none;
      font-size: 14px;
      font-weight: 720;
      outline: none;
    }}
    .side-nav a:hover, .side-nav a:focus-visible {{ background: var(--accent-soft); color: var(--accent-ink); }}
    .content {{ min-width: 0; display: grid; gap: 16px; }}
    .panel {{ padding: 20px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; margin-top: 14px; }}
    .metric {{ padding: 13px 14px; box-shadow: none; background: var(--surface-2); }}
    .metric strong {{ display:block; font-size:22px; line-height:1.1; font-weight:780; }}
    .metric span {{ color: var(--muted); font-size: 13px; }}
    .pill,.value-pill {{
      display:inline-flex;
      align-items:center;
      min-height:24px;
      padding:3px 9px;
      border-radius:999px;
      font-size:12px;
      font-weight:800;
      white-space: nowrap;
      border: 1px solid transparent;
    }}
    .pill.good {{ background:var(--good-soft); color:var(--good); border-color: oklch(0.82 0.055 154); }}
    .pill.bad {{ background:var(--bad-soft); color:var(--bad); border-color: oklch(0.84 0.07 28); }}
    .pill.warn {{ background:var(--warn-soft); color:var(--warn); border-color: oklch(0.86 0.065 72); }}
    .value-pill {{ background:var(--accent-soft); color:var(--accent-ink); border-color: oklch(0.84 0.045 238); }}
    .summary-grid {{ display:grid; grid-template-columns: 1.1fr .9fr; gap:10px; margin-top:12px; }}
    .summary-box {{ border:1px solid var(--line); border-radius:var(--radius-sm); padding:14px; background:var(--surface-2); }}
    .summary-box p {{ max-width: 74ch; }}
    .rule-overview-list {{ display:grid; gap:10px; margin-top:12px; }}
    .overview-rule {{ border:1px solid var(--line); border-radius:var(--radius); background:var(--surface); overflow:hidden; }}
    .overview-rule summary {{ display:grid; grid-template-columns:auto minmax(0,1fr) auto; gap:12px; align-items:center; padding:13px 14px; cursor:pointer; }}
    .overview-rule summary strong {{ display:block; font-size:14px; }}
    .overview-rule summary em {{
      display:inline-flex;
      margin-top:5px;
      padding:3px 8px;
      border-radius:999px;
      background:var(--accent-soft);
      color:var(--accent-ink);
      font-style:normal;
      font-size:12px;
      font-weight:800;
    }}
    .overview-rule-body {{ display:grid; grid-template-columns: 1.25fr 1fr; gap:10px; padding:0 14px 14px; border-top:1px solid var(--line); }}
    .overview-rule-body > div {{ padding:12px; border-radius:var(--radius-sm); background:var(--surface-2); }}
    .overview-rule-body p {{ max-width: 75ch; }}
    .logic-topology {{ margin-top:12px; padding:14px; border:1px solid var(--line); border-radius:var(--radius); background:var(--surface-2); }}
    .logic-tree, .logic-tree ul {{ list-style:none; margin:10px 0 0; padding-left:18px; }}
    .logic-tree > li {{ margin-top:0; }}
    .logic-group, .logic-rule-ref {{ position:relative; margin:8px 0; }}
    .logic-group::before, .logic-rule-ref::before {{ content:""; position:absolute; left:-12px; top:13px; width:8px; border-top:1px solid var(--line-strong); }}
    .logic-operator {{ display:inline-flex; padding:4px 9px; border-radius:999px; background:var(--accent-soft); color:var(--accent-ink); font-size:12px; font-weight:800; }}
    .logic-rule-ref {{ display:grid; grid-template-columns:auto minmax(0,1fr); gap:8px; align-items:start; padding:8px 10px; border:1px solid var(--line); border-radius:var(--radius-sm); background:var(--surface); }}
    .logic-rule-item {{ display:block; padding:0; border:0; background:transparent; }}
    .logic-rule-detail {{ box-shadow:none; }}
    .logic-rule-detail summary {{ background:var(--surface); }}
    .logic-rule-detail.maintenance-missing {{ border-color:oklch(0.74 0.13 28); background:var(--bad-soft); }}
    .logic-rule-detail.maintenance-missing summary {{ background:oklch(0.965 0.032 28); }}
    .logic-rule-title {{ display:block; margin-top:5px; color:var(--ink); font-size:14px; font-weight:760; }}
    .logic-rule-code {{ font-weight:800; color:var(--accent-ink); white-space:nowrap; }}
    .maintenance-inline {{ display:block; margin-top:6px; color:var(--bad); font-size:12px; font-weight:800; }}
    .maintenance-alert {{ margin-top:12px; padding:12px; border:1px solid oklch(0.78 0.12 28); border-radius:var(--radius-sm); background:var(--bad-soft); color:var(--ink); }}
    .maintenance-alert h4 {{ color:var(--bad); }}
    .maintenance-alert p {{ color:var(--bad); font-weight:720; }}
    .maintenance-alert ul {{ margin:8px 0 0; padding-left:18px; }}
    .maintenance-alert li + li {{ margin-top:6px; }}
    .maintenance-alert li span {{ display:block; margin-top:2px; }}
    .maintenance-alert li em {{ display:block; margin-top:2px; color:var(--bad); font-style:normal; font-weight:800; }}
    .maintenance-alert.compact {{ margin-top:0; }}
    .repo-detail {{ grid-column:1 / -1; }}
    .repo-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-bottom:12px; }}
    .repo-grid > div {{ padding:10px; border-radius:var(--radius-sm); border:1px solid var(--line); background:var(--surface); }}
    .keyword-definition-table pre {{ max-height:220px; min-width:260px; }}
    .rule-card {{ margin-top: 14px; padding: 0; box-shadow: none; overflow:hidden; }}
    .rule-card summary {{ cursor:pointer; }}
    .rule-head {{ display:grid; grid-template-columns:auto minmax(0,1fr) auto; gap:12px; align-items:start; padding:16px; border-bottom:1px solid var(--line); }}
    .rule-head::-webkit-details-marker, .overview-rule summary::-webkit-details-marker {{ display:none; }}
    .rule-head::before, .overview-rule summary::before {{
      content:"展开";
      justify-self:start;
      align-self:start;
      grid-column:1;
      grid-row:1;
      padding:3px 8px;
      border-radius:999px;
      background:var(--surface-3);
      color:var(--muted);
      font-size:12px;
      font-weight:800;
      border:1px solid oklch(0.72 0.11 238);
      background:var(--accent-soft);
      color:var(--accent-ink);
    }}
    .rule-card[open] > .rule-head::before, .overview-rule[open] > summary::before {{ content:"收起"; }}
    .rule-head > div, .overview-rule summary > span:first-of-type {{ grid-column:2; }}
    .rule-head > .pill {{ grid-column:3; grid-row:1; }}
    .summary-actions {{ grid-column:3; grid-row:1; display:flex; flex-direction:column; gap:8px; align-items:flex-end; }}
    .process-link {{ cursor:pointer; border:1px solid oklch(0.72 0.11 238); background:var(--accent-soft); color:var(--accent-ink); border-radius:999px; padding:5px 10px; font-size:12px; font-weight:800; }}
    .process-link:hover, .process-link:focus-visible {{ background:oklch(0.91 0.045 238); }}
    .rule-grid {{ display:grid; grid-template-columns: 1fr; gap:12px; padding:14px; }}
    .sub-panel {{ padding:14px; box-shadow:none; background:var(--surface-2); }}
    .keyword-card {{ border:1px solid var(--line); border-radius:var(--radius-sm); background:var(--surface); overflow:hidden; }}
    .keyword-card + .keyword-card {{ margin-top:10px; }}
    .keyword-card summary {{ display:flex; justify-content:space-between; gap:12px; align-items:center; padding:11px 12px; cursor:pointer; font-weight:800; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:10px 9px; border-top:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-weight:800; background:var(--surface-3); }}
    tr:hover td {{ background: oklch(0.982 0.006 238); }}
    .evidence-text {{ color:var(--ink); max-width: 82ch; }}
    .decision-box {{ border:1px solid oklch(0.82 0.055 238); background:var(--accent-soft); border-radius:var(--radius-sm); padding:13px; }}
    .decision-line {{ display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:8px; font-weight:800; }}
    .reasoning-detail {{ margin-top:10px; border:1px solid var(--line); border-radius:var(--radius-sm); background:var(--surface); padding:10px 12px; }}
    .reasoning-detail summary {{ cursor:pointer; font-weight:800; color:var(--accent-ink); padding:7px 10px; border-radius:var(--radius-sm); background:var(--accent-soft); border:1px solid oklch(0.72 0.11 238); }}
    .reasoning-detail pre {{ margin-top:10px; max-height:360px; }}
    .suspicion-card {{ border:1px solid oklch(0.84 0.07 28); background:var(--bad-soft); border-radius:var(--radius-sm); padding:13px; white-space:pre-wrap; }}
    .suspicion-card h4 {{ color: var(--bad); }}
    .suspicion-card + .suspicion-card {{ margin-top:10px; }}
    .parallel-lanes {{ display:grid; gap:12px; margin:14px 0; }}
    .rule-lane {{ border:1px solid var(--line); border-radius:var(--radius); background:var(--surface); overflow:hidden; }}
    .rule-lane summary {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:12px; align-items:center; padding:13px 14px; cursor:pointer; }}
    .rule-lane summary strong {{ display:block; }}
    .rule-lane summary em {{ display:block; margin-top:2px; color:var(--muted); font-style:normal; font-size:12px; }}
    .lane-total {{ font-weight:800; color:var(--accent-ink); }}
    .node-steps {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(216px,1fr)); gap:10px; padding:0 14px 14px; border-top:1px solid var(--line); }}
    .node-step {{ padding:12px; border-radius:var(--radius-sm); background:var(--surface-2); border:1px solid var(--line); }}
    .node-step-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:8px; min-height:32px; }}
    .duration-bar {{ height:8px; margin:10px 0 8px; border-radius:999px; background:var(--surface-3); overflow:hidden; }}
    .duration-bar span {{ display:block; height:100%; border-radius:999px; background:var(--accent); }}
    .source-list {{ margin:10px 0 0; padding-left:18px; }}
    .source-list p {{ margin-top:4px; }}
    pre {{
      overflow:auto;
      max-height:520px;
      margin:0;
      padding:12px;
      border-radius:var(--radius-sm);
      background:oklch(0.235 0.025 244);
      color:oklch(0.91 0.018 235);
      font-size:12px;
      line-height:1.55;
      white-space:pre-wrap;
      word-break:break-word;
    }}
    details.raw-block {{ border:1px solid var(--line); border-radius:var(--radius-sm); background:var(--surface); padding:10px 12px; }}
    details.raw-block + details.raw-block {{ margin-top:10px; }}
    details.raw-block summary {{ cursor:pointer; font-weight:800; color:var(--accent-ink); display:inline-flex; padding:7px 10px; border-radius:var(--radius-sm); background:var(--accent-soft); border:1px solid oklch(0.72 0.11 238); }}
    details.raw-block.dev-data {{ border:0; background:transparent; padding:8px 0 0; }}
    details.raw-block.dev-data summary {{ background:transparent; border:0; padding:0; text-decoration:underline; text-underline-offset:3px; }}
    details.raw-block.dev-data pre {{ margin-top:10px; }}
    .empty {{ color:var(--muted); font-size:13px; }}
    :focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    @media (max-width: 980px) {{
      .hero,.layout,.summary-grid,.overview-rule-body {{ grid-template-columns:1fr; }}
      .repo-grid {{ grid-template-columns:1fr; }}
      .side-nav {{ position:static; grid-template-columns:repeat(2,minmax(0,1fr)); }}
      .metrics {{ grid-template-columns:1fr 1fr; }}
    }}
    @media (max-width: 700px) {{
      .page {{ width:calc(100% - 20px); padding-top:12px; }}
      .metrics,.side-nav {{ grid-template-columns:1fr; }}
      .hero {{ grid-template-columns:1fr; padding:18px; }}
      .status-card {{ min-width:0; }}
      .rule-head, .overview-rule summary {{ grid-template-columns:1fr; }}
      .rule-head::before, .overview-rule summary::before, .rule-head > div, .overview-rule summary > span:first-of-type, .rule-head > .pill, .summary-actions {{ grid-column:1; grid-row:auto; align-items:flex-start; }}
      table {{ display:block; overflow-x:auto; white-space:nowrap; }}
      .evidence-text {{ white-space:normal; min-width: 320px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <div>
        <p class="eyebrow">AIRS 智能审核 Dify 调用记录</p>
        <h1>{escape(str(metadata.get('patientName', '未知患者')))} · {escape(str(metadata.get('diseaseName', '未知病种')))}</h1>
        <p class="sub">{escape(record.get('startedAt', ''))} · workflow run id: {escape(workflow_run_id)}</p>
      </div>
      <div class="status-card {status_class(final_result)}"><span>审核结论</span><strong>{escape(final_result)}</strong></div>
    </header>
    <div class="layout">
      <nav class="side-nav" aria-label="结果导航">
        <div class="nav-group">
          <div class="nav-group-title">专家关注</div>
          <a href="#overview">审核结论</a>
          <a href="#rules">AI判断过程</a>
        </div>
        <div class="nav-group">
          <div class="nav-group-title">开发问题排查</div>
          <a href="#nodes">节点时间线</a>
          <a href="#io">请求与入参</a>
          <a href="#raw">完整原始数据</a>
        </div>
      </nav>
      <div class="content">
        <section id="overview" class="panel">
          <h2>审核结论</h2>
          <div class="metrics">
            <div class="metric"><strong>{escape(str(response.get('status', '-')))}</strong><span>HTTP 状态</span></div>
            <div class="metric"><strong>{len(record.get('events', []))}</strong><span>SSE 事件</span></div>
            <div class="metric"><strong>{len(rule_results)}</strong><span>规则数量</span></div>
            <div class="metric"><strong>{failed_count}</strong><span>不通过规则</span></div>
          </div>
          <div class="summary-grid">
            <div class="summary-box"><h4>审核意见</h4><p>{escape(str(final_outputs.get('advice') or '未识别审核意见。'))}</p></div>
            <div class="summary-box"><h4>调用状态</h4><p>{escape('运行失败' if record.get('error') else '运行完成')}</p><p class="meta">{escape(record.get('error') or '')}</p></div>
          </div>
          <h3 class="section-subtitle">规则判定总览</h3>
          {rule_overview}
        </section>
        {render_rule_cards(final_outputs)}
        <section id="nodes" class="panel">
          <h2>节点时间线</h2>
          <p class="sub">规则分支按并行处理链路展示；每个步骤条展示该节点耗时，下面保留完整节点明细。</p>
          {parallel_nodes}
          <details class="raw-block"><summary>完整节点明细</summary><table><thead><tr><th>节点</th><th>类型</th><th>状态</th><th>耗时</th><th>输出</th></tr></thead><tbody>{node_rows}</tbody></table></details>
        </section>
        <section id="io" class="panel">
          <h2>请求与入参</h2>
          <details class="raw-block"><summary>普通终端执行命令</summary><pre>{escape(command)}</pre></details>
          <details class="raw-block"><summary>测试者原始入参</summary><pre>{escape(raw_input)}</pre></details>
          <details class="raw-block"><summary>结构化工作流入参</summary><pre>{escape(structured_input)}</pre></details>
          <details class="raw-block"><summary>请求信息</summary><pre>{escape(record.get('request'))}</pre></details>
          <details class="raw-block"><summary>响应信息</summary><pre>{escape(record.get('response'))}</pre></details>
        </section>
        <section id="raw" class="panel">
          <h2>完整原始数据</h2>
          <details class="raw-block"><summary>最终输出 JSON</summary><pre>{escape(record.get('finalOutputs'))}</pre></details>
          <details class="raw-block"><summary>完整运行记录 JSON</summary><pre>{escape(record)}</pre></details>
        </section>
      </div>
    </div>
  </main>
  <script>
    document.addEventListener('click', function(event) {{
      const trigger = event.target.closest('.process-link');
      if (!trigger) return;
      event.preventDefault();
      event.stopPropagation();
      const ruleCode = trigger.dataset.ruleCode;
      const target = document.getElementById('rule-' + ruleCode);
      if (!target) return;
      document.querySelectorAll('.rule-card').forEach(function(card) {{
        card.open = card === target;
      }});
      target.open = true;
      target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }}, true);
  </script>
</body>
</html>"""


def qc_date_range(start_time, end_time):
    return f"{start_time.strftime('%Y%m%d')}-{end_time.strftime('%Y%m%d')}"


def read_qc_index(index_path):
    path = Path(index_path)
    if not path.exists():
        return {"reports": {}}
    try:
        data = read_json_file(path)
    except Exception:
        return {"reports": {}}
    if not isinstance(data, dict):
        return {"reports": {}}
    data.setdefault("reports", {})
    return data


def extract_qc_outputs(run):
    outputs = run.get("outputs") or run.get("finalOutputs") or {}
    if isinstance(outputs, str):
        parsed = parse_maybe_json(outputs)
        return parsed if isinstance(parsed, dict) else {"text": outputs}
    return outputs if isinstance(outputs, dict) else {}


def extract_qc_inputs(run):
    inputs = run.get("inputs") or {}
    if isinstance(inputs, str):
        parsed = parse_maybe_json(inputs)
        return parsed if isinstance(parsed, dict) else {"text": inputs}
    return inputs if isinstance(inputs, dict) else {}


def parse_nested_json_field(mapping, key):
    if not isinstance(mapping, dict):
        return None
    return parse_maybe_json(mapping.get(key))


def extract_qc_patient_name(inputs):
    for key in ("patientName", "patient_name", "姓名"):
        value = inputs.get(key) if isinstance(inputs, dict) else ""
        if value:
            return str(value)
    materials = parse_nested_json_field(inputs, "material_list")
    if isinstance(materials, list):
        return extract_patient_name(inputs, materials)
    return "未知患者"


def extract_qc_disease_name(inputs):
    certification = parse_nested_json_field(inputs, "certification_list")
    if isinstance(certification, dict):
        disease = certification.get("meta", {}).get("chronicDiseaseName")
        if disease:
            return str(disease)
    if isinstance(inputs, dict):
        return str(inputs.get("chronicDiseaseName") or "未知病种")
    return "未知病种"


def qc_final_result(run, outputs):
    return str(outputs.get("finalResult") or outputs.get("reviewResult") or run.get("status") or "未识别")


def qc_report_metadata(log_item, run_id):
    run = workflow_log_run(log_item)
    inputs = extract_qc_inputs(run)
    outputs = extract_qc_outputs(run)
    created_at = parse_dify_time(run.get("created_at") or run.get("createdAt"))
    audit_time = display_timestamp(created_at) if created_at else ""
    audit_stamp = compact_timestamp(created_at) if created_at else "未知时间"
    patient_name = extract_qc_patient_name(inputs)
    disease_name = extract_qc_disease_name(inputs)
    final_result = qc_final_result(run, outputs)
    filename = "_".join(
        sanitize_path_part(part, fallback)
        for part, fallback in (
            (audit_stamp, "未知时间"),
            (patient_name, "未知患者"),
            (disease_name, "未知病种"),
            (final_result, "未识别"),
            (run_id, "no-workflowrunid"),
        )
    ) + "_qc.html"
    return {
        "run_id": run_id,
        "patient_name": patient_name,
        "disease_name": disease_name,
        "audit_time": audit_time,
        "audit_stamp": audit_stamp,
        "final_result": final_result,
        "filename": filename,
        "status": str(run.get("status", "")),
    }


def count_qc_suspicions(rule_results):
    total = 0
    for rule in rule_results:
        if isinstance(rule, dict) and isinstance(rule.get("suspicionList"), list):
            total += len(rule["suspicionList"])
    return total


def render_qc_rule_rows(rule_results):
    if not rule_results:
        return "<tr><td colspan=\"4\" class=\"empty\">没有规则明细。</td></tr>"
    rows = []
    for rule in rule_results:
        if not isinstance(rule, dict):
            continue
        suspicions = rule.get("suspicionList") if isinstance(rule.get("suspicionList"), list) else []
        suspicion_text = "；".join(
            str(item.get("suspicionType") or item.get("detail") or "")
            for item in suspicions
            if isinstance(item, dict)
        )
        rows.append(
            "<tr>"
            f"<td>{escape(str(rule.get('ruleCode', '')))}</td>"
            f"<td><span class=\"pill {status_class(rule.get('ruleResult'))}\">{escape(str(rule.get('ruleResult', '未识别')))}</span></td>"
            f"<td>{escape(str(rule.get('reasoningContent') or rule.get('reason') or ''))}</td>"
            f"<td>{escape(suspicion_text)}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan=\"4\" class=\"empty\">没有规则明细。</td></tr>"


def render_qc_report(env, log_item, run_id):
    run = workflow_log_run(log_item)
    outputs = extract_qc_outputs(run)
    inputs = extract_qc_inputs(run)
    metadata = qc_report_metadata(log_item, run_id)
    created_at = parse_dify_time(run.get("created_at") or run.get("createdAt"))
    finished_at = parse_dify_time(run.get("finished_at") or run.get("finishedAt"))
    case = {
        "metadata": {
            "patientName": metadata["patient_name"],
            "diseaseName": metadata["disease_name"],
            "recordedAt": metadata["audit_time"],
            "timeZone": "Asia/Shanghai",
            "sourceInput": f"dify logs · {env.get('key')}",
            "environment": env.get("key"),
        },
        "raw_input": inputs,
        "parsed_input": {
            "certification_list": parse_nested_json_field(inputs, "certification_list"),
            "material_list": parse_nested_json_field(inputs, "material_list"),
        },
        "dify_payload": {
            "inputs": inputs,
            "response_mode": DEFAULT_RESPONSE_MODE,
            "user": DEFAULT_USER,
        },
        "terminal_command": (
            f"python3 dify_airs_runner.py qc-report --env {env.get('key')} "
            f"--start {metadata['audit_time'] or ''}"
        ),
    }
    record = {
        "startedAt": display_timestamp(created_at) if created_at else "",
        "endedAt": display_timestamp(finished_at) if finished_at else "",
        "timeZone": "Asia/Shanghai",
        "caseMetadata": case["metadata"],
        "terminalCommand": case["terminal_command"],
        "request": {
            "method": "GET",
            "url": f"{str(env.get('api_base', '')).rstrip('/')}/workflows/run/{run_id}",
            "headers": {"Authorization": "Bearer ***", "Content-Type": "application/json"},
            "body": None,
        },
        "response": {
            "status": run.get("status"),
            "reason": "",
            "headers": {},
            "body": {
                "total_tokens": run.get("total_tokens"),
                "total_steps": run.get("total_steps"),
                "environment": {"key": env.get("key"), "label": env.get("label")},
            },
        },
        "events": [],
        "nodeRuns": qc_node_runs(run, outputs),
        "finalOutputs": outputs,
        "error": {"type": "DifyWorkflowError", "message": str(run.get("error"))} if run.get("error") else None,
    }
    return render_html_from_case(case, record, run_id)


def render_html_from_case(case, record, workflow_run_id):
    original_get_case_metadata = get_case_metadata
    try:
        globals()["get_case_metadata"] = lambda _case_dir: case
        return render_html(SCRIPT_DIR, record, workflow_run_id)
    finally:
        globals()["get_case_metadata"] = original_get_case_metadata


def qc_node_runs(run, outputs):
    if isinstance(run.get("nodeRuns"), list):
        return run["nodeRuns"]
    return [
        {
            "id": str(run.get("id") or ""),
            "title": "Dify 工作流运行",
            "type": "workflow",
            "status": run.get("status") or "",
            "elapsedSeconds": run.get("elapsed_time") or run.get("elapsedTime"),
            "inputs": None,
            "processData": None,
            "outputs": outputs,
        }
    ]


def write_qc_index_page(output_dir, env, range_label, generated_reports):
    links = []
    for item in generated_reports:
        links.append(
            "<tr>"
            f"<td>{escape(item['patient_name'])}</td>"
            f"<td>{escape(item['disease_name'])}</td>"
            f"<td>{escape(item['audit_time'])}</td>"
            f"<td>{escape(item['final_result'])}</td>"
            f"<td>{escape(item['run_id'])}</td>"
            f"<td><a href=\"{escape(item['filename'])}\">打开报告</a></td>"
            "</tr>"
        )
    body = "".join(links) or "<tr><td colspan=\"6\">本次没有新增报告。</td></tr>"
    html_text = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" /><title>AIRS Dify 质控报告索引</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;background:#f5f7fa;color:#1f2937;margin:0}}main{{width:min(1000px,calc(100% - 32px));margin:0 auto;padding:24px 0}}section{{background:#fff;border:1px solid #d8dee8;border-radius:10px;padding:18px 20px}}table{{width:100%;border-collapse:collapse}}th,td{{border-top:1px solid #e2e8f0;padding:9px;text-align:left}}a{{color:#1d4ed8}}</style></head>
<body><main><section><h1>AIRS Dify 质控报告索引</h1><p>{escape(str(env.get('label')))} · {escape(range_label)}</p><table><thead><tr><th>患者姓名</th><th>申请病种</th><th>发起审核时间</th><th>智能审核结果</th><th>Workflow Run ID</th><th>报告</th></tr></thead><tbody>{body}</tbody></table></section></main></body></html>"""
    (output_dir / "index.html").write_text(html_text, encoding="utf-8")


def write_qc_reports(env, logs, output_root, start_time, end_time):
    env_key = sanitize_path_part(env.get("key") or DEFAULT_ENV, DEFAULT_ENV)
    range_label = qc_date_range(start_time, end_time)
    env_dir = Path(output_root) / env_key
    output_dir = env_dir / range_label
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = env_dir / "qc-report-index.json"
    index = read_qc_index(index_path)
    created = 0
    skipped = 0
    generated_reports = []
    for item in logs:
        run_id = workflow_run_id_from_log(item)
        if not run_id:
            continue
        key = f"{env_key}:{run_id}"
        metadata = qc_report_metadata(item, run_id)
        report_path = output_dir / metadata["filename"]
        previous_value = index["reports"].get(key, "")
        previous_path = Path(previous_value) if previous_value else None
        same_template = index.get("templateVersion") == QC_REPORT_TEMPLATE_VERSION
        if key in index["reports"] and previous_path.name == report_path.name and report_path.exists() and same_template:
            skipped += 1
            generated_reports.append(metadata)
            continue
        if previous_path and previous_path.exists() and previous_path != report_path:
            previous_path.unlink()
        report_path.write_text(render_qc_report(env, item, run_id), encoding="utf-8")
        index["reports"][key] = str(report_path)
        created += 1
        generated_reports.append(metadata)
    index["updatedAt"] = display_timestamp(now_local())
    index["templateVersion"] = QC_REPORT_TEMPLATE_VERSION
    index["environment"] = {"key": env.get("key"), "label": env.get("label"), "api_base": env.get("api_base")}
    write_json_file(index_path, index)
    write_qc_index_page(output_dir, env, range_label, generated_reports)
    return {"created": created, "skipped": skipped, "output_dir": output_dir, "index_path": index_path}


def parse_qc_time_range(start_value, end_value, days, now=None):
    now = now or now_local()
    end_time = parse_local_time(end_value) if end_value else now
    start_time = parse_local_time(start_value) if start_value else end_time - timedelta(days=max(1, int(days)))
    if start_time > end_time:
        raise RuntimeError("质控查询开始时间不能晚于结束时间。")
    return start_time, end_time


def command_prepare_input(args):
    env_key = getattr(args, "env", "") or ""
    output_root = SCRIPT_DIR / "userinput" / env_key if env_key else SCRIPT_DIR / "userinput"
    result = prepare_input_file(Path(args.input), output_root, env_key=env_key)
    print(f"已生成结构化入参：{result.input_path}")
    print(f"患者名称：{result.patient_name}")
    print(f"申请病种：{result.disease_name}")
    print("\n普通终端执行命令：")
    print(result.terminal_command)


def command_run(args):
    case_dir, case_record = load_case_input(Path(args.case_dir))
    env = load_environment(args.env)
    api_key = args.api_key or env["api_key"]
    api_base = args.api_base or env["api_base"]
    response_mode = args.response_mode or DEFAULT_RESPONSE_MODE
    call_time = now_local()
    record = call_dify_workflow(case_record, api_base, api_key, response_mode, args.transport)
    output_dir, raw_path, html_path = write_result_record(case_dir, record, call_time)
    print(f"结果目录：{output_dir}")
    print(f"原始结果：{raw_path}")
    print(f"HTML 结果：{html_path}")
    hint = get_run_error_hint(record)
    if hint:
        print(f"错误提示：{hint}")


def command_qc_report(args):
    env = load_environment(args.env)
    start_time, end_time = parse_qc_time_range(args.start, args.end, args.days)
    logs = fetch_workflow_logs(env, start_time, end_time, args.page_size)
    enriched = []
    for item in logs:
        run_id = workflow_run_id_from_log(item)
        detail = fetch_workflow_run_detail(env, run_id) if run_id else {}
        if detail:
            merged = dict(workflow_log_run(item))
            merged.update(detail)
            enriched.append(merged)
        else:
            enriched.append(item)
    result = write_qc_reports(env, enriched, SCRIPT_DIR / "qc_reports", start_time, end_time)
    print(f"质控报告目录：{result['output_dir']}")
    print(f"新增报告：{result['created']}")
    print(f"跳过已生成：{result['skipped']}")
    print(f"质控索引：{result['index_path']}")


def command_render_html(args):
    record_path = Path(args.record)
    record = read_json_file(record_path)
    case_dir = Path(args.case_dir) if args.case_dir else record_path.parent.parent
    workflow_run_id = sanitize_path_part(find_workflow_run_id(record), "no-workflowrunid")
    html_path = record_path.with_name(record_path.name.replace("_raw-result.json", "_result.html"))
    html_path.write_text(render_html(case_dir, record, workflow_run_id), encoding="utf-8")
    print(f"HTML 结果：{html_path}")


def build_parser():
    parser = argparse.ArgumentParser(description="AIRS 智能审核 Dify 工作流测试工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-input", help="结构化测试者入参并生成可执行命令")
    prepare.add_argument("--input", required=True, help="测试者提供的原始入参 JSON")
    prepare.add_argument("--env", default=DEFAULT_ENV, help="环境标识，例如 test/prod；默认 test")
    prepare.set_defaults(func=command_prepare_input)

    run = subparsers.add_parser("run", help="调用 AIRS 智能审核 Dify 工作流")
    run.add_argument("--case-dir", required=True, help="prepare-input 生成的 userinput 子目录")
    run.add_argument("--env", default=DEFAULT_ENV, help="环境标识，例如 test/prod；默认 test")
    run.add_argument("--api-base", default="", help="Dify API base；不传时从环境配置读取")
    run.add_argument("--api-key", default="", help="Dify API Key；不传时从环境配置读取")
    run.add_argument("--response-mode", default=DEFAULT_RESPONSE_MODE, choices=("streaming", "blocking"))
    run.add_argument("--transport", default="curl", choices=("curl", "urllib"), help="调用传输方式，默认 curl")
    run.set_defaults(func=command_run)

    render = subparsers.add_parser("render-html", help="根据 raw-result.json 重新生成 HTML")
    render.add_argument("--record", required=True, help="raw-result.json 文件")
    render.add_argument("--case-dir", default="", help="可选：对应 case 目录")
    render.set_defaults(func=command_render_html)

    qc = subparsers.add_parser("qc-report", help="查询最近几天 Dify 调用记录并生成逐次质控 HTML")
    qc.add_argument("--env", default=DEFAULT_ENV, help="环境标识，例如 test/prod；默认 test")
    qc.add_argument("--days", type=int, default=3, help="查询最近几天调用记录；默认 3")
    qc.add_argument("--start", default="", help="精确开始时间，例如 2026-05-09T00:00:00+08:00")
    qc.add_argument("--end", default="", help="精确结束时间；不传则为当前时间")
    qc.add_argument("--page-size", type=int, default=100, help="每页拉取数量；默认 100")
    qc.set_defaults(func=command_qc_report)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
