def _require_object(value, field_name):
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} 必须是完整 certification_list 对象")
    return value


def _require_condition_index(value):
    if isinstance(value, bool):
        raise ValueError("ConditionIndex 必须是 1 或 2")
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            value = int(value)
    if value not in (1, 2):
        raise ValueError("ConditionIndex 必须是 1 或 2")
    return value


def main(
    ConditionIndex=None,
    originalCertificationList=None,
    assembledCertificationList=None,
    **kwargs,
) -> dict:
    """根据条件节点的 ConditionIndex 输出原始或 ADP 组装的 certification_list。"""
    if isinstance(ConditionIndex, dict) and "ConditionIndex" in ConditionIndex:
        params = ConditionIndex
        ConditionIndex = params.get("ConditionIndex")
        originalCertificationList = (
            originalCertificationList
            if originalCertificationList is not None
            else params.get("originalCertificationList")
        )
        assembledCertificationList = (
            assembledCertificationList
            if assembledCertificationList is not None
            else params.get("assembledCertificationList")
        )
    elif isinstance(originalCertificationList, dict) and "originalCertificationList" in originalCertificationList:
        params = originalCertificationList
        originalCertificationList = params.get("originalCertificationList")
        ConditionIndex = ConditionIndex if ConditionIndex is not None else params.get("ConditionIndex")
        assembledCertificationList = (
            assembledCertificationList
            if assembledCertificationList is not None
            else params.get("assembledCertificationList")
        )

    if originalCertificationList is None:
        originalCertificationList = kwargs.get("originalCertificationList")
    if assembledCertificationList is None:
        assembledCertificationList = kwargs.get("assembledCertificationList")
    if ConditionIndex is None:
        ConditionIndex = kwargs.get("ConditionIndex")

    original = _require_object(originalCertificationList, "originalCertificationList")
    condition_index = _require_condition_index(ConditionIndex)
    if condition_index == 1 or assembledCertificationList is None or (
        isinstance(assembledCertificationList, str) and not assembledCertificationList.strip()
    ):
        return {"certification_list": original}

    assembled = _require_object(assembledCertificationList, "assembledCertificationList")
    return {"certification_list": assembled}
