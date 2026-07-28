#!/usr/bin/env python3
"""Query a Tencent ADP knowledge application over HTTP SSE."""

import argparse
import http.client
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


class ConfigError(Exception):
    def __init__(self, message, error_type="config"):
        super().__init__(message)
        self.error_type = error_type


class AdPError(Exception):
    def __init__(self, message, error_type="sse"):
        super().__init__(message)
        self.error_type = error_type


def load_config(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            config = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError("无法读取有效的配置文件") from error

    if not isinstance(config, dict):
        raise ConfigError("配置文件必须是 JSON 对象")
    for name in ("chat_url", "app_key_env"):
        if not isinstance(config.get(name), str) or not config[name].strip():
            raise ConfigError("配置缺少有效字段: " + name)

    chat_url = config["chat_url"].strip()
    try:
        parsed_url = urllib.parse.urlparse(chat_url)
        hostname = parsed_url.hostname
    except ValueError as error:
        raise ConfigError("配置字段无效: chat_url") from error
    if parsed_url.scheme not in ("http", "https") or not hostname:
        raise ConfigError("配置字段无效: chat_url")
    config["chat_url"] = chat_url

    if "timeout_seconds" in config:
        timeout = config["timeout_seconds"]
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not timeout > 0
        ):
            raise ConfigError("配置字段无效: timeout_seconds")

    if "streaming_throttle" in config:
        throttle = config["streaming_throttle"]
        if (
            isinstance(throttle, bool)
            or not isinstance(throttle, int)
            or not 1 <= throttle <= 100
        ):
            raise ConfigError("配置字段无效: streaming_throttle")
    return config


def build_request(config, query):
    if not isinstance(query, str) or not query.strip():
        raise ConfigError("查询内容不能为空")
    query = query.strip()

    env_name = config.get("app_key_env", "ADP_APP_KEY")
    if not isinstance(env_name, str) or not env_name.strip():
        raise ConfigError("配置缺少有效字段: app_key_env")
    env_name = env_name.strip()
    app_key = os.environ.get(env_name, "").strip()
    if not app_key:
        raise ConfigError("请设置环境变量: " + env_name, error_type="auth")

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


def _parse_sse_data(lines):
    if not lines:
        return None
    try:
        event = json.loads("\n".join(lines))
    except json.JSONDecodeError as error:
        raise AdPError("SSE 事件不是有效 JSON") from error

    if (
        isinstance(event, list)
        and len(event) == 2
        and isinstance(event[0], str)
        and isinstance(event[1], dict)
    ):
        return event[0], event[1]
    if isinstance(event, dict):
        event_name = event.get("type")
        if isinstance(event_name, str) and isinstance(
            event.get("payload"), dict
        ):
            return event_name, event
    raise AdPError("SSE 事件格式无效")


def read_sse(stream):
    data_lines = []
    for raw_line in stream:
        try:
            line = (
                raw_line.decode("utf-8")
                if isinstance(raw_line, bytes)
                else raw_line
            )
        except UnicodeDecodeError as error:
            raise AdPError("SSE 数据不是有效 UTF-8") from error
        line = line.rstrip("\r\n")
        if not line:
            parsed = _parse_sse_data(data_lines)
            data_lines = []
            if parsed is not None:
                yield parsed
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            data_lines.append(value)


def collect_result(query, events):
    answer = ""
    knowledge = []
    workflow = {"name": "", "run_id": "", "outputs": []}
    request_id = None
    session_id = None
    finality_signaled = False
    final_reply_seen = False
    reference_types = {1: "qa", 2: "document", 4: "web"}

    for event_name, event in events:
        payload = event.get("payload", {})
        request_id = payload.get("request_id") or event.get(
            "request_id"
        ) or request_id
        session_id = payload.get("session_id") or event.get(
            "session_id"
        ) or session_id

        if event_name == "error":
            raise AdPError("ADP 返回错误事件")
        if (
            event_name == "token_stat"
            and payload.get("status_summary") == "failed"
        ):
            raise AdPError("ADP 工作流执行失败")

        if event_name == "reply":
            if "is_final" in payload:
                finality_signaled = True
                if payload["is_final"] is True:
                    final_reply_seen = True
            content = payload.get("content")
            if isinstance(content, str) and content.strip():
                answer = content
            work_flow = payload.get("work_flow")
            if isinstance(work_flow, dict):
                if work_flow.get("workflow_name") is not None:
                    workflow["name"] = work_flow["workflow_name"]
                if work_flow.get("workflow_run_id") is not None:
                    workflow["run_id"] = work_flow["workflow_run_id"]
                if work_flow.get("outputs") is not None:
                    workflow["outputs"] = work_flow["outputs"]

        if event_name == "reference":
            references = payload.get("references", [])
            if not isinstance(references, list):
                continue
            for reference in references:
                if not isinstance(reference, dict):
                    continue
                knowledge.append(
                    {
                        "type": reference_types.get(
                            reference.get("type"), "unknown"
                        ),
                        "title": reference.get("doc_name")
                        or reference.get("name")
                        or "",
                        "content": reference.get("content", ""),
                        "url": reference.get("url", ""),
                        "confidence": reference.get("confidence"),
                    }
                )

    if finality_signaled and not final_reply_seen:
        raise AdPError("SSE 未收到最终回答事件")
    if not answer:
        raise AdPError("未收到最终回答", error_type="empty_result")

    return {
        "ok": True,
        "query": query,
        "answer": answer,
        "knowledge": knowledge,
        "workflow": workflow,
        "meta": {
            "session_id": session_id,
            "request_id": request_id,
            "source": "tencent-adp",
        },
    }


def query_adp(config, query, opener=None, debug=False):
    body = build_request(config, query)
    encoded_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        config["chat_url"],
        data=encoded_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    timeout = config.get("timeout_seconds", 120)
    open_url = opener or urllib.request.urlopen

    try:
        response = open_url(request, timeout=timeout)
        try:
            events = list(read_sse(response))
        finally:
            response.close()
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise AdPError("ADP 身份认证失败", error_type="auth") from error
        raise AdPError("ADP HTTP 请求失败", error_type="network") from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise AdPError("ADP 请求超时", error_type="timeout") from error
        raise AdPError("无法连接 ADP 服务", error_type="network") from error
    except (socket.timeout, TimeoutError) as error:
        raise AdPError("ADP 请求超时", error_type="timeout") from error
    except http.client.HTTPException as error:
        raise AdPError("ADP SSE 响应中断", error_type="network") from error
    except OSError as error:
        raise AdPError("ADP SSE 连接中断", error_type="network") from error

    if debug:
        for event_name, _ in events:
            print("event: " + event_name, file=sys.stderr)
    return collect_result(body["content"], events)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        result = query_adp(config, args.query, debug=args.debug)
    except (ConfigError, AdPError) as error:
        result = {
            "ok": False,
            "error_type": error.error_type,
            "message": str(error),
        }
        print(json.dumps(result, ensure_ascii=False))
        return 1
    except (socket.timeout, TimeoutError):
        result = {
            "ok": False,
            "error_type": "timeout",
            "message": "ADP 请求超时",
        }
        print(json.dumps(result, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
