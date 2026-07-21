import json


def main(certification_list=None, **kwargs) -> dict:
    """从完整认定标准中提取备案病种名称和编码。"""
    # 兼容平台整体传参：main({"certification_list": {...}})
    if isinstance(certification_list, dict) and "certification_list" in certification_list:
        certification_list = certification_list["certification_list"]

    if isinstance(certification_list, str):
        if not certification_list.strip():
            raise ValueError("certification_list 不能为空")
        try:
            data = json.loads(certification_list)
        except json.JSONDecodeError as error:
            raise ValueError("certification_list 必须是合法 JSON 字符串") from error
    else:
        data = certification_list

    # 兼容对象数组入参：只处理第一个完整认定标准。
    if isinstance(data, list):
        if not data:
            raise ValueError("certification_list 为空数组，无法提取备案病种")
        data = data[0]

    if not isinstance(data, dict):
        raise ValueError("certification_list 必须是对象、对象数组或 JSON 字符串")

    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("certification_list 中缺少 meta 对象")

    chronic_disease_name = meta.get("chronicDiseaseName")
    chronic_disease_code = meta.get("chronicDiseaseCode")
    if not isinstance(chronic_disease_name, str) or not chronic_disease_name.strip():
        raise ValueError("meta.chronicDiseaseName 不能为空字符串")
    if not isinstance(chronic_disease_code, str) or not chronic_disease_code.strip():
        raise ValueError("meta.chronicDiseaseCode 不能为空字符串")

    return {
        "chronicDiseaseName": chronic_disease_name.strip(),
        "chronicDiseaseCode": chronic_disease_code.strip(),
    }
