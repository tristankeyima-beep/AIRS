def _require_object(value, field_name):
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} 必须是完整 certification_list 对象")
    return value


def main(
    originalCertificationList=None,
    **kwargs,
) -> dict:
    """在知识库未命中分支中，原样返回最初的 certification_list。"""
    if isinstance(originalCertificationList, dict) and "originalCertificationList" in originalCertificationList:
        originalCertificationList = originalCertificationList.get("originalCertificationList")

    if originalCertificationList is None:
        originalCertificationList = kwargs.get("originalCertificationList")

    original = _require_object(originalCertificationList, "originalCertificationList")
    return {"certification_list": original}
