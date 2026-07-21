import json
import math
import re


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

    if isinstance(value, list):
        return value

    if not isinstance(value, dict):
        raise ValueError("knowledge_result 必须是对象、数组或 JSON 字符串")

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


def _read_document_name(item, content):
    doc_name = item.get("DocName")
    if isinstance(doc_name, str) and doc_name.strip():
        return doc_name.strip()

    match = re.search(r"(?m)^\s*文档名[：:]\s*(.+?)\s*$", content)
    if match and match.group(1).strip():
        return match.group(1).strip()

    raise ValueError("最高相关 DOC 缺少 DocName，且 Content 中未找到文档名")


def main(knowledge_result=None, chronicDiseaseName=None, **kwargs) -> dict:
    """选择 ADP 知识库结果中相关性最高的有效 DOC 正文。"""
    if isinstance(knowledge_result, dict):
        params = knowledge_result
        if chronicDiseaseName is None:
            chronicDiseaseName = params.get("chronicDiseaseName")
        if "knowledge_result" in params:
            knowledge_result = params.get("knowledge_result")
        elif "knowledgeContent" in params:
            # 腾讯代码节点的 lke_system_params 会把 KnowledgeList 数组放在此字段。
            knowledge_result = params.get("knowledgeContent")

    if knowledge_result is None:
        for key in ("knowledge_result", "knowledgeContent", "Output", "output", "result"):
            if kwargs.get(key) is not None:
                knowledge_result = kwargs[key]
                break

    if chronicDiseaseName is None:
        chronicDiseaseName = kwargs.get("chronicDiseaseName")
    if not isinstance(chronicDiseaseName, str) or not chronicDiseaseName.strip():
        raise ValueError("chronicDiseaseName 必须是非空字符串")
    chronic_disease_name = chronicDiseaseName.strip()

    knowledge_list = _parse_knowledge_result(knowledge_result)
    selected_content = None
    selected_document_name = None
    selected_confidence = None

    for item in knowledge_list:
        if not isinstance(item, dict) or item.get("KnowledgeType") != "DOC":
            continue

        content = item.get("Content")
        if not isinstance(content, str) or not content.strip():
            continue
        if chronic_disease_name not in content:
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
            selected_document_name = _read_document_name(item, selected_content)
            selected_confidence = confidence

    if selected_content is None:
        return {"knowledgeContent": "", "documentName": ""}

    return {
        "knowledgeContent": selected_content,
        "documentName": selected_document_name,
    }
