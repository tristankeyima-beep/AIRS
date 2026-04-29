import json
import re


def main(extraction_data=None, **kwargs) -> dict:
    """
    将模型出参转换为 Array<object>。
    输入格式: [ {"keywordCode": "10001001", "found": ..., "results": ...}, ... ]
    """
    if extraction_data is None:
        extraction_data = []

    if isinstance(extraction_data, str):
        text = extraction_data.strip()

        if text:
            # 去掉 <think>...</think>
            text = re.sub(r"^\s*<think>.*?</think>\s*", "", text, flags=re.S)

            extraction_data = json.loads(text)
        else:
            extraction_data = []

    if not isinstance(extraction_data, list):
        raise ValueError("精解结果必须是数组格式")

    extraction_data.sort(key=lambda x: str(x.get("keywordCode", "")))

    return {"extractionList": extraction_data}
