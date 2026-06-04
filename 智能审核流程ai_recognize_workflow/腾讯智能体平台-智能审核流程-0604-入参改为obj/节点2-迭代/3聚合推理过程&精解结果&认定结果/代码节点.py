import json


def _strip_json_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```") and value.endswith("```"):
        lines = value.splitlines()
        if len(lines) >= 2:
            first = lines[0].strip().lower()
            if first.startswith("```json") or first == "```":
                return "\n".join(lines[1:-1]).strip()
    return value


def _try_parse_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _normalize_input(value, key: str, default):
    if value is None:
        return default

    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")

    if isinstance(value, str):
        stripped = _strip_json_fence(value)
        parsed = _try_parse_json(stripped)

        # 如果是 {"ruleResult": ...} / {"reasoningContent": ...} / {"extractionList": ...}
        if isinstance(parsed, dict) and key in parsed:
            return parsed.get(key, default)

        # 如果本身就是合法 JSON（例如数组 / 对象 / 字符串）
        if parsed is not None:
            return parsed

        # 普通字符串原样返回
        return stripped

    # 如果直接传的是 {"ruleResult": ...} 这种单字段对象
    if isinstance(value, dict) and key in value and set(value.keys()) == {key}:
        return value.get(key, default)

    return value


def main(params: dict) -> dict:
    """
    聚合节点：将 ruleResult / reasoningContent / extractionList 组装成统一输出

    入参示例：
    {
      "ruleResult": [...],
      "reasoningContent": "...",
      "extractionList": [...]
    }

    输出示例：
    {
      "output": [
        {
          "ruleResult": [...],
          "reasoningContent": "...",
          "extractionList": [...]
        }
      ]
    }
    """
    rule_result = params.get("ruleResult")
    reasoning_content = params.get("reasoningContent")
    extraction_list = params.get("extractionList")

    rule_result = _normalize_input(rule_result, "ruleResult", [])
    reasoning_content = _normalize_input(reasoning_content, "reasoningContent", "")
    extraction_list = _normalize_input(extraction_list, "extractionList", [])

    payload = {
        "ruleResult": rule_result or [],
        "reasoningContent": reasoning_content or "",
        "extractionList": extraction_list or [],
    }

    return {
        "output": [payload]
    }