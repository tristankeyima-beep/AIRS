import json


def _load_mutex_diseases(mutexDiseases):
    if isinstance(mutexDiseases, str):
        data = json.loads(mutexDiseases) if mutexDiseases.strip() else []
    else:
        data = mutexDiseases or []

    if data is None:
        data = []

    if not isinstance(data, list):
        raise ValueError("mutexDiseases 必须是数组")

    return data


def main(mutexDiseases, currentDiseaseName: str = "", **kwargs) -> dict:
    """
    从 mutexDiseases 中提取互斥病种名称。
    """
    mutex_diseases = _load_mutex_diseases(mutexDiseases)

    mutex_diseases_names = []
    for item in mutex_diseases:
        if not isinstance(item, dict):
            continue
        name = item.get("mutexDiseasesName", "")
        if name:
            mutex_diseases_names.append(name)

    return {
        "currentDiseaseName": currentDiseaseName or kwargs.get("currentDiseaseName", ""),
        "mutexDiseasesName": mutex_diseases_names
    }
