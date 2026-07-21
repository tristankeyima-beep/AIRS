def _require_object(value, field_name):
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} 必须是完整 certification_list 对象")
    return value


def main(
    originalCertificationList=None,
    assembledCertificationList=None,
    **kwargs,
) -> dict:
    """在条件分支汇合处，输出原始或 ADP 组装的 certification_list。"""
    if isinstance(originalCertificationList, dict) and "originalCertificationList" in originalCertificationList:
        params = originalCertificationList
        originalCertificationList = params.get("originalCertificationList")
        assembledCertificationList = (
            assembledCertificationList
            if assembledCertificationList is not None
            else params.get("assembledCertificationList")
        )

    if originalCertificationList is None:
        originalCertificationList = kwargs.get("originalCertificationList")
    if assembledCertificationList is None:
        assembledCertificationList = kwargs.get("assembledCertificationList")

    original = _require_object(originalCertificationList, "originalCertificationList")
    if assembledCertificationList is None or (
        isinstance(assembledCertificationList, str) and not assembledCertificationList.strip()
    ):
        return {"certification_list": original}

    assembled = _require_object(assembledCertificationList, "assembledCertificationList")
    return {"certification_list": assembled}
