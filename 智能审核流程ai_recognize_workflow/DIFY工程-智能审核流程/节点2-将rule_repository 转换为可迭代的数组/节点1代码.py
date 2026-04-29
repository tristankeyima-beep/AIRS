import json

def main(certification_list: str, material_list: str = "", **kwargs) -> dict:
    """
    将认定标准中的 ruleRepository 转换为可迭代的规则数组
    """
    
    # 解析 JSON 字符串（可能是对象或数组）
    data = json.loads(certification_list) if certification_list else {}
    if isinstance(data, list):
        if not data:
            raise ValueError("certification_list 为空数组，无法提取 ruleRepository")
        data = data[0]
    if not isinstance(data, dict):
        raise ValueError("certification_list 必须是对象或对象数组的 JSON 字符串")
    
    # 提取 ruleRepository（新格式为数组）
    rule_repo = data.get("ruleRepository", [])
    if not rule_repo:
        raise ValueError("certification_list 中未找到 ruleRepository，请传入认定标准JSON")
    meta = data.get("meta", {})
    
    # ruleRepository 已经是数组格式，直接构建输出
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
        "logicTopology": data.get("logicTopology", {})
    }
