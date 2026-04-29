import json

def _parse_mutex_review_result(mutexReviewResult):
    if not mutexReviewResult:
        return None

    if isinstance(mutexReviewResult, str):
        stripped_result = mutexReviewResult.strip()
        if stripped_result in ("通过", "不通过"):
            return {
                "reviewResult": stripped_result,
                "mutexDiseasesName": [],
                "reason": "",
            }
        try:
            mutexReviewResult = json.loads(stripped_result)
        except json.JSONDecodeError:
            return None

    if not isinstance(mutexReviewResult, dict):
        return None

    review_result = mutexReviewResult.get("reviewResult")
    if review_result not in ("通过", "不通过"):
        review_result = "通过"

    hit_names = mutexReviewResult.get("mutexDiseasesName", [])
    if isinstance(hit_names, str):
        hit_names = [hit_names] if hit_names else []
    elif not isinstance(hit_names, list):
        hit_names = []

    return {
        "reviewResult": review_result,
        "mutexDiseasesName": hit_names,
        "reason": mutexReviewResult.get("reason", ""),
    }


def main(ruleResults: list, logicTopology: dict, mutexReviewResult=None) -> dict:
    """
    根据逻辑拓扑树合并各条规则的判断结果
    """
    
    # 存储每个规则的完整信息（使用字典以 ruleCode 为 key）
    rule_info_map = {}
    # 保持规则出现的顺序
    rule_order = []
    
    # 兼容 ruleResults 直接传入整体对象的情况
    if isinstance(ruleResults, dict) and "ruleResults" in ruleResults:
        ruleResults = ruleResults.get("ruleResults") or []
    
    # 解析 ruleResults，提取每个规则的完整信息
    for item in ruleResults:
        if isinstance(item, str):
            item = json.loads(item)
        
        # 处理列表形式的输入
        items_to_process = item if isinstance(item, list) else [item]
        
        for sub_item in items_to_process:
            if isinstance(sub_item, str):
                sub_item = json.loads(sub_item)
            
            if not isinstance(sub_item, dict):
                continue
            
            # 处理包含 ruleResult 的结构
            if "ruleResult" in sub_item and isinstance(sub_item.get("ruleResult"), list):
                reasoning_content = sub_item.get("reasoningContent")
                extraction_list = sub_item.get("extractionList", [])
                
                # 遍历 ruleResult 数组中的每个规则
                for rule_item in sub_item.get("ruleResult", []):
                    if not isinstance(rule_item, dict):
                        continue
                    
                    rule_code = rule_item.get("ruleCode")
                    if not rule_code:
                        continue
                    
                    # 保存规则的完整信息
                    rule_info_map[rule_code] = {
                        "ruleCode": rule_code,
                        "ruleContent": rule_item.get("ruleContent", ""),
                        "ruleResult": rule_item.get("ruleResult", ""),
                        "reasoningContent": reasoning_content or "",
                        "ruleKeywordGuide": extraction_list,
                        "suspicionList": rule_item.get("suspicionList", [])
                    }
                    
                    # 记录规则出现的顺序（避免重复）
                    if rule_code not in rule_order:
                        rule_order.append(rule_code)
    
    # 递归计算逻辑拓扑
    def evaluate(node):
        if node["type"] == "RULE_REF":
            rule_code = node["ruleCode"]
            rule_info = rule_info_map.get(rule_code, {})
            return rule_info.get("ruleResult") == "通过"
        
        elif node["type"] == "GROUP":
            operator = node["operator"]
            children_results = [evaluate(child) for child in node["children"]]
            
            if operator == "AND":
                return all(children_results)
            elif operator == "OR":
                return any(children_results)
        
        return False
    
    # 计算规则合并结果
    final_pass = evaluate(logicTopology)
    parsed_mutex_review_result = _parse_mutex_review_result(mutexReviewResult)

    if parsed_mutex_review_result and parsed_mutex_review_result.get("reviewResult") == "不通过":
        final_pass = False
    
    # 构建输出结果（按照规则出现的顺序）
    output_rule_results = []
    for rule_code in rule_order:
        if rule_code not in rule_info_map:
            continue
        
        rule_info = rule_info_map[rule_code]
        rule_output = {
            "ruleCode": rule_info["ruleCode"],
            "ruleContent": rule_info.get("ruleContent", ""),
            "ruleKeywordGuide": rule_info.get("ruleKeywordGuide", []),
            "reasoningContent": rule_info.get("reasoningContent", ""),
            "ruleResult": rule_info.get("ruleResult", "")
        }
        
        # 仅在 ruleResult 为"不通过"时包含 suspicionList 字段
        if rule_info.get("ruleResult") == "不通过" and rule_info.get("suspicionList"):
            rule_output["suspicionList"] = rule_info["suspicionList"]
        
        output_rule_results.append(rule_output)
    
    output = {
        "finalResult": "通过" if final_pass else "不通过",
        "ruleResults": output_rule_results
    }

    return output
