def _require_object(value, field_name):
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} 必须是完整 certification_list 对象")
    return value


def main(
    knowledgeContent=None,
    originalCertificationList=None,
    assembledCertificationList=None,
    **kwargs,
) -> dict:
    """根据知识库是否命中病种，选择原始或 ADP 组装后的 certification_list。"""
    if isinstance(knowledgeContent, dict) and any(
        key in knowledgeContent
        for key in ("knowledgeContent", "originalCertificationList", "assembledCertificationList")
    ):
        params = knowledgeContent
        knowledgeContent = params.get("knowledgeContent")
        originalCertificationList = originalCertificationList or params.get("originalCertificationList")
        assembledCertificationList = assembledCertificationList or params.get("assembledCertificationList")

    if knowledgeContent is None:
        knowledgeContent = kwargs.get("knowledgeContent")
    if knowledgeContent is not None and not isinstance(knowledgeContent, str):
        raise ValueError("knowledgeContent 必须是字符串或为空")

    if originalCertificationList is None:
        originalCertificationList = kwargs.get("originalCertificationList")
    if assembledCertificationList is None:
        assembledCertificationList = kwargs.get("assembledCertificationList")

    original = _require_object(originalCertificationList, "originalCertificationList")
    assembled = _require_object(assembledCertificationList, "assembledCertificationList")

    selected = original if not (knowledgeContent or "").strip() else assembled
    return {"certification_list": selected}
