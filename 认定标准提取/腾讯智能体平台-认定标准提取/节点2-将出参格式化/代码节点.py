import json
import re


ITEM_KEYS = {"dataType", "required", "keywordContent", "enumOptions"}


def normalize_output(value):
    if not value:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        if isinstance(value.get("ruleKeywordGuide"), list):
            return value["ruleKeywordGuide"]
        if isinstance(value.get("result"), list):
            return value["result"]
        if isinstance(value.get("Output"), (dict, list, str)):
            return normalize_output(value["Output"])
        if ITEM_KEYS.intersection(value.keys()):
            return [
                {
                    key: value[key]
                    for key in ("dataType", "required", "keywordContent", "enumOptions")
                    if key in value
                }
            ]
        return [value]

    if isinstance(value, str):
        return parse_text_output(value)

    return []


def parse_text_output(value):
    text = str(value).strip()
    if not text:
        return []

    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
    matches = re.findall(code_block_pattern, text)

    if matches:
        json_str = matches[-1].strip()
    else:
        json_str = text

    result = []

    try:
        parsed = json.loads(json_str)

        if isinstance(parsed, list):
            result = parsed
        elif isinstance(parsed, dict):
            result = normalize_output(parsed)
    except json.JSONDecodeError:
        array_match = re.search(r"\[[\s\S]*\]", json_str)
        if array_match:
            try:
                parsed = json.loads(array_match.group())
                if isinstance(parsed, list):
                    result = parsed
            except json.JSONDecodeError:
                result = []

    return result


def main(ruleKeywordGuide=None, llm_output=None) -> dict:
    """
    腾讯代码节点标准写法：将 LLM 输出解析为 ruleKeywordGuide 数组。
    兼容普通文本输出，以及腾讯结构化输出传入的 obj / [obj]。
    """
    value = ruleKeywordGuide if ruleKeywordGuide is not None else llm_output

    if isinstance(value, (dict, list)):
        result = normalize_output(value)
    else:
        result = parse_text_output(value)

    return {"result": result}
