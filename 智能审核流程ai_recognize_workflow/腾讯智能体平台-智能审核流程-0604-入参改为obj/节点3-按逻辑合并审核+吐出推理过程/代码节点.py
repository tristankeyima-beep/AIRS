import json


def _try_parse_json(value):
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


def _normalize_rule_results(value):
    """
    将 ruleResults 统一解析成 list
    支持：
    1. 直接传 list
    2. 传 JSON 字符串
    3. 传 {"ruleResults": ...}
    """
    if value is None:
        return []

    if isinstance(value, str):
        parsed = _try_parse_json(value)
        if parsed is not None:
            return _normalize_rule_results(parsed)
        raise ValueError("ruleResults 不是合法 JSON 字符串")

    if isinstance(value, dict):
        if "ruleResults" in value:
            return _normalize_rule_results(value.get("ruleResults"))
        # 兼容腾讯子工作流结束节点的包装结构：
        # {"Output": {"one_rule_result": [...]}}
        if "Output" in value:
            return _normalize_rule_results(value.get("Output"))
        # 兼容子工作流出参字段：
        # {"one_rule_result": [{"ruleResult": [...], ...}]}
        if "one_rule_result" in value:
            return _normalize_rule_results(value.get("one_rule_result"))
        # 兼容聚合代码节点原始输出：
        # {"output": [{"ruleResult": [...], ...}]}
        if "output" in value:
            return _normalize_rule_results(value.get("output"))
        return [value]

    if isinstance(value, list):
        normalized = []
        for item in value:
            if isinstance(item, str):
                parsed_item = _try_parse_json(item)
                if parsed_item is not None:
                    if isinstance(parsed_item, list):
                        normalized.extend(parsed_item)
                    else:
                        normalized.append(parsed_item)
                else:
                    continue
            elif isinstance(item, dict) and any(
                key in item for key in ("Output", "one_rule_result", "output", "ruleResults")
            ):
                normalized.extend(_normalize_rule_results(item))
            else:
                normalized.append(item)
        return normalized

    return []


def _normalize_logic_topology(value):
    """
    将 logicTopology 统一解析成 dict
    支持：
    1. 直接传 dict
    2. 传 JSON 字符串
    3. 传 {"logicTopology": ...}
    """
    if value is None:
        return {}

    if isinstance(value, str):
        parsed = _try_parse_json(value)
        if parsed is not None:
            return _normalize_logic_topology(parsed)
        raise ValueError("logicTopology 不是合法 JSON 字符串")

    if isinstance(value, dict):
        if "logicTopology" in value and set(value.keys()) == {"logicTopology"}:
            return _normalize_logic_topology(value.get("logicTopology"))
        return value

    return {}


def main(params: dict) -> dict:
    """
    根据逻辑拓扑树合并各条规则的判断结果

    入参示例：
    {
      "ruleResults": [...],
      "logicTopology": {...}
    }
    """

    rule_results_input = params.get("ruleResults")
    logic_topology_input = params.get("logicTopology")

    rule_results = _normalize_rule_results(rule_results_input)
    logic_topology = _normalize_logic_topology(logic_topology_input)

    # 存储每个规则的完整信息（使用字典以 ruleCode 为 key）
    rule_info_map = {}
    # 保持规则出现顺序
    rule_order = []

    # 解析 ruleResults，提取每个规则的完整信息
    for item in rule_results:
        if not isinstance(item, dict):
            continue

        # 兼容单条规则直接传入
        if "ruleCode" in item and "ruleResult" in item:
            rule_code = item.get("ruleCode")
            if rule_code:
                rule_info_map[rule_code] = {
                    "ruleCode": rule_code,
                    "ruleContent": item.get("ruleContent", ""),
                    "ruleResult": item.get("ruleResult", ""),
                    "reasoningContent": item.get("reasoningContent", ""),
                    "ruleKeywordGuide": item.get("ruleKeywordGuide", []),
                    "suspicionList": item.get("suspicionList", []),
                }
                if rule_code not in rule_order:
                    rule_order.append(rule_code)
            continue

        # 处理聚合结构：{"ruleResult":[...], "reasoningContent":"...", "extractionList":[...]}
        if "ruleResult" in item and isinstance(item.get("ruleResult"), list):
            reasoning_content = item.get("reasoningContent", "")
            extraction_list = item.get("extractionList", [])

            for rule_item in item.get("ruleResult", []):
                if not isinstance(rule_item, dict):
                    continue

                rule_code = rule_item.get("ruleCode")
                if not rule_code:
                    continue

                rule_info_map[rule_code] = {
                    "ruleCode": rule_code,
                    "ruleContent": rule_item.get("ruleContent", ""),
                    "ruleResult": rule_item.get("ruleResult", ""),
                    "reasoningContent": reasoning_content or "",
                    "ruleKeywordGuide": extraction_list if isinstance(extraction_list, list) else [],
                    "suspicionList": rule_item.get("suspicionList", []),
                }

                if rule_code not in rule_order:
                    rule_order.append(rule_code)

    # 递归计算逻辑拓扑
    def evaluate(node):
        if not isinstance(node, dict) or "type" not in node:
            return False

        node_type = node.get("type")

        if node_type == "RULE_REF":
            rule_code = node.get("ruleCode")
            if not rule_code:
                return False
            rule_info = rule_info_map.get(rule_code, {})
            return rule_info.get("ruleResult") == "通过"

        if node_type == "GROUP":
            operator = node.get("operator")
            children = node.get("children", [])

            if not children or not isinstance(children, list):
                return False

            children_results = [evaluate(child) for child in children]

            if operator == "AND":
                return all(children_results)
            if operator == "OR":
                return any(children_results)

            return False

        return False

    final_pass = evaluate(logic_topology)

    # 构建输出结果
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
            "ruleResult": rule_info.get("ruleResult", ""),
        }

        if rule_info.get("ruleResult") == "不通过" and rule_info.get("suspicionList"):
            rule_output["suspicionList"] = rule_info.get("suspicionList", [])

        output_rule_results.append(rule_output)

    return {
        "finalResult": "通过" if final_pass else "不通过",
        "ruleResults": output_rule_results,
    }
