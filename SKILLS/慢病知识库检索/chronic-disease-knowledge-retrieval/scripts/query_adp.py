#!/usr/bin/env python3
"""Query a Tencent ADP knowledge application over HTTP SSE."""

import argparse
import http.client
import json
import math
import os
import queue
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


MAX_SSE_EVENTS = 1000
MAX_SSE_BYTES = 5 * 1024 * 1024
_CLOSE_REQUESTS = queue.Queue(maxsize=1)


def _close_worker():
    while True:
        response, finished = _CLOSE_REQUESTS.get()
        try:
            response.close()
        except Exception:
            pass
        finally:
            finished.set()


_CLOSE_THREAD = threading.Thread(target=_close_worker, daemon=True)
_CLOSE_THREAD.start()


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


def _reject_json_constant(value):
    raise ValueError("non-finite JSON constant")


def _parse_sse_data(lines):
    if not lines:
        return None
    try:
        event = json.loads(
            "\n".join(lines),
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as error:
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


def _bounded_lines(stream, deadline):
    messages = queue.Queue(maxsize=1)
    stopped = threading.Event()

    def offer(kind, value=None):
        while not stopped.is_set():
            try:
                messages.put((kind, value), timeout=0.01)
                return True
            except queue.Full:
                continue
        return False

    def read_lines():
        try:
            if hasattr(stream, "readline"):
                while not stopped.is_set():
                    line = stream.readline(MAX_SSE_BYTES + 1)
                    if line in (b"", ""):
                        offer("eof")
                        return
                    if not offer("line", line):
                        return
            else:
                for line in stream:
                    if not offer("line", line):
                        return
                offer("eof")
        except Exception as error:
            offer("error", error)

    reader = threading.Thread(target=read_lines, daemon=True)
    reader.start()
    try:
        while True:
            wait_seconds = None
            if deadline is not None:
                wait_seconds = deadline - time.monotonic()
                if wait_seconds <= 0:
                    raise AdPError(
                        "ADP SSE 读取超时",
                        error_type="timeout",
                    )
            try:
                kind, value = messages.get(timeout=wait_seconds)
            except queue.Empty as error:
                raise AdPError(
                    "ADP SSE 读取超时",
                    error_type="timeout",
                ) from error
            if kind == "eof":
                return
            if kind == "error":
                raise value
            yield value
    finally:
        stopped.set()


def read_sse(stream, deadline=None):
    data_lines = []
    byte_count = 0
    event_count = 0
    for raw_line in _bounded_lines(stream, deadline):
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
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return None


def _json_safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _json_safe(item)
            for key, item in value.items()
            if isinstance(key, str)
        }
    return None


def collect_result(query, events):
    answer = ""
    knowledge = []
    workflow = {"name": "", "run_id": "", "outputs": []}
    request_id = None
    session_id = None
    bot_reply_incomplete = False
    token_success = False
    reference_types = {1: "qa", 2: "document", 4: "web"}

    for event_name, event in events:
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            raise AdPError("SSE 事件 payload 格式无效")
        if "request_id" in payload or "request_id" in event:
            value = (
                payload["request_id"]
                if "request_id" in payload
                else event["request_id"]
            )
            request_id = value if isinstance(value, str) else None
        if "session_id" in payload or "session_id" in event:
            value = (
                payload["session_id"]
                if "session_id" in payload
                else event["session_id"]
            )
            session_id = value if isinstance(value, str) else None

        if event_name == "error":
            raise AdPError("ADP 返回错误事件")
        if (
            event_name == "token_stat"
            and payload.get("status_summary") == "failed"
        ):
            raise AdPError("ADP 工作流执行失败")
        if (
            event_name == "token_stat"
            and payload.get("status_summary") == "success"
        ):
            token_success = True

        if event_name == "reply":
            content = payload.get("content")
            if payload.get("is_from_self") is not True:
                if payload.get("is_final") is False:
                    bot_reply_incomplete = True
                elif payload.get("is_final") is True:
                    bot_reply_incomplete = False
                if isinstance(content, str) and content.strip():
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
                        _json_safe(outputs)
                        if isinstance(outputs, list)
                        else []
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

    if bot_reply_incomplete and not token_success:
        raise AdPError("SSE 在回答完成前结束")
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


def _interrupt_response_socket(response):
    pending = [response]
    seen = set()
    while pending and len(seen) < 16:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, socket.socket):
            try:
                current.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            return
        for name in ("_sock", "sock", "socket", "fp", "raw", "_fp"):
            try:
                nested = getattr(current, name, None)
            except Exception:
                continue
            if nested is not None:
                pending.append(nested)


def _bounded_response_close(response):
    finished = threading.Event()
    try:
        _CLOSE_REQUESTS.put_nowait((response, finished))
    except queue.Full:
        return
    finished.wait(timeout=0.02)


def query_adp(config, query, opener=None, debug=False):
    body = build_request(config, query)
    encoded_body = json.dumps(
        body,
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
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
            _interrupt_response_socket(response)
            _bounded_response_close(response)
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
    query = sys.stdin.readline() if args.query_stdin else args.query

    try:
        config = load_config(args.config)
        result = query_adp(config, query, debug=args.debug)
    except (ConfigError, AdPError) as error:
        result = {
            "ok": False,
            "error_type": error.error_type,
            "message": str(error),
        }
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 1
    except (socket.timeout, TimeoutError):
        result = {
            "ok": False,
            "error_type": "timeout",
            "message": "ADP 请求超时",
        }
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 1

    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
