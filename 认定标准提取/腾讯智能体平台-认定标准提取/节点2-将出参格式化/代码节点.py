import json
import re


def main(llm_output: str) -> dict:
    """
    腾讯代码节点标准写法：将 LLM 输出解析为 ruleKeywordGuide 数组。
    """
    result = []

    if not llm_output or not str(llm_output).strip():
        return {"result": result}

    text = str(llm_output).strip()

    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
    matches = re.findall(code_block_pattern, text)

    if matches:
        json_str = matches[-1].strip()
    else:
        json_str = text

    try:
        parsed = json.loads(json_str)

        if isinstance(parsed, list):
            result = parsed
        elif isinstance(parsed, dict):
            if isinstance(parsed.get("ruleKeywordGuide"), list):
                result = parsed["ruleKeywordGuide"]
            elif isinstance(parsed.get("result"), list):
                result = parsed["result"]
            else:
                result = [parsed]
    except json.JSONDecodeError:
        array_match = re.search(r"\[[\s\S]*\]", json_str)
        if array_match:
            try:
                parsed = json.loads(array_match.group())
                if isinstance(parsed, list):
                    result = parsed
            except json.JSONDecodeError:
                result = []

    return {"result": result}

