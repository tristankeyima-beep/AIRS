import json
import re


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[0].strip().lower().startswith("```"):
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _try_parse_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_json_fragment(text: str) -> str | None:
    decoder = json.JSONDecoder()
    candidates = []

    # Prefer arrays, because the expected extraction result is Array<object>.
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return text[index : index + end]
        if isinstance(parsed, dict):
            candidates.append(text[index : index + end])

    return candidates[0] if candidates else None


def _parse_extraction_data(text: str):
    stripped = _strip_json_fence(text)
    parsed = _try_parse_json(stripped)
    if parsed is not None:
        return parsed

    # Some models put the JSON inside a markdown fence within <think>...</think>.
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.S | re.I)
    if fence_match:
        parsed = _try_parse_json(fence_match.group(1).strip())
        if parsed is not None:
            return parsed

    fragment = _extract_json_fragment(stripped)
    if fragment:
        parsed = _try_parse_json(fragment)
        if parsed is not None:
            return parsed

    # Last fallback: remove think blocks and try again, for models that put JSON after thinking.
    without_think = re.sub(r"<think>.*?</think>", "", stripped, flags=re.S).strip()
    if without_think and without_think != stripped:
        return _parse_extraction_data(without_think)

    return None


def main(extraction_data=None, **kwargs) -> dict:
    """
    将模型出参转换为 Array<object>。
    输入格式: [ {"keywordCode": "10001001", "found": ..., "results": ...}, ... ]
    """
    if extraction_data is None:
        extraction_data = []

    if isinstance(extraction_data, str):
        text = extraction_data.strip()

        if text:
            extraction_data = _parse_extraction_data(text)
            if extraction_data is None:
                raise ValueError("无法从模型输出中解析精解结果 JSON 数组")
        else:
            extraction_data = []

    if not isinstance(extraction_data, list):
        raise ValueError("精解结果必须是数组格式")

    extraction_data.sort(key=lambda x: str(x.get("keywordCode", "")))

    return {"extractionList": extraction_data}
