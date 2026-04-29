import json


def format_reasoning_result(reasoning_content: str) -> str:
    """
    入参: reasoningContent (string)
    出参: reasoningContent (string)
    """
    return reasoning_content or ""


def main(reasoningContent=None, **kwargs) -> dict:
    """
    入口函数：兼容 DIFY 运行时 main() 调用。
    """
    if reasoningContent is None:
        if "reasoningContent" in kwargs:
            reasoningContent = kwargs.get("reasoningContent")
        elif isinstance(kwargs.get("input"), dict):
            reasoningContent = kwargs["input"].get("reasoningContent")
        else:
            return {"reasoningContent": ""}

    if isinstance(reasoningContent, (bytes, bytearray)):
        reasoningContent = reasoningContent.decode("utf-8", errors="ignore")

    if isinstance(reasoningContent, dict):
        reasoningContent = reasoningContent.get("reasoningContent", "")
    elif isinstance(reasoningContent, str):
        # 兼容上游把 JSON 字符串整体透传的情况
        try:
            parsed = json.loads(reasoningContent)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and "reasoningContent" in parsed:
            reasoningContent = parsed.get("reasoningContent", "")

    reasoningContent = format_reasoning_result(reasoningContent or "")
    return {"reasoningContent": reasoningContent}
