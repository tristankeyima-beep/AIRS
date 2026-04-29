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
        if isinstance(parsed, dict) and key in parsed:
            return parsed.get(key, default)
        if parsed is not None:
            return parsed
        return stripped

    if isinstance(value, dict) and key in value:
        if set(value.keys()) == {key}:
            return value.get(key, default)
    return value


def main(ruleResult=None, reasoningContent=None, extractionList=None, **kwargs) -> dict:
    """
    出参聚合：将 ruleResult / reasoningContent / extractionList 组装成一个输出。
    """
    if ruleResult is None:
        ruleResult = kwargs.get("ruleResult")
    if reasoningContent is None:
        reasoningContent = kwargs.get("reasoningContent")
    if extractionList is None:
        extractionList = kwargs.get("extractionList")

    ruleResult = _normalize_input(ruleResult, "ruleResult", [])
    reasoningContent = _normalize_input(reasoningContent, "reasoningContent", "")
    extractionList = _normalize_input(extractionList, "extractionList", [])

    payload = {
        "ruleResult": ruleResult or [],
        "reasoningContent": reasoningContent or "",
        "extractionList": extractionList or [],
    }

    return {"output": [payload]}
