import json
import math


WRAPPER_KEYS = (
    "knowledge_result",
    "Output",
    "output",
    "result",
    "data",
    "input",
    "inputs",
    "params",
    "arguments",
    "variables",
)


def _parse_knowledge_result(value):
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("knowledge_result 不能为空")
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError("knowledge_result 必须是合法 JSON 对象") from error

    if not isinstance(value, dict):
        raise ValueError("knowledge_result 必须是对象或 JSON 字符串")

    if isinstance(value.get("KnowledgeList"), list):
        return value["KnowledgeList"]

    for key in WRAPPER_KEYS:
        if key in value and value[key] is not None:
            return _parse_knowledge_result(value[key])

    received_keys = ", ".join(sorted(map(str, value.keys()))) or "（无）"
    raise ValueError(
        "knowledge_result 中未找到 KnowledgeList 数组；"
        f"当前对象字段：{received_keys}"
    )


def main(knowledge_result=None, **kwargs) -> dict:
    """选择 ADP 知识库结果中相关性最高的有效 DOC 正文。"""
    if knowledge_result is None:
        for key in ("knowledge_result", "Output", "output", "result"):
            if kwargs.get(key) is not None:
                knowledge_result = kwargs[key]
                break

    knowledge_list = _parse_knowledge_result(knowledge_result)
    selected_content = None
    selected_confidence = None

    for item in knowledge_list:
        if not isinstance(item, dict) or item.get("KnowledgeType") != "DOC":
            continue

        content = item.get("Content")
        if not isinstance(content, str) or not content.strip():
            continue

        try:
            confidence = float(item.get("Confidence"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(confidence):
            continue

        # 仅在分数更高时替换；同分保留 KnowledgeList 中更早的条目。
        if selected_confidence is None or confidence > selected_confidence:
            selected_content = content.strip()
            selected_confidence = confidence

    if selected_content is None:
        raise ValueError("未找到 Content 非空且 Confidence 有效的 DOC 知识库结果")

    return {"knowledgeContent": selected_content}
