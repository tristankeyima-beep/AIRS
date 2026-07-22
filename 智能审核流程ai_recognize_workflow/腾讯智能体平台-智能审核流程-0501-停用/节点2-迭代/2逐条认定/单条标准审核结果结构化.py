import ast
import json
import re


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            if lines[0].strip().lower().startswith("```json"):
                return "\n".join(lines[1:-1]).strip()
            if lines[0].strip() == "```":
                return "\n".join(lines[1:-1]).strip()
    return text


def _unescape_json_string(value: str) -> str:
    text = value.strip()
    if "\\n" in text or '\\"' in text or "\\t" in text or "\\r" in text:
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
        text = text.replace('\\"', '"')
        text = text.replace("\\\\", "\\")
    return text


def _try_parse_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None


def _extract_json_fragment(text: str):
    stripped = text.strip()
    for left, right in (("{", "}"), ("[", "]")):
        if left in stripped and right in stripped:
            start = stripped.find(left)
            end = stripped.rfind(right)
            if start != -1 and end != -1 and end > start:
                return stripped[start:end + 1]
    return None


def _normalize_ref_content(text: str) -> str:
    lines = text.splitlines()
    normalized_lines = [re.sub(r"[ \t]{3,}", " ", line) for line in lines]
    return "\n".join(normalized_lines)


def _normalize_source(source):
    if isinstance(source, str):
        return {"refContent": _normalize_ref_content(source)}
    if isinstance(source, dict):
        ref_content = source.get("refContent")
        if isinstance(ref_content, str):
            source = dict(source)
            source["refContent"] = _normalize_ref_content(ref_content)
        return source
    return source


def _normalize_suspicion_item(item):
    if isinstance(item, str):
        item = {"detail": item}
    elif not isinstance(item, dict):
        item = {"detail": item}

    normalized = {
        "suspicionType": item.get("suspicionType") or "未知",
        "detail": item.get("detail") or "",
        "sources": item.get("sources"),
    }

    sources = normalized["sources"]
    if sources is None:
        normalized["sources"] = []
    elif isinstance(sources, (bytes, bytearray)):
        normalized["sources"] = [sources.decode("utf-8", errors="ignore")]
    elif isinstance(sources, str):
        normalized["sources"] = [sources]
    elif not isinstance(sources, list):
        normalized["sources"] = [sources]

    normalized["sources"] = [_normalize_source(source) for source in normalized["sources"]]
    return normalized


def _normalize_suspicion_list(value):
    if value is None:
        return []

    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")

    if isinstance(value, str):
        unescaped = _unescape_json_string(value)
        stripped = _strip_json_fence(unescaped)
        parsed = _try_parse_json(stripped)

        if parsed is None:
            fragment = _extract_json_fragment(stripped)
            if fragment:
                parsed = _try_parse_json(fragment)

        if parsed is not None:
            return _normalize_suspicion_list(parsed)

        return [{"detail": stripped}]

    if isinstance(value, dict):
        return [_normalize_suspicion_item(value)]

    if isinstance(value, list):
        return [_normalize_suspicion_item(item) for item in value]

    return [_normalize_suspicion_item(value)]


def _normalize_entry(entry, fallback=None) -> dict:
    if isinstance(entry, str):
        stripped = entry.strip()
        if stripped in ("通过", "不通过"):
            entry = {"ruleResult": stripped}
        else:
            return {"value": entry}

    if not isinstance(entry, dict):
        return {"value": entry}

    base = {}

    if isinstance(fallback, dict):
        if "ruleCode" in fallback:
            base["ruleCode"] = fallback["ruleCode"]
        if "ruleContent" in fallback:
            base["ruleContent"] = fallback["ruleContent"]

    items = entry.get("items")
    if isinstance(items, dict):
        if "ruleCode" in items:
            base["ruleCode"] = items["ruleCode"]
        if "ruleContent" in items:
            base["ruleContent"] = items["ruleContent"]

    if "ruleCode" in entry:
        base["ruleCode"] = entry["ruleCode"]
    if "ruleContent" in entry:
        base["ruleContent"] = entry["ruleContent"]

    # 如果 LLM 把提示词里的变量名原样输出了，用当前规则对象兜底覆盖。
    if isinstance(fallback, dict):
        if str(base.get("ruleCode", "")).strip() in ("", "ruleCode", "{{ruleCode}}"):
            if "ruleCode" in fallback:
                base["ruleCode"] = fallback["ruleCode"]
        if str(base.get("ruleContent", "")).strip() in ("", "ruleContent", "{{ruleContent}}"):
            if "ruleContent" in fallback:
                base["ruleContent"] = fallback["ruleContent"]

    result = entry.get("ruleResult")
    if result is None:
        result = "不通过" if "suspicionList" in entry else "通过"
    base["ruleResult"] = result

    if base["ruleResult"] == "不通过":
        base["suspicionList"] = _normalize_suspicion_list(entry.get("suspicionList"))

    return base


def _parse_rule_result_value(value):
    """
    将 ruleResult 原始值解析成 Python 对象
    支持：
    - list
    - dict
    - JSON 字符串
    - markdown json 代码块
    - 转义后的 JSON 字符串
    """
    if value is None:
        return []

    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")

    if isinstance(value, (list, dict)):
        return value

    if isinstance(value, str):
        stripped = _strip_json_fence(value)
        parsed = _try_parse_json(stripped)

        if parsed is None:
            unescaped = _unescape_json_string(stripped)
            parsed = _try_parse_json(unescaped)

            if parsed is None:
                fragment = _extract_json_fragment(stripped)
                if fragment:
                    parsed = _try_parse_json(fragment)

            if parsed is None:
                fragment = _extract_json_fragment(unescaped)
                if fragment:
                    parsed = _try_parse_json(fragment)

        if parsed is not None:
            if isinstance(parsed, dict) and set(parsed.keys()) == {"ruleResult"}:
                return parsed.get("ruleResult")
            return parsed

        return [{"value": stripped}]

    return [value]


def _normalize_items(value):
    """
    将 items 统一成规则对象。
    腾讯平台建议把 items 配成 obj；这里额外兼容 JSON 字符串。
    """
    if value is None:
        return None

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        parsed = _try_parse_json(_strip_json_fence(value))
        if isinstance(parsed, dict):
            return parsed

    return value


def main(params: dict) -> dict:
    """
    腾讯代码节点标准写法：
    入参：
    {
      "ruleResult": "...",
      "items": {...}
    }

    输出：
    {
      "ruleResult": [...]
    }
    """
    rule_result = params.get("ruleResult")
    items = _normalize_items(params.get("items"))

    # 兼容有些节点把文本放在 text 字段里
    if rule_result is None:
        rule_result = params.get("text")

    parsed_value = _parse_rule_result_value(rule_result)

    if isinstance(parsed_value, list):
        return {
            "ruleResult": [_normalize_entry(item, items) for item in parsed_value]
        }

    if isinstance(parsed_value, dict):
        if any(key in parsed_value for key in ("ruleCode", "ruleResult", "ruleContent", "suspicionList")):
            return {
                "ruleResult": [_normalize_entry(parsed_value, items)]
            }

        return {
            "ruleResult": [
                _normalize_entry(
                    payload,
                    {"ruleCode": rule_code, **payload} if isinstance(payload, dict) else {"ruleCode": rule_code},
                )
                for rule_code, payload in parsed_value.items()
            ]
        }

    return {
        "ruleResult": [_normalize_entry(parsed_value, items)]
    }
