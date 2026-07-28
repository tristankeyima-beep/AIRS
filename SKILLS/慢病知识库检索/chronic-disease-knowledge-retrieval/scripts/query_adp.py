#!/usr/bin/env python3
"""Query a Tencent ADP knowledge application over HTTP SSE."""

import argparse
import http.client
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


MAX_SSE_EVENTS = 1000
MAX_SSE_BYTES = 5 * 1024 * 1024


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


def _check_deadline(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise AdPError("ADP SSE 读取超时", error_type="timeout")


def read_sse(stream, deadline=None):
    data_lines = []
    byte_count = 0
    event_count = 0
    iterator = iter(stream)
    while True:
        _check_deadline(deadline)
        try:
            raw_line = next(iterator)
        except StopIteration:
            break
        _check_deadline(deadline)
        byte_count += (
            len(raw_line)
            if isinstance(raw_line, bytes)
            else len(raw_line.encode("utf-8"))
        )
        if byte_count > MAX_SSE_BYTES:
            raise AdPError("SSE 响应超过大小限制")
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
                _check_deadline(deadline)
                event_count += 1
                if event_count > MAX_SSE_EVENTS:
                    raise AdPError("SSE 事件数量超过限制")
                yield parsed
                event_name, event = parsed
                payload = event.get("payload", {})
                if (
                    event_name == "token_stat"
                    and isinstance(payload, dict)
                    and payload.get("status_summary")
                    in ("success", "failed")
                ):
                    return
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            data_lines.append(value)


def _string_or_empty(value):
    return value if isinstance(value, str) else ""


def _number_or_none(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def collect_result(query, events):
    answer = ""
    knowledge = []
    workflow = {"name": "", "run_id": "", "outputs": []}
    request_id = None
    session_id = None
    reference_types = {1: "qa", 2: "document", 4: "web"}

    for event_name, event in events:
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            raise AdPError("SSE 事件 payload 格式无效")
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
            content = payload.get("content")
            if (
                payload.get("is_from_self") is not True
                and isinstance(content, str)
                and content.strip()
            ):
                answer = content
            work_flow = payload.get("work_flow")
            if isinstance(work_flow, dict):
                if "workflow_name" in work_flow:
                    workflow["name"] = _string_or_empty(
                        work_flow["workflow_name"]
                    )
                if "workflow_run_id" in work_flow:
                    workflow["run_id"] = _string_or_empty(
                        work_flow["workflow_run_id"]
                    )
                if "outputs" in work_flow:
                    outputs = work_flow["outputs"]
                    workflow["outputs"] = (
                        outputs if isinstance(outputs, list) else []
                    )

        if event_name == "reference":
            references = payload.get("references", [])
            if not isinstance(references, list):
                continue
            for reference in references:
                if not isinstance(reference, dict):
                    continue
                doc_name = _string_or_empty(reference.get("doc_name"))
                name = _string_or_empty(reference.get("name"))
                knowledge.append(
                    {
                        "type": reference_types.get(
                            reference.get("type"), "unknown"
                        ),
                        "title": doc_name or name,
                        "content": _string_or_empty(
                            reference.get("content")
                        ),
                        "url": _string_or_empty(reference.get("url")),
                        "confidence": _number_or_none(
                            reference.get("confidence")
                        ),
                    }
                )

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


def _debug_events(events):
    for event_name, event in events:
        print("event: " + event_name, file=sys.stderr)
        yield event_name, event


def _response_content_type(response):
    content_type = ""
    headers = getattr(response, "headers", None)
    if headers is not None:
        for name, value in headers.items():
            if str(name).lower() == "content-type":
                content_type = value
                break
    if not content_type and hasattr(response, "getheader"):
        content_type = response.getheader("Content-Type", "")
    if not isinstance(content_type, str):
        return ""
    return content_type.split(";", 1)[0].strip().lower()


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
    deadline = time.monotonic() + timeout
    open_url = opener or urllib.request.urlopen

    try:
        response = open_url(request, timeout=timeout)
        try:
            if _response_content_type(response) != "text/event-stream":
                raise AdPError("ADP 响应不是 SSE 事件流")
            events = read_sse(response, deadline=deadline)
            if debug:
                events = _debug_events(events)
            return collect_result(body["content"], events)
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


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument("--query")
    query_group.add_argument("--query-stdin", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    query = sys.stdin.read() if args.query_stdin else args.query

    try:
        config = load_config(args.config)
        result = query_adp(config, query, debug=args.debug)
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
