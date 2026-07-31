#!/usr/bin/env python3
"""Run a chronic-disease audit through Tencent ADP async workflows."""

import ast
import copy
import datetime
import hashlib
import hmac
import json
import math
import time
import urllib.parse
import uuid


DEFAULT_SUSPICION_TYPE_OPTIONS = (
    "指标异常;信息缺失;资质不符;临床表现不足;材料不全"
)


class AuditClientError(Exception):
    """A safe, classified error suitable for a CLI envelope."""

    def __init__(self, message, error_type="response", code=None, request_id=None):
        super().__init__(message)
        self.error_type = error_type
        self.code = code
        self.request_id = request_id


def _config_error(message):
    return AuditClientError(message, error_type="config")


def _input_error(message, code=None):
    return AuditClientError(message, error_type="input", code=code)


def _nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def load_config(path):
    """Load and validate the selected deployment profile."""
    try:
        with open(path, "r", encoding="utf-8") as file:
            root = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise _config_error("无法读取有效的配置文件") from error

    if not isinstance(root, dict):
        raise _config_error("配置文件必须是 JSON 对象")
    profile_name = root.get("active_profile")
    profiles = root.get("profiles")
    if not _nonempty_string(profile_name) or not isinstance(profiles, dict):
        raise _config_error("配置缺少有效的 active_profile 或 profiles")
    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        raise _config_error("找不到 active_profile 对应的配置")

    result = {"profile": profile_name.strip()}
    for name in (
        "api_host",
        "app_id",
        "app_key",
        "secret_id",
        "secret_key",
        "region",
        "service",
        "version",
    ):
        value = profile.get(name)
        if not _nonempty_string(value):
            raise _config_error("配置缺少有效字段: " + name)
        result[name] = value.strip()

    parsed = urllib.parse.urlparse(result["api_host"])
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise _config_error("配置字段无效: api_host")
    result["api_host"] = parsed.scheme + "://" + parsed.netloc.rstrip("/")

    run_env = profile.get("run_env")
    if isinstance(run_env, bool) or run_env not in (0, 1):
        raise _config_error("配置字段无效: run_env")
    result["run_env"] = run_env

    for name in ("poll_interval_seconds", "timeout_seconds"):
        value = root.get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise _config_error("配置字段无效: " + name)
        result[name] = value
    return result


def _strip_single_fence(text):
    stripped = text.lstrip("\ufeff").strip()
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[0].strip().lower() in ("```", "```json"):
        if lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_jsonish(text):
    """Parse JSON-ish input without evaluating executable expressions."""
    if not isinstance(text, str):
        raise _input_error("输入必须是文本")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = _strip_single_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(cleaned)
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError) as error:
        raise _input_error("输入不是有效的 JSON-ish 数据") from error


def _new_id(uuid_factory):
    return str(uuid_factory())


def _validate_audit_id(value):
    if not _nonempty_string(value):
        raise _input_error("auditId 必须是非空字符串")
    value = value.strip()
    if value in (".", "..") or any(char in value for char in ("/", "\\", "\0")):
        raise _input_error("auditId 包含不安全的路径字符")
    return value


def normalize_audit_input(value, uuid_factory=uuid.uuid4):
    """Validate and normalize an audit request without mutating its source."""
    if not isinstance(value, dict):
        raise _input_error("审核输入必须是对象")
    result = copy.deepcopy(value)

    certification = result.get("certification_list")
    if isinstance(certification, list):
        if len(certification) > 1:
            raise _input_error(
                "certification_list 包含多个候选对象",
                code="multiple_certification_candidates",
            )
        if len(certification) == 1:
            certification = certification[0]
    if not isinstance(certification, dict):
        raise _input_error("certification_list 必须是对象")
    meta = certification.get("meta")
    if not isinstance(meta, dict):
        raise _input_error("certification_list.meta 必须是对象")
    for name in ("chronicDiseaseName", "chronicDiseaseCode"):
        if not _nonempty_string(meta.get(name)):
            raise _input_error("certification_list.meta 缺少有效字段: " + name)
        meta[name] = meta[name].strip()
    result["certification_list"] = certification

    audit_id = result.get("auditId")
    if audit_id is None:
        audit_id = _new_id(uuid_factory)
    result["auditId"] = _validate_audit_id(audit_id)

    materials = result.get("material_list")
    if not isinstance(materials, list) or not materials:
        raise _input_error("material_list 必须是非空对象数组")
    for index, material in enumerate(materials):
        if not isinstance(material, dict):
            raise _input_error("material_list 的每一项必须是对象")
        for name in ("materialName", "materialContent"):
            if not _nonempty_string(material.get(name)):
                raise _input_error(
                    "material_list[" + str(index) + "] 缺少有效字段: " + name
                )
            material[name] = material[name].strip()
        if material.get("materialId") is None:
            material["materialId"] = _new_id(uuid_factory)
        elif not _nonempty_string(material.get("materialId")):
            raise _input_error("materialId 必须是非空字符串")

    suspicions = result.get("suspicion_type_options")
    if suspicions is None:
        suspicions = DEFAULT_SUSPICION_TYPE_OPTIONS
    if not _nonempty_string(suspicions):
        raise _input_error("suspicion_type_options 必须是非空字符串")
    result["suspicion_type_options"] = suspicions.strip()
    return result


def _sha256_hex(value):
    return hashlib.sha256(value).hexdigest()


def _hmac_sha256(key, value):
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


def build_signed_headers(config, action, body, timestamp=None):
    """Build TC3-HMAC-SHA256 headers for one ADP action."""
    if timestamp is None:
        timestamp = int(time.time())
    timestamp = int(timestamp)
    host = urllib.parse.urlparse(config["api_host"]).netloc.lower()
    content_type = "application/json"
    canonical_headers = "content-type:" + content_type + "\n" + "host:" + host + "\n"
    signed_headers = "content-type;host"
    canonical_request = (
        "POST\n/\n\n"
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
    scope = date + "/" + config["service"] + "/tc3_request"
    string_to_sign = (
        "TC3-HMAC-SHA256\n"
        + str(timestamp)
        + "\n"
        + scope
        + "\n"
        + _sha256_hex(canonical_request.encode("utf-8"))
    )
    secret_date = _hmac_sha256(
        ("TC3" + config["secret_key"]).encode("utf-8"),
        date,
    )
    secret_service = _hmac_sha256(secret_date, config["service"])
    secret_signing = _hmac_sha256(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        "TC3-HMAC-SHA256 Credential="
        + config["secret_id"]
        + "/"
        + scope
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
