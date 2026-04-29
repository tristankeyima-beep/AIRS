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


def _normalize_entry(entry, fallback=None) -> dict:
    if isinstance(entry, str):
        stripped = entry.strip()
        if stripped in ("通过", "不通过"):
            entry = {"ruleResult": stripped}
        else:
            parsed = _parse_json_from_text(stripped)
            if parsed is not None:
                return _normalize_entry(parsed, fallback)
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

    result = entry.get("ruleResult")
    if result is None:
        result = "不通过" if "suspicionList" in entry else "通过"
    base["ruleResult"] = result

    if base["ruleResult"] == "不通过":
        base["suspicionList"] = _normalize_suspicion_list(entry.get("suspicionList"))

    return base


def _try_parse_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None


def _parse_json_from_text(text: str):
    stripped = _strip_json_fence(text)
    parsed = _try_parse_json(stripped)
    if parsed is not None:
        return parsed

    unescaped = _unescape_json_string(stripped)
    parsed = _try_parse_json(unescaped)
    if parsed is not None:
        return parsed

    for candidate in (stripped, unescaped):
        fragment = _extract_json_fragment(candidate)
        if fragment:
            parsed = _try_parse_json(fragment)
            if parsed is not None:
                return parsed

    return None


def _extract_json_fragment(text: str) -> str | None:
    stripped = text.strip()
    for left, right in (("{", "}"), ("[", "]")):
        if left in stripped and right in stripped:
            start = stripped.find(left)
            end = stripped.rfind(right)
            if start != -1 and end != -1 and end > start:
                return stripped[start : end + 1]
    return None


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


def main(ruleResult=None, **kwargs) -> dict:
    if ruleResult is None:
        if "ruleResult" in kwargs:
            ruleResult = kwargs.get("ruleResult")
        elif "text" in kwargs:
            ruleResult = kwargs.get("text")
        else:
            return {"ruleResult": []}

    if isinstance(ruleResult, list):
        fallback = kwargs.get("items")
        return {"ruleResult": [_normalize_entry(item, fallback) for item in ruleResult]}

    if isinstance(ruleResult, dict) and set(ruleResult.keys()) == {"ruleResult"}:
        ruleResult = ruleResult.get("ruleResult")

    if isinstance(ruleResult, dict) and not any(
        key in ruleResult for key in ("ruleCode", "ruleResult", "ruleContent", "suspicionList")
    ):
        for text_key in ("text", "output", "result", "answer", "content"):
            text_value = ruleResult.get(text_key)
            if isinstance(text_value, str) and text_value.strip():
                return main(ruleResult=text_value, **kwargs)

    if isinstance(ruleResult, (bytes, bytearray)):
        ruleResult = ruleResult.decode("utf-8", errors="ignore")

    if isinstance(ruleResult, str):
        stripped = ruleResult.strip()
        parsed = _parse_json_from_text(stripped)
        if parsed is not None:
            if isinstance(parsed, dict) and set(parsed.keys()) == {"ruleResult"}:
                ruleResult = parsed.get("ruleResult")
            else:
                ruleResult = parsed
        else:
            return {"ruleResult": [{"value": stripped}]}

    if isinstance(ruleResult, dict):
        if any(key in ruleResult for key in ("ruleCode", "ruleResult", "ruleContent", "suspicionList")):
            fallback = kwargs.get("items")
            return {"ruleResult": [_normalize_entry(ruleResult, fallback)]}
        return {
            "ruleResult": [
                _normalize_entry(
                    payload,
                    {"ruleCode": rule_code, **payload} if isinstance(payload, dict) else {"ruleCode": rule_code},
                )
                for rule_code, payload in ruleResult.items()
            ]
        }

    return {"ruleResult": [_normalize_entry(ruleResult, kwargs.get("items"))]}
