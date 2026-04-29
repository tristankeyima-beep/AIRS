import ast
import json


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            if lines[0].strip().lower().startswith("```json"):
                return "\n".join(lines[1:-1]).strip()
            if lines[0].strip() == "```":
                return "\n".join(lines[1:-1]).strip()
    return text


def _try_parse_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None


def _extract_json_fragment(text: str) -> str | None:
    stripped = text.strip()
    if "{" in stripped and "}" in stripped:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if end > start:
            return stripped[start : end + 1]
    return None


def _normalize_source(source):
    if isinstance(source, str):
        return {"refContent": source}
    if not isinstance(source, dict):
        return {"refContent": str(source)}
    return {
        "mutexDiseasesName": source.get("mutexDiseasesName", ""),
        "materialId": source.get("materialId", ""),
        "materialName": source.get("materialName", ""),
        "refContent": source.get("refContent", ""),
    }


def _normalize_result(data):
    if not isinstance(data, dict):
        return {
            "reviewResult": "通过",
            "mutexDiseasesName": [],
            "reason": "未在患者材料中发现明确的互斥病种证据。",
        }

    hit_names = data.get("mutexDiseasesName", [])
    if isinstance(hit_names, str):
        hit_names = [hit_names] if hit_names else []
    elif not isinstance(hit_names, list):
        hit_names = [str(hit_names)]

    deduped_hit_names = []
    seen = set()
    for name in hit_names:
        if not isinstance(name, str):
            name = str(name)
        name = name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        deduped_hit_names.append(name)

    review_result = data.get("reviewResult", "")
    if review_result not in ("通过", "不通过"):
        review_result = "不通过" if deduped_hit_names else "通过"

    reason = data.get("reason", "")
    if not reason:
        if review_result == "不通过" and deduped_hit_names:
            reason = f"患者材料中明确含有互斥病种：{'、'.join(deduped_hit_names)}，所以审核不通过。"
        else:
            reason = "未在患者材料中发现明确的互斥病种证据。"

    return {
        "reviewResult": review_result,
        "mutexDiseasesName": deduped_hit_names,
        "reason": reason,
    }


def main(mutexReviewResult=None, **kwargs) -> dict:
    if mutexReviewResult is None:
        mutexReviewResult = kwargs.get("text")

    if isinstance(mutexReviewResult, dict):
        return _normalize_result(mutexReviewResult)

    if isinstance(mutexReviewResult, (bytes, bytearray)):
        mutexReviewResult = mutexReviewResult.decode("utf-8", errors="ignore")

    if isinstance(mutexReviewResult, str):
        stripped = _strip_json_fence(mutexReviewResult)
        parsed = _try_parse_json(stripped)
        if parsed is None:
            fragment = _extract_json_fragment(stripped)
            if fragment:
                parsed = _try_parse_json(fragment)
        if parsed is not None:
            return _normalize_result(parsed)

    return _normalize_result({})
