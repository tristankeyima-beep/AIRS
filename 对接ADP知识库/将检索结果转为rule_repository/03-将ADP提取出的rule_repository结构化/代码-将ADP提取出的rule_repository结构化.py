import json
import re


def _parse_json_text(value, field_name):
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} 不能为空")

    code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if code_blocks:
        text = code_blocks[-1].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{field_name} 必须是合法 JSON 对象或数组") from error


def _read_payload(value, logic_topology=None):
    if isinstance(value, str):
        value = _parse_json_text(value, "llm_output")

    if isinstance(value, list):
        return value, logic_topology

    if not isinstance(value, dict):
        raise ValueError("llm_output 必须是对象、数组或 JSON 字符串")

    if "Output" in value:
        return _read_payload(value["Output"], logic_topology)

    if "ruleRepository" in value:
        return value["ruleRepository"], value.get("logicTopology", logic_topology)

    for wrapper_key in ("result", "output", "data"):
        if wrapper_key in value:
            return _read_payload(value[wrapper_key], logic_topology)

    raise ValueError("llm_output 中未找到 ruleRepository")


def _require_non_empty_string(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串")
    return value.strip()


def _normalize_required(value, field_name):
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ValueError(f"{field_name} 必须是布尔值")


def _normalize_keyword_guide(guides, rule_code):
    if not isinstance(guides, list) or not guides:
        raise ValueError(f"规则 {rule_code} 的 ruleKeywordGuide 至少包含一条提取项")
    if len(guides) > 999:
        raise ValueError(f"规则 {rule_code} 的提取项数量不能超过 999")

    normalized_guides = []
    for index, guide in enumerate(guides, start=1):
        if not isinstance(guide, dict):
            raise ValueError(f"规则 {rule_code} 的第 {index} 条提取项必须是对象")

        data_type = _require_non_empty_string(
            guide.get("dataType"),
            f"规则 {rule_code} 的第 {index} 条提取项 dataType",
        ).lower()
        if data_type not in ("enum", "string"):
            raise ValueError(f"规则 {rule_code} 的第 {index} 条提取项 dataType 只能是 enum 或 string")

        keyword_content = _require_non_empty_string(
            guide.get("keywordContent"),
            f"规则 {rule_code} 的第 {index} 条提取项 keywordContent",
        )

        enum_options = guide.get("enumOptions", [])
        if data_type == "enum":
            if not isinstance(enum_options, list):
                enum_options = []
            else:
                enum_options = [
                    option.strip()
                    for option in enum_options
                    if isinstance(option, str) and option.strip()
                ]

            # 流程不可逆：LLM 漏枚举选项时，将该提取项降级为自由文本，继续产出规则库。
            if not enum_options:
                data_type = "string"
        else:
            enum_options = []

        normalized_guides.append({
            "keywordCode": f"{rule_code}{index:03d}",
            "dataType": data_type,
            "required": _normalize_required(
                guide.get("required"),
                f"规则 {rule_code} 的第 {index} 条提取项 required",
            ),
            "keywordContent": keyword_content,
            "enumOptions": enum_options,
        })

    return normalized_guides


def _normalize_rules(raw_rules, chronic_disease_code):
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError("ruleRepository 至少包含一条规则")
    if len(raw_rules) > 999:
        raise ValueError("ruleRepository 的规则数量不能超过 999")

    prefix_match = re.search(r"(\d{2})$", chronic_disease_code)
    if not prefix_match:
        raise ValueError("chronicDiseaseCode 必须以两位数字结尾，才能生成五位 ruleCode")
    prefix = prefix_match.group(1)

    normalized_rules = []
    rule_code_map = {}
    for index, raw_rule in enumerate(raw_rules, start=1):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"第 {index} 条规则必须是对象")

        temp_rule_id = _require_non_empty_string(
            raw_rule.get("tempRuleId"),
            f"第 {index} 条规则 tempRuleId",
        )
        if not re.fullmatch(r"R\d{3}", temp_rule_id):
            raise ValueError(f"第 {index} 条规则 tempRuleId 必须形如 R001")
        if temp_rule_id in rule_code_map:
            raise ValueError(f"tempRuleId 重复：{temp_rule_id}")

        rule_code = f"{prefix}{index:03d}"
        rule_code_map[temp_rule_id] = rule_code
        rule_content = _require_non_empty_string(raw_rule.get("ruleContent"), f"规则 {temp_rule_id} 的 ruleContent")
        rule_source = raw_rule.get("ruleSource", "ADP知识库检索结果")
        if not isinstance(rule_source, str) or not rule_source.strip():
            rule_source = "ADP知识库检索结果"
        experience = raw_rule.get("experience", "")
        if experience is None:
            experience = ""
        if not isinstance(experience, str):
            raise ValueError(f"规则 {temp_rule_id} 的 experience 必须是字符串")

        normalized_rules.append({
            "ruleCode": rule_code,
            "ruleContent": rule_content,
            "ruleSource": rule_source.strip(),
            "experience": experience,
            "ruleKeywordGuide": _normalize_keyword_guide(raw_rule.get("ruleKeywordGuide"), rule_code),
            "sourceRuleContent": str(raw_rule.get("sourceRuleContent") or rule_content).strip(),
            "sourceMdFile": str(raw_rule.get("sourceMdFile") or "").strip(),
            "sourceSection": str(raw_rule.get("sourceSection") or "认定标准").strip(),
        })

    return normalized_rules, rule_code_map


