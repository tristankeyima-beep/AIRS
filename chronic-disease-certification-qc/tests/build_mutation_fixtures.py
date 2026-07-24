#!/usr/bin/env python3
import json
import os
import re
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "fixtures" / "generated"
CASE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CASE_FILES = {
    "materials.txt",
    "standard.txt",
    "audit-result.json",
    "expected.json",
}


def negate_claim(text):
    if "明确诊断为" not in text:
        raise ValueError("文本中没有可否定的“明确诊断为”")
    return text.replace("明确诊断为", "明确排除为", 1)


def weaken_claim(text):
    replacements = (
        ("明确诊断为", "疑似"),
        ("已经接受", "建议评估是否需要"),
        ("规律接受长期治疗", "建议评估是否需要长期治疗"),
    )
    for source, replacement in replacements:
        if source in text:
            return text.replace(source, replacement, 1)
    raise ValueError("文本中没有可弱化的明确事实")


def flip_final_result(value):
    try:
        return {"通过": "不通过", "不通过": "通过"}[value]
    except (KeyError, TypeError) as exc:
        raise ValueError("最终结论只能是“通过”或“不通过”") from exc


def reorder_materials(materials):
    return list(reversed(list(materials)))


def _expected(conclusion, risk, issues, must_find, must_not, *, invariant=False):
    return {
        "expectedQcConclusion": conclusion,
        "expectedRisk": risk,
        "expectedIssues": issues,
        "mustFindText": must_find,
        "mustNotReport": must_not,
        "mutationKind": "invariance" if invariant else "defect",
        "expectedInvariant": invariant,
    }


def mutation_cases():
    diagnosis = "出院诊断：明确诊断为测试病种。"
    treatment = "治疗经过：已经接受长期治疗三年。"
    reordered = reorder_materials(
        [
            "诊断证明：已明确诊断为测试病种。",
            "治疗记录：患者需继续治疗。",
        ]
    )
    return {
        "and-to-or": {
            "materials": "检查记录：条件A已满足。",
            "standard": "逻辑：或\n认定标准：条件A满足；条件B满足。",
            "audit": {
                "finalResult": "不通过",
                "advice": "条件B缺失，因此全部条件不满足",
            },
            "expected": _expected(
                "不可靠",
                "错误拒绝风险",
                ["OR 逻辑计算错误"],
                ["条件A已满足"],
                ["条件A也缺失"],
            ),
        },
        "deleted-key-evidence": {
            "materials": "门诊记录：本次仅登记随访日期。",
            "standard": "认定标准：已明确诊断为测试病种。",
            "audit": {
                "finalResult": "通过",
                "advice": "材料明确诊断为测试病种",
            },
            "expected": _expected(
                "不可靠",
                "错误放行风险",
                ["关键证据缺失"],
                ["本次仅登记随访日期"],
                ["材料中已有明确诊断"],
            ),
        },
        "false-missing-with-evidence": {
            "materials": "治疗记录：患者规律接受长期治疗三年。",
            "standard": "认定标准：患者已规律接受长期治疗。",
            "audit": {
                "finalResult": "不通过",
                "advice": "缺少长期治疗证据",
            },
            "expected": _expected(
                "不可靠",
                "错误拒绝风险",
                ["误报缺失"],
                ["患者规律接受长期治疗三年"],
                ["材料确实没有治疗记录"],
            ),
        },
        "flipped-final-result": {
            "materials": "诊断证明：已明确诊断为测试病种。",
            "standard": "认定标准：已明确诊断为测试病种。",
            "audit": {
                "finalResult": flip_final_result("通过"),
                "advice": "明确诊断条件满足",
            },
            "expected": _expected(
                "不可靠",
                "错误拒绝风险",
                ["最终结论翻转错误"],
                ["已明确诊断为测试病种"],
                ["材料不支持诊断"],
            ),
        },
        "negated-diagnosis": {
            "materials": negate_claim(diagnosis),
            "standard": "认定标准：已明确诊断为测试病种。",
            "audit": {
                "finalResult": "通过",
                "advice": "材料明确诊断为测试病种",
            },
            "expected": _expected(
                "不可靠",
                "错误放行风险",
                ["证据含义提取错误"],
                ["明确排除为测试病种"],
                ["材料支持明确诊断"],
            ),
        },
        "reason-result-contradiction": {
            "materials": "诊断证明：未明确诊断为测试病种。",
            "standard": "认定标准：已明确诊断为测试病种。",
            "audit": {
                "finalResult": "通过",
                "advice": "明确诊断条件不满足",
            },
            "expected": _expected(
                "存在重大疑点",
                "暂时无法判断",
                ["审核理由与最终结论矛盾"],
                ["未明确诊断为测试病种"],
                ["审核理由确认条件满足"],
            ),
        },
        "reordered-materials": {
            "materials": "\n".join(reordered),
            "standard": "认定标准：已明确诊断为测试病种，且需继续治疗。",
            "audit": {
                "finalResult": "通过",
                "advice": "诊断与继续治疗条件均满足",
            },
            "expected": _expected(
                "可靠",
                "未发现明显风险",
                [],
                ["治疗记录：患者需继续治疗", "诊断证明：已明确诊断为测试病种"],
                ["材料顺序改变导致结论变化"],
                invariant=True,
            ),
        },
        "unrelated-material-added": {
            "materials": "挂号记录：就诊序号为001。\n诊断证明：已明确诊断为测试病种。",
            "standard": "认定标准：已明确诊断为测试病种。",
            "audit": {
                "finalResult": "通过",
                "advice": "明确诊断条件满足",
            },
            "expected": _expected(
                "可靠",
                "未发现明显风险",
                [],
                ["挂号记录：就诊序号为001", "已明确诊断为测试病种"],
                ["无关材料改变审核结论"],
                invariant=True,
            ),
        },
        "weakened-diagnosis": {
            "materials": weaken_claim(diagnosis),
            "standard": "认定标准：已明确诊断为测试病种。",
            "audit": {
                "finalResult": "通过",
                "advice": "材料明确诊断为测试病种",
            },
            "expected": _expected(
                "不可靠",
                "错误放行风险",
                ["过度推理"],
                ["疑似测试病种"],
                ["已经明确确诊"],
            ),
        },
        "weakened-treatment": {
            "materials": weaken_claim(treatment),
            "standard": "认定标准：患者已经接受长期治疗。",
            "audit": {
                "finalResult": "通过",
                "advice": "患者已经接受长期治疗",
            },
            "expected": _expected(
                "不可靠",
                "错误放行风险",
                ["过度推理"],
                ["建议评估是否需要长期治疗"],
                ["长期治疗事实已明确"],
            ),
        },
    }


