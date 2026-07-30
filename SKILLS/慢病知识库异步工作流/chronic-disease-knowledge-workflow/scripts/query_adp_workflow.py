#!/usr/bin/env python3
"""Call a Tencent ADP knowledge_qa application through async workflow APIs."""

import argparse
import datetime
import hashlib
import hmac
import json
import math
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


MAX_RESPONSE_BYTES = 5 * 1024 * 1024
FAILED_STATES = {3, 4, 5}


class ConfigError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.error_type = "config"
        self.request_id = None


class WorkflowError(Exception):
    def __init__(self, message, error_type="response", request_id=None):
        super().__init__(message)
        self.error_type = error_type
        self.request_id = request_id


def load_config(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            config = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError("无法读取有效的配置文件") from error

    if not isinstance(config, dict):
        raise ConfigError("配置文件必须是 JSON 对象")

    required = ("api_host", "app_id", "secret_id", "secret_key")
    for name in required:
        value = config.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError("配置缺少有效字段: " + name)
        config[name] = value.strip()

    parsed = urllib.parse.urlparse(config["api_host"])
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ConfigError("配置字段无效: api_host")
    config["api_host"] = (
        parsed.scheme + "://" + parsed.netloc.rstrip("/")
    )

    defaults = {
        "run_env": 1,
        "region": "1",
        "service": "lke",
        "version": "2023-11-30",
        "poll_interval_seconds": 1,
        "timeout_seconds": 120,
    }
    for name, value in defaults.items():
        config.setdefault(name, value)

    if (
        isinstance(config["run_env"], bool)
        or config["run_env"] not in (0, 1)
    ):
        raise ConfigError("配置字段无效: run_env")
    for name in ("region", "service", "version"):
        value = config[name]
        if not isinstance(value, str) or not value.strip():
            raise ConfigError("配置字段无效: " + name)
        config[name] = value.strip()
    for name in ("poll_interval_seconds", "timeout_seconds"):
        value = config[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ConfigError("配置字段无效: " + name)

    return config


def _sha256_hex(value):
    return hashlib.sha256(value).hexdigest()


def _hmac_sha256(key, value):
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


def build_signed_headers(config, action, body, timestamp=None):
    if timestamp is None:
        timestamp = int(time.time())
    timestamp = int(timestamp)

    parsed = urllib.parse.urlparse(config["api_host"])
    host = parsed.netloc.lower()
    content_type = "application/json"
    canonical_headers = (
        "content-type:" + content_type + "\n"
        "host:" + host + "\n"
    )
    signed_headers = "content-type;host"
    canonical_request = (
        "POST\n"
        "/\n"
        "\n"
        + canonical_headers
        + "\n"
        + signed_headers
        + "\n"
        + _sha256_hex(body)
    )

    date = datetime.datetime.fromtimestamp(
        timestamp,
        datetime.timezone.utc,
    ).strftime("%Y-%m-%d")
    service = config["service"]
    credential_scope = date + "/" + service + "/tc3_request"
    string_to_sign = (
        "TC3-HMAC-SHA256\n"
        + str(timestamp)
        + "\n"
        + credential_scope
        + "\n"
        + _sha256_hex(canonical_request.encode("utf-8"))
    )

    secret_date = _hmac_sha256(
        ("TC3" + config["secret_key"]).encode("utf-8"),
        date,
    )
    secret_service = _hmac_sha256(secret_date, service)
    secret_signing = _hmac_sha256(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    authorization = (
        "TC3-HMAC-SHA256 "
        "Credential="
        + config["secret_id"]
        + "/"
        + credential_scope
        + ", SignedHeaders="
        + signed_headers
        + ", Signature="
        + signature
    )
    return {
        "Authorization": authorization,
        "Content-Type": content_type,
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Version": config["version"],
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Region": config["region"],
    }


def _error_type_for_code(code):
    if code.startswith(("AuthFailure", "Unauthorized", "Forbidden")):
        return "auth"
    return "response"


def _unwrap_response(data):
    if not isinstance(data, dict) or not isinstance(
        data.get("Response"),
        dict,
    ):
        raise WorkflowError("ADP 响应格式无效")
    response = data["Response"]
    request_id = response.get("RequestId")
    if not isinstance(request_id, str):
        request_id = None

    error = response.get("Error")
    if isinstance(error, dict):
        code = error.get("Code")
        if not isinstance(code, str) or not code:
            code = "UnknownError"
        raise WorkflowError(
            "ADP 返回错误: " + code,
            error_type=_error_type_for_code(code),
            request_id=request_id,
        )
    return response, request_id


def post_action(config, action, payload):
    try:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise WorkflowError("请求参数无法转换为 JSON") from error

    headers = build_signed_headers(config, action, body)
    request = urllib.request.Request(
        config["api_host"] + "/",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=float(config["timeout_seconds"]),
        ) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        request_id = error.headers.get("X-TC-RequestId")
        try:
            raw = error.read(MAX_RESPONSE_BYTES + 1)
            data = json.loads(raw.decode("utf-8"))
            _unwrap_response(data)
        except WorkflowError:
            raise
        except Exception:
            pass
        error_type = (
            "auth" if error.code in (401, 403) else "http"
        )
        raise WorkflowError(
            "ADP HTTP 请求失败: " + str(error.code),
            error_type=error_type,
            request_id=request_id,
        ) from None
    except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
        reason = getattr(error, "reason", None)
        error_type = (
            "timeout"
            if isinstance(reason, (socket.timeout, TimeoutError))
            or isinstance(error, (socket.timeout, TimeoutError))
            else "http"
        )
        raise WorkflowError(
            "ADP 请求超时"
            if error_type == "timeout"
            else "ADP 服务不可访问",
            error_type=error_type,
        ) from None
    except OSError:
        raise WorkflowError(
            "ADP 服务不可访问",
            error_type="http",
        ) from None

    if len(raw) > MAX_RESPONSE_BYTES:
        raise WorkflowError("ADP 响应超过大小限制")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkflowError("ADP 响应不是有效 JSON") from error
    if not isinstance(data, dict):
        raise WorkflowError("ADP 响应格式无效")
    return data


def _parse_output(value):
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    if value is None or isinstance(
        value,
        (dict, list, int, float, bool),
    ):
        return value
    return str(value)


def _answer_from_output(output):
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        for name in ("answer", "result", "output", "content", "text"):
            if name not in output:
                continue
            value = output[name]
            if isinstance(value, str):
                return value
            return json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
    if output in ("", None):
        return ""
    return json.dumps(
        output,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def query_workflow(
    config,
    query,
    post=None,
    sleep=time.sleep,
    monotonic=time.monotonic,
    visitor_id_factory=None,
):
    if not isinstance(query, str) or not query.strip():
        raise ConfigError("查询内容不能为空")
    query = query.strip()
    if post is None:
        post = post_action
    if visitor_id_factory is None:
        visitor_id_factory = lambda: str(uuid.uuid4())

    started = monotonic()
    create_data = post(
        config,
        "CreateWorkflowRun",
        {
            "AppBizId": config["app_id"],
            "RunEnv": config["run_env"],
            "Query": query,
            "VisitorId": visitor_id_factory(),
        },
    )
    create_response, create_request_id = _unwrap_response(create_data)
    run_id = create_response.get("WorkflowRunId")
    if not isinstance(run_id, str) or not run_id:
        raise WorkflowError(
            "创建工作流后未返回 WorkflowRunId",
            request_id=create_request_id,
        )

    timeout = float(config["timeout_seconds"])
    interval = float(config["poll_interval_seconds"])
    while True:
        if monotonic() - started >= timeout:
            raise WorkflowError(
                "等待 ADP 工作流结果超时",
                error_type="timeout",
                request_id=create_request_id,
            )

        describe_data = post(
            config,
            "DescribeWorkflowRun",
            {
                "AppBizId": config["app_id"],
                "WorkflowRunId": run_id,
            },
        )
        describe_response, request_id = _unwrap_response(describe_data)
        workflow = describe_response.get("WorkflowRun")
        if not isinstance(workflow, dict):
            raise WorkflowError(
                "查询工作流后未返回 WorkflowRun",
                request_id=request_id,
            )
        state = workflow.get("State")
        if isinstance(state, bool) or not isinstance(state, int):
            raise WorkflowError(
                "工作流状态格式无效",
                request_id=request_id,
            )

        if state == 2:
            output = _parse_output(workflow.get("Output"))
            answer = _answer_from_output(output)
            if not answer:
                raise WorkflowError(
                    "工作流已完成但未返回结果",
                    request_id=request_id,
                )
            return {
                "ok": True,
                "query": query,
                "answer": answer,
                "workflow": {
                    "run_id": run_id,
                    "state": state,
                    "output": output,
                },
                "request_id": request_id,
            }

        if state in FAILED_STATES:
            raise WorkflowError(
                "ADP 工作流执行失败",
                error_type="workflow",
                request_id=request_id,
            )

        remaining = timeout - (monotonic() - started)
        if remaining <= 0:
            raise WorkflowError(
                "等待 ADP 工作流结果超时",
                error_type="timeout",
                request_id=request_id,
            )
        sleep(min(interval, remaining))


def print_error(error, stream=sys.stdout):
    error_data = {
        "type": getattr(error, "error_type", "response"),
        "message": str(error),
    }
    request_id = getattr(error, "request_id", None)
    if isinstance(request_id, str) and request_id:
        error_data["request_id"] = request_id
    print(
        json.dumps(
            {"ok": False, "error": error_data},
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ),
        file=stream,
    )


def main(argv=None, stdin=sys.stdin, stdout=sys.stdout):
    parser = argparse.ArgumentParser(
        description="调用 ADP 异步工作流检索慢病知识",
    )
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--query-stdin",
        action="store_true",
        help="从标准输入读取一行问题",
    )
    args = parser.parse_args(argv)

    try:
        if not args.query_stdin:
            raise ConfigError("必须使用 --query-stdin 传入问题")
        query = stdin.readline()
        if query.endswith("\n"):
            query = query[:-1]
        if query.endswith("\r"):
            query = query[:-1]
        config = load_config(args.config)
        result = query_workflow(config, query)
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ),
            file=stdout,
        )
        return 0
    except (ConfigError, WorkflowError) as error:
        print_error(error, stream=stdout)
        return 1
    except Exception:
        print_error(
            WorkflowError(
                "调用 ADP 工作流时发生未知错误",
                error_type="response",
            ),
            stream=stdout,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