def _rewrite_logic_topology(node, rule_code_map, referenced_codes):
    if not isinstance(node, dict):
        raise ValueError("logicTopology 节点必须是对象")

    node_type = node.get("type")
    if node_type == "RULE_REF":
        reference = _require_non_empty_string(node.get("ruleCode"), "RULE_REF.ruleCode")
        if reference in rule_code_map:
            rule_code = rule_code_map[reference]
        elif reference in rule_code_map.values():
            rule_code = reference
        else:
            raise ValueError(f"logicTopology 引用了不存在的规则：{reference}")
        referenced_codes.add(rule_code)
        return {"type": "RULE_REF", "ruleCode": rule_code}

    if node_type != "GROUP":
        raise ValueError("logicTopology 节点 type 只能是 GROUP 或 RULE_REF")

    operator = node.get("operator")
    if operator not in ("AND", "OR"):
        raise ValueError("GROUP.operator 只能是 AND 或 OR")
    children = node.get("children")
    if not isinstance(children, list) or not children:
        raise ValueError("GROUP.children 必须是非空数组")

    normalized = {
        key: value
        for key, value in node.items()
        if key not in ("type", "operator", "children")
    }
    normalized.update({
        "type": "GROUP",
        "operator": operator,
        "children": [
            _rewrite_logic_topology(child, rule_code_map, referenced_codes)
            for child in children
        ],
    })
    return normalized


def main(llm_output=None, chronicDiseaseCode=None, logicTopology=None, **kwargs) -> dict:
    """将 ADP 检索结果 LLM 输出结构化为 ruleRepository 与 logicTopology。"""
    if isinstance(llm_output, dict) and "llm_output" in llm_output:
        params = llm_output
        llm_output = params.get("llm_output")
        chronicDiseaseCode = chronicDiseaseCode or params.get("chronicDiseaseCode")
        logicTopology = logicTopology or params.get("logicTopology")

    if llm_output is None:
        for key in ("Output", "output", "result", "ruleRepository"):
            if kwargs.get(key) is not None:
                llm_output = kwargs[key]
                break
    if chronicDiseaseCode is None:
        chronicDiseaseCode = kwargs.get("chronicDiseaseCode")

    chronic_disease_code = _require_non_empty_string(chronicDiseaseCode, "chronicDiseaseCode")
    raw_rules, raw_topology = _read_payload(llm_output, logicTopology)
    rule_repository, rule_code_map = _normalize_rules(raw_rules, chronic_disease_code)
    if raw_topology is None:
        raise ValueError("llm_output 中缺少 logicTopology")
    if isinstance(raw_topology, str):
        raw_topology = _parse_json_text(raw_topology, "logicTopology")

    referenced_codes = set()
    logic_topology = _rewrite_logic_topology(raw_topology, rule_code_map, referenced_codes)
    expected_codes = set(rule_code_map.values())
    if referenced_codes != expected_codes:
        missing_codes = sorted(expected_codes - referenced_codes)
        raise ValueError(f"logicTopology 未引用规则：{', '.join(missing_codes)}")

    return {
        "ruleRepository": rule_repository,
        "logicTopology": logic_topology,
    }
