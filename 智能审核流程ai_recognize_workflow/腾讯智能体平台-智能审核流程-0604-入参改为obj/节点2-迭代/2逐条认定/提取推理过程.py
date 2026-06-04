import json


def format_reasoning_result(reasoning_content: str) -> str:
    """
    对推理过程文本做最终格式整理
    """
    return reasoning_content or ""


def main(params: dict) -> dict:
    """
    腾讯代码节点标准写法

    入参示例：
    {
      "reasoningContent": "......"
    }

    或：
    {
      "reasoningContent": "{\"reasoningContent\": \"......\"}"
    }

    输出示例：
    {
      "reasoningContent": "......"
    }
    """
    reasoning_content = params.get("reasoningContent", "")

    if reasoning_content is None:
        reasoning_content = ""

    if isinstance(reasoning_content, (bytes, bytearray)):
        reasoning_content = reasoning_content.decode("utf-8", errors="ignore")

    if isinstance(reasoning_content, dict):
        reasoning_content = reasoning_content.get("reasoningContent", "")
    elif isinstance(reasoning_content, str):
        text = reasoning_content.strip()
        if text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None

            if isinstance(parsed, dict) and "reasoningContent" in parsed:
                reasoning_content = parsed.get("reasoningContent", "")
            else:
                reasoning_content = text

    reasoning_content = format_reasoning_result(str(reasoning_content or ""))

    return {
        "reasoningContent": reasoning_content
    }