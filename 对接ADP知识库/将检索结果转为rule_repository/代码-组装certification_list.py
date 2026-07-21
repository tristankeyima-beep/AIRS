import json
import re
from datetime import date


WRAPPER_KEYS = ("Output", "output", "result", "data", "input", "inputs", "params")


def _parse_json(value, field_name):
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} 不能为空")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{field_name} 必须是合法 JSON") from error


def _require_string(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串")
    return value.strip()


def _unwrap_rule_repository(value):
    value = _parse_json(value, "ruleRepository")
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        raise ValueError("ruleRepository 必须是数组、对象或 JSON 字符串")
    if isinstance(value.get("ruleRepository"), list):
        return value["ruleRepository"]
    for key in WRAPPER_KEYS:
        if key in value:
            return _unwrap_rule_repository(value[key])
    raise ValueError("ruleRepository 中未找到规则数组")


def _unwrap_logic_topology(value):
    value = _parse_json(value, "logicTopology")
    if not isinstance(value, dict):
        raise ValueError("logicTopology 必须是对象或 JSON 字符串")
    if "logicTopology" in value:
        return _unwrap_logic_topology(value["logicTopology"])
    if value.get("type") in ("GROUP", "RULE_REF"):
        return value
    for key in WRAPPER_KEYS:
        if key in value:
            return _unwrap_logic_topology(value[key])
    raise ValueError("logicTopology 中未找到逻辑树对象")


def _validate_logic_topology(node, rule_codes):
    if not isinstance(node, dict):
        raise ValueError("logicTopology 节点必须是对象")
    if node.get("type") == "RULE_REF":
        rule_code = _require_string(node.get("ruleCode"), "RULE_REF.ruleCode")
        if rule_code not in rule_codes:
            raise ValueError(f"logicTopology 引用了不存在的规则：{rule_code}")
        return
    if node.get("type") != "GROUP":
        raise ValueError("logicTopology 节点 type 只能是 GROUP 或 RULE_REF")
    if node.get("operator") not in ("AND", "OR"):
        raise ValueError("GROUP.operator 只能是 AND 或 OR")
    children = node.get("children")
    if not isinstance(children, list) or not children:
        raise ValueError("GROUP.children 必须是非空数组")
    for child in children:
        _validate_logic_topology(child, rule_codes)


def main(
    chronicDiseaseName=None,
    chronicDiseaseCode=None,
    documentName=None,
    ruleRepository=None,
    logicTopology=None,
    **kwargs,
) -> dict:
    """将 ADP 分支输出组装为现有审核流程可用的 certification_list。"""
    if isinstance(chronicDiseaseName, dict) and any(
        key in chronicDiseaseName
        for key in ("chronicDiseaseName", "chronicDiseaseCode", "ruleRepository", "logicTopology")
    ):
        params = chronicDiseaseName
        chronicDiseaseName = params.get("chronicDiseaseName")
        chronicDiseaseCode = chronicDiseaseCode or params.get("chronicDiseaseCode")
        documentName = documentName or params.get("documentName")
        ruleRepository = ruleRepository if ruleRepository is not None else params.get("ruleRepository")
        logicTopology = logicTopology if logicTopology is not None else params.get("logicTopology")

    chronic_disease_name = _require_string(
        chronicDiseaseName if chronicDiseaseName is not None else kwargs.get("chronicDiseaseName"),
        "chronicDiseaseName",
    )
    chronic_disease_code = _require_string(
        chronicDiseaseCode if chronicDiseaseCode is not None else kwargs.get("chronicDiseaseCode"),
        "chronicDiseaseCode",
    )
    document_name = _require_string(
        documentName if documentName is not None else kwargs.get("documentName"),
        "documentName",
    )

    rule_repository = _unwrap_rule_repository(
        ruleRepository if ruleRepository is not None else kwargs.get("ruleRepository")
    )
    if not rule_repository:
        raise ValueError("ruleRepository 至少包含一条规则")
    rule_codes = set()
    for index, rule in enumerate(rule_repository, start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"第 {index} 条规则必须是对象")
        rule_code = _require_string(rule.get("ruleCode"), f"第 {index} 条规则 ruleCode")
        if rule_code in rule_codes:
            raise ValueError(f"ruleRepository 存在重复 ruleCode：{rule_code}")
        rule_codes.add(rule_code)

    logic_topology = _unwrap_logic_topology(
        logicTopology if logicTopology is not None else kwargs.get("logicTopology")
    )
    _validate_logic_topology(logic_topology, rule_codes)

    document_stem = re.sub(r"\.md$", "", document_name, flags=re.IGNORECASE).strip()
    version = document_stem if document_stem.startswith("ADP-") else f"ADP-{document_stem}"
    first_rule_source = rule_repository[0].get("ruleSource")
    source_file = first_rule_source.strip() if isinstance(first_rule_source, str) and first_rule_source.strip() else "ADP知识库检索结果"

    return {
        "certification_list": {
            "meta": {
                "version": version,
                "chronicDiseaseName": chronic_disease_name,
                "chronicDiseaseCode": chronic_disease_code,
                "createdAt": date.today().isoformat(),
                "description": "由 ADP 知识库检索结果生成",
                "sourceFile": source_file,
            },
            "ruleRepository": rule_repository,
            "logicTopology": logic_topology,
        }
    }