def _validate_generated_root(root):
    root = Path(root)
    if root.name != "generated" or root.parent.name != "fixtures":
        raise ValueError("生成目录必须是 fixtures/generated")
    if root.is_symlink() or root.parent.is_symlink():
        raise ValueError("生成目录及其父目录不能是符号链接")
    root.parent.mkdir(parents=True, exist_ok=True)
    if root.parent.is_symlink():
        raise ValueError("生成目录父目录不能是符号链接")
    if root.exists() and not root.is_dir():
        raise ValueError("生成目录必须是普通目录")
    root.mkdir(exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("生成目录必须是普通目录")
    return root


def _single_newline(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("文本 fixture 必须是非空字符串")
    return text.rstrip("\r\n") + "\n"


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _atomic_write(path, text):
    if path.is_symlink():
        raise ValueError(f"拒绝覆盖符号链接：{path.name}")
    data = text.encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _write_case(root, name, case):
    if not CASE_NAME.fullmatch(name):
        raise ValueError(f"非法案例目录名：{name}")
    case_dir = root / name
    if case_dir.is_symlink():
        raise ValueError(f"拒绝写入符号链接案例目录：{name}")
    case_dir.mkdir(exist_ok=True)
    if case_dir.is_symlink() or not case_dir.is_dir():
        raise ValueError(f"案例路径不是普通目录：{name}")

    payloads = {
        "materials.txt": _single_newline(case["materials"]),
        "standard.txt": _single_newline(case["standard"]),
        "audit-result.json": _json_text(case["audit"]),
        "expected.json": _json_text(case["expected"]),
    }
    if set(payloads) != CASE_FILES:
        raise ValueError(f"案例文件合同不完整：{name}")
    for filename in sorted(payloads):
        _atomic_write(case_dir / filename, payloads[filename])


def build_mutation_fixtures(generated_root=None):
    root = _validate_generated_root(GENERATED if generated_root is None else generated_root)
    cases = mutation_cases()
    for name in sorted(cases):
        _write_case(root, name, cases[name])
    return root


def main():
    build_mutation_fixtures()


if __name__ == "__main__":
    main()
