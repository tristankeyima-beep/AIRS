import json


def _normalize_result_item(item):
    if not isinstance(item, dict):
        return item

    normalized = dict(item)

    if "materialSource" not in normalized:
        normalized["materialSource"] = normalized.get("sourceHospital", "")

    return normalized


def _normalize_extraction_item(item):
    if not isinstance(item, dict):
        return item

    normalized = dict(item)
    results = normalized.get("results")
    if isinstance(results, list):
        normalized["results"] = [_normalize_result_item(result) for result in results]
    return normalized


def main(params: dict) -> dict:
    """
    将 extraction_data 解析为数组，并按 keywordCode 排序后输出 extractionList
    入参示例：
    {
      "extraction_data": "[{\"keywordCode\":\"1002001001\",\"found\":true,\"results\":[...]}]"
    }
    """
    extraction_data = params.get("extraction_data", "")

    # 兼容腾讯平台不同节点的输出命名。
    # 正常配置应使用 extraction_data；如果误绑成 Output/text/result/content，也尽量读取。
    if extraction_data is None or extraction_data == "":
        for fallback_key in ("Output", "output", "text", "result", "content"):
            if params.get(fallback_key) not in (None, ""):
                extraction_data = params.get(fallback_key)
                break

    # 如果绑定到了整个 Output 对象，例如 {"extraction_data": [...]}
    if isinstance(extraction_data, dict) and "extraction_data" in extraction_data:
        extraction_data = extraction_data.get("extraction_data")

    # 空值处理
    if extraction_data is None or extraction_data == "":
        extraction_list = []
    # 如果传入的是字符串，按 JSON 解析
    elif isinstance(extraction_data, str):
        extraction_list = json.loads(extraction_data)
    # 如果平台直接传入数组，也兼容
    elif isinstance(extraction_data, list):
        extraction_list = extraction_data
    else:
        raise ValueError("extraction_data 必须是 JSON 字符串或数组格式")

    if not isinstance(extraction_list, list):
        raise ValueError("解析后的 extraction_data 必须是数组格式")

    extraction_list = [_normalize_extraction_item(item) for item in extraction_list]

    # 按 keywordCode 排序
    extraction_list.sort(key=lambda x: str(x.get("keywordCode", "")) if isinstance(x, dict) else "")

    return {
        "extractionList": extraction_list
    }
