#!/usr/bin/env python3
import argparse
import html
import json
import re
import ssl
import subprocess
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
README_PATH = SCRIPT_DIR / "README.md"
DEFAULT_API_BASE = "https://dify.hzmarvel.com/v1"
DEFAULT_RESPONSE_MODE = "streaming"
DEFAULT_USER = "dify-airs-workflow-test"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
INPUT_FILE_NAME = "入参.json"


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


def shell_quote(value):
    text = str(value)
    if re.match(r"^[A-Za-z0-9_./:=@%+\-]+$", text):
        return text
    return '"' + re.sub(r'(["\\$`])', r"\\\1", text) + '"'


def build_run_command(case_dir):
    relative_case = case_dir
    try:
        relative_case = case_dir.relative_to(SCRIPT_DIR)
    except ValueError:
        pass
    return (
        f"cd {shell_quote(SCRIPT_DIR)} && "
        f"python3 dify_airs_runner.py run --case-dir {shell_quote(relative_case)}"
    )


def prepare_input_file(input_path, output_root=None, now=None):
    input_path = Path(input_path)
    output_root = Path(output_root) if output_root else SCRIPT_DIR / "userinput"
    now = now or now_local()
    raw_input = read_json_file(input_path)
    inputs, patient_name, disease_name, certification, materials = normalize_inputs(raw_input)

    safe_patient = sanitize_path_part(patient_name, "未知患者")
    safe_disease = sanitize_path_part(disease_name, "未知病种")
    case_dir = output_root / f"{safe_patient}_{safe_disease}_{compact_timestamp(now)}"
    case_dir.mkdir(parents=True, exist_ok=True)
    terminal_command = build_run_command(case_dir)
    payload = {
        "metadata": {
            "patientName": patient_name,
            "diseaseName": disease_name,
            "recordedAt": display_timestamp(now),
            "timeZone": "Asia/Shanghai",
            "sourceInput": str(input_path),
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
            "<details class=\"keyword-card\">"
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


def render_rule_overview(final_outputs, certification):
    rules = final_outputs.get("ruleResults") if isinstance(final_outputs, dict) else []
    if not isinstance(rules, list) or not rules:
        return "<p class=\"empty\">没有规则判定总览。</p>"
    logic_topology = certification.get("logicTopology") if isinstance(certification, dict) else {}
    cards = []
    for index, rule in enumerate(rules, 1):
        if not isinstance(rule, dict):
            continue
        rule_code = str(rule.get("ruleCode") or f"规则{index}")
        result = str(rule.get("ruleResult") or rule.get("reviewResult") or "未识别")
        operators = find_rule_relation(logic_topology, rule_code)
        relation_text = " / ".join(operator_label(item) for item in operators) if operators else "未识别关系"
        cards.append(
            "<details class=\"overview-rule\" open>"
            "<summary>"
            "<span>"
            f"<strong>规则 {escape(rule_code)}</strong>"
            f"<em>{escape(relation_text)}</em>"
            "</span>"
            f"<span class=\"pill {status_class(result)}\">{escape(result)}</span>"
            "</summary>"
            "<div class=\"overview-rule-body\">"
            "<div><h4>规则原文</h4>"
            f"<p>{escape(str(rule.get('ruleContent', '')))}</p></div>"
            "<div><h4>不通过原因</h4>"
            f"<p>{escape(rule_decision_summary(rule))}</p></div>"
            "</div>"
            "</details>"
        )
    return "<div class=\"rule-overview-list\">" + "".join(cards) + "</div>"


def render_rule_cards(final_outputs):
    rules = final_outputs.get("ruleResults") if isinstance(final_outputs, dict) else []
    if not isinstance(rules, list) or not rules:
        return "<section id=\"rules\" class=\"panel\"><h2>规则链路</h2><p class=\"empty\">没有规则审核明细。</p></section>"
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
                "<summary>完整模型推理过程</summary>"
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
            "<section class=\"sub-panel\"><h4>提取规则与精解结果</h4>"
            f"{render_keyword_guides(rule)}</section>"
            "<section class=\"sub-panel\"><h4>逐条认定</h4>"
            "<div class=\"decision-box\">"
            "<div class=\"decision-line\"><span>认定结果</span>"
            f"<span class=\"pill {status_class(result)}\">{escape(result)}</span></div>"
            f"<p>{escape(rule_decision_summary(rule))}</p>"
            "</div>"
            f"{reasoning_block}</section>"
            "<section class=\"sub-panel\"><h4>疑点说明</h4>"
            f"{render_suspicion_list(rule)}</section>"
            "</div></details>"
        )
    return "<section id=\"rules\" class=\"panel\"><h2>规则链路</h2><p class=\"sub\">按规则查看：规则定义、提取证据、逐条认定和疑点来源。</p>" + "".join(cards) + "</section>"


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
    :root {{ --bg:#f3f5f7; --panel:#fff; --ink:#16212c; --muted:#65727d; --line:#d9e2e6; --green:#2f8f6b; --red:#b42318; --amber:#a15c07; --blue:#2f6f9f; --soft-green:#eef8f3; --soft-red:#fff1f0; --soft-amber:#fff8ec; --soft-blue:#eef6fb; }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; }}
    .page {{ width: min(1440px, calc(100% - 32px)); margin: 0 auto; padding: 24px 0 56px; }}
    .hero, .panel, .metric, .side-nav, .rule-card, .sub-panel {{ border: 1px solid var(--line); border-radius: 8px; background: var(--panel); box-shadow: 0 8px 24px rgba(23,33,43,.04); }}
    .hero {{ display: grid; grid-template-columns: minmax(0,1fr) 220px; gap: 16px; padding: 22px; background: linear-gradient(135deg,#fff,var(--soft-blue)); }}
    h1,h2,h3,h4,p {{ margin: 0; }}
    h1 {{ font-size: 26px; line-height: 1.25; }}
    h2 {{ font-size: 18px; margin-bottom: 10px; }}
    h3 {{ font-size: 16px; line-height: 1.45; }}
    h4 {{ font-size: 14px; margin-bottom: 10px; }}
    .section-subtitle {{ margin-top:16px; }}
    .sub,.meta,.eyebrow {{ color: var(--muted); font-size: 13px; }}
    .eyebrow {{ font-weight: 800; letter-spacing: 0; }}
    .status-card {{ display: grid; align-content: center; justify-items: start; padding: 16px; border-radius: 8px; background: #102033; color: #fff; }}
    .status-card strong {{ font-size: 30px; line-height: 1.15; }}
    .layout {{ display: grid; grid-template-columns: 220px minmax(0,1fr); gap: 16px; margin-top: 16px; align-items: start; }}
    .side-nav {{ position: sticky; top: 16px; padding: 12px; display: grid; gap: 8px; }}
    .side-nav a {{ display: block; padding: 9px 10px; border-radius: 7px; color: var(--ink); text-decoration: none; font-size: 14px; }}
    .side-nav a:hover {{ background: var(--soft-blue); }}
    .content {{ min-width: 0; display: grid; gap: 16px; }}
    .panel {{ padding: 18px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-top: 14px; }}
    .metric {{ padding: 14px; box-shadow: none; }}
    .metric strong {{ display:block; font-size:22px; line-height:1.2; }}
    .pill,.value-pill {{ display:inline-flex; align-items:center; min-height:24px; padding:3px 9px; border-radius:999px; font-size:12px; font-weight:800; }}
    .pill.good {{ background:var(--soft-green); color:var(--green); }}
    .pill.bad {{ background:var(--soft-red); color:var(--red); }}
    .pill.warn {{ background:var(--soft-amber); color:var(--amber); }}
    .value-pill {{ background:var(--soft-blue); color:var(--blue); }}
    .summary-grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-top:12px; }}
    .summary-box {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fbfcfd; }}
    .rule-overview-list {{ display:grid; gap:10px; margin-top:14px; }}
    .overview-rule {{ border:1px solid var(--line); border-radius:8px; background:#fff; overflow:hidden; }}
    .overview-rule summary {{ display:grid; grid-template-columns:auto minmax(0,1fr) auto; gap:12px; align-items:center; padding:12px 14px; cursor:pointer; }}
    .overview-rule summary strong {{ display:block; font-size:14px; }}
    .overview-rule summary em {{ display:inline-flex; margin-top:5px; padding:3px 8px; border-radius:999px; background:var(--soft-blue); color:var(--blue); font-style:normal; font-size:12px; font-weight:800; }}
    .overview-rule-body {{ display:grid; grid-template-columns: 1.2fr 1fr; gap:12px; padding:0 14px 14px; border-top:1px solid var(--line); }}
    .overview-rule-body > div {{ padding:12px; border-radius:8px; background:#fbfcfd; }}
    .rule-card {{ margin-top: 14px; padding: 16px; box-shadow: none; }}
    .rule-card summary {{ cursor:pointer; }}
    .rule-head {{ display:grid; grid-template-columns:auto minmax(0,1fr) auto; gap:12px; align-items:start; padding-bottom:14px; border-bottom:1px solid var(--line); }}
    .rule-head::-webkit-details-marker, .overview-rule summary::-webkit-details-marker {{ display:none; }}
    .rule-head::before, .overview-rule summary::before {{ content:"展开"; justify-self:start; align-self:start; grid-column:1; grid-row:1; padding:3px 8px; border-radius:999px; background:#eef1f4; color:var(--muted); font-size:12px; font-weight:800; }}
    .rule-card[open] > .rule-head::before, .overview-rule[open] > summary::before {{ content:"收起"; }}
    .rule-head > div, .overview-rule summary > span:first-of-type {{ grid-column:2; }}
    .rule-head > .pill, .overview-rule summary > .pill {{ grid-column:3; grid-row:1; }}
    .rule-grid {{ display:grid; grid-template-columns: 1fr; gap:12px; margin-top:14px; }}
    .sub-panel {{ padding:14px; box-shadow:none; background:#fbfcfd; }}
    .keyword-card {{ border:1px solid var(--line); border-radius:8px; background:#fff; overflow:hidden; }}
    .keyword-card + .keyword-card {{ margin-top:10px; }}
    .keyword-card summary {{ display:flex; justify-content:space-between; gap:12px; align-items:center; padding:11px 12px; cursor:pointer; font-weight:800; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:9px 8px; border-top:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-weight:800; background:#f8fafb; }}
    .evidence-text {{ color:#263746; }}
    .decision-box {{ border-left:4px solid var(--blue); background:#f7fbfd; border-radius:8px; padding:12px; }}
    .decision-line {{ display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:8px; font-weight:800; }}
    .reasoning-detail {{ margin-top:10px; border:1px solid var(--line); border-radius:8px; background:#fff; padding:10px 12px; }}
    .reasoning-detail summary {{ cursor:pointer; font-weight:800; color:var(--blue); }}
    .reasoning-detail pre {{ margin-top:10px; max-height:360px; }}
    .suspicion-card {{ border-left:4px solid var(--blue); background:#f7fbfd; border-radius:8px; padding:12px; white-space:pre-wrap; }}
    .suspicion-card {{ border-left-color:var(--red); background:#fff8f7; }}
    .suspicion-card + .suspicion-card {{ margin-top:10px; }}
    .parallel-lanes {{ display:grid; gap:12px; margin:14px 0; }}
    .rule-lane {{ border:1px solid var(--line); border-radius:8px; background:#fff; overflow:hidden; }}
    .rule-lane summary {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:12px; align-items:center; padding:12px 14px; cursor:pointer; }}
    .rule-lane summary strong {{ display:block; }}
    .rule-lane summary em {{ display:block; margin-top:2px; color:var(--muted); font-style:normal; font-size:12px; }}
    .lane-total {{ font-weight:800; color:var(--blue); }}
    .node-steps {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:10px; padding:0 14px 14px; border-top:1px solid var(--line); }}
    .node-step {{ padding:12px; border-radius:8px; background:#fbfcfd; border:1px solid var(--line); }}
    .node-step-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:8px; min-height:32px; }}
    .duration-bar {{ height:8px; margin:10px 0 8px; border-radius:999px; background:#e8eef2; overflow:hidden; }}
    .duration-bar span {{ display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,var(--blue),#67a6c9); }}
    .source-list {{ margin:10px 0 0; padding-left:18px; }}
    .source-list p {{ margin-top:4px; }}
    pre {{ overflow:auto; max-height:520px; margin:0; padding:12px; border-radius:8px; background:#0f1720; color:#d8e3ea; font-size:12px; line-height:1.55; white-space:pre-wrap; word-break:break-word; }}
    details.raw-block {{ border:1px solid var(--line); border-radius:8px; background:#fff; padding:10px 12px; }}
    details.raw-block + details.raw-block {{ margin-top:10px; }}
    details.raw-block summary {{ cursor:pointer; font-weight:800; }}
    .empty {{ color:var(--muted); font-size:13px; }}
    @media (max-width: 980px) {{ .hero,.layout,.summary-grid,.rule-grid {{ grid-template-columns:1fr; }} .side-nav {{ position:static; }} .metrics {{ grid-template-columns:1fr 1fr; }} }}
    @media (max-width: 620px) {{ .page {{ width:calc(100% - 20px); }} .metrics {{ grid-template-columns:1fr; }} .rule-head {{ grid-template-columns:1fr; }} }}
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
      <div class="status-card"><span>审核结论</span><strong>{escape(final_result)}</strong></div>
    </header>
    <div class="layout">
      <nav class="side-nav" aria-label="结果导航">
        <a href="#overview">审核结论</a>
        <a href="#rules">规则链路</a>
        <a href="#nodes">节点时间线</a>
        <a href="#io">请求与入参</a>
        <a href="#raw">完整原始数据</a>
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
</body>
</html>"""


def command_prepare_input(args):
    result = prepare_input_file(Path(args.input), SCRIPT_DIR / "userinput")
    print(f"已生成结构化入参：{result.input_path}")
    print(f"患者名称：{result.patient_name}")
    print(f"申请病种：{result.disease_name}")
    print("\n普通终端执行命令：")
    print(result.terminal_command)


def command_run(args):
    case_dir, case_record = load_case_input(Path(args.case_dir))
    api_key = args.api_key or read_api_key_from_readme()
    api_base = args.api_base or DEFAULT_API_BASE
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
    prepare.set_defaults(func=command_prepare_input)

    run = subparsers.add_parser("run", help="调用 AIRS 智能审核 Dify 工作流")
    run.add_argument("--case-dir", required=True, help="prepare-input 生成的 userinput 子目录")
    run.add_argument("--api-base", default=DEFAULT_API_BASE, help="Dify API base")
    run.add_argument("--api-key", default="", help="Dify API Key；不传时从 README.md 读取")
    run.add_argument("--response-mode", default=DEFAULT_RESPONSE_MODE, choices=("streaming", "blocking"))
    run.add_argument("--transport", default="curl", choices=("curl", "urllib"), help="调用传输方式，默认 curl")
    run.set_defaults(func=command_run)

    render = subparsers.add_parser("render-html", help="根据 raw-result.json 重新生成 HTML")
    render.add_argument("--record", required=True, help="raw-result.json 文件")
    render.add_argument("--case-dir", default="", help="可选：对应 case 目录")
    render.set_defaults(func=command_render_html)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
