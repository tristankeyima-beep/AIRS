import json

def main(certification_list=None, material_list: str = "", **kwargs) -> dict:
    """
    将认定标准中的 ruleRepository 转换为可迭代的规则数组
    兼容两种入参方式：
    1. main(certification_list="...")
    2. main({"certification_list": "..."}) 这种平台整体传参方式
    """

    # 兼容：如果 certification_list 实际上传进来是整个参数 dict
    if isinstance(certification_list, dict):
        kwargs = {**certification_list, **kwargs}
        certification_list = kwargs.get("certification_list", "")
        material_list = kwargs.get("material_list", material_list)

    # 如果 certification_list 本身已经是 dict，则无需 json.loads
    if isinstance(certification_list, dict):
        data = certification_list
    elif isinstance(certification_list, str):
        data = json.loads(certification_list) if certification_list else {}
    else:
        raise ValueError(f"certification_list 类型错误，当前类型: {type(certification_list).__name__}")

    # 如果外层是数组，取第一个对象
    if isinstance(data, list):
        if not data:
            raise ValueError("certification_list 为空数组，无法提取 ruleRepository")
        data = data[0]

    if not isinstance(data, dict):
        raise ValueError("certification_list 必须是对象或对象数组的 JSON 字符串")

    # 提取 ruleRepository
    rule_repo = data.get("ruleRepository", [])
    if not rule_repo:
        raise ValueError("certification_list 中未找到 ruleRepository，请传入认定标准JSON")

    meta = data.get("meta", {})

    # 构建规则数组
    rules_array = []
    for rule_config in rule_repo:
        rules_array.append({
            "ruleCode": rule_config.get("ruleCode", ""),
            "ruleContent": rule_config.get("ruleContent", ""),
            "experience": rule_config.get("experience", None),
            "ruleKeywordGuide": rule_config.get("ruleKeywordGuide", [])
        })

    # 按 ruleCode 排序
    rules_array.sort(key=lambda x: x["ruleCode"])

    return {
        "chronicDiseaseCode": meta.get("chronicDiseaseCode", ""),
        "chronicDiseaseName": meta.get("chronicDiseaseName", ""),
        "rulesArray": rules_array,
        "rulesCount": len(rules_array),
        "logicTopology": data.get("logicTopology", {}),
        "logicTopologyStr": json.dumps(data.get("logicTopology", {}), ensure_ascii=False)
    }
