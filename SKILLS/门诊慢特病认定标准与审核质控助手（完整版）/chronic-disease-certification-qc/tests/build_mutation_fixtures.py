#!/usr/bin/env python3
import copy
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
GENERATED = FIXTURES / "generated"
CASE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CASE_FILES = {
    "materials.txt",
    "standard.txt",
    "audit-result.json",
    "expected.json",
}


def _expected(conclusion, risk, issues, must_find, must_not, *, invariant=False):
    return {
        "expectedQcConclusion": conclusion,
        "expectedRisk": risk,
        "expectedIssues": list(issues),
        "mustFindText": list(must_find),
        "mustNotReport": list(must_not),
        "mutationKind": "invariance" if invariant else "defect",
        "expectedInvariant": invariant,
    }


def _correct_expected(must_find):
    return _expected(
        "可靠",
        "未发现明显风险",
        [],
        must_find,
        ["证据不足"],
        invariant=True,
    )


# Every generated case starts from one of these self-consistent bases. A base may
# correctly pass or correctly reject; "correct" means its inputs and result agree.
BASE_CORRECT = {
    "diagnosis": {
        "materials": ["诊断证明：明确诊断为测试病种。"],
        "standard": "认定标准：已明确诊断为测试病种。",
        "audit": {
            "finalResult": "通过",
            "advice": "明确诊断条件满足",
        },
        "expected": _correct_expected(["明确诊断为测试病种"]),
    },
    "treatment": {
        "materials": ["治疗记录：患者已经接受长期治疗三年。"],
        "standard": "认定标准：患者已经接受长期治疗。",
        "audit": {
            "finalResult": "通过",
            "advice": "长期治疗条件满足",
        },
        "expected": _correct_expected(["患者已经接受长期治疗三年"]),
    },
    "logic-and-rejection": {
        "materials": ["检查记录：条件A已满足。"],
        "standard": "逻辑：且\n认定标准：条件A满足；条件B满足。",
        "audit": {
            "finalResult": "不通过",
            "advice": "条件B缺失，因此不通过",
        },
        "expected": _correct_expected(["条件A已满足"]),
    },
    "compound": {
        "materials": [
            "诊断证明：已明确诊断为测试病种。",
            "治疗记录：患者需继续治疗。",
        ],
        "standard": "认定标准：已明确诊断为测试病种，且需继续治疗。",
        "audit": {
            "finalResult": "通过",
            "advice": "诊断与继续治疗条件均满足",
        },
        "expected": _correct_expected(
            ["诊断证明：已明确诊断为测试病种", "治疗记录：患者需继续治疗"]
        ),
    },
}


def negate_claim(text):
    if "明确诊断为" not in text:
        raise ValueError("文本中没有可否定的“明确诊断为”")
    return text.replace("明确诊断为", "已明确排除", 1)


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


def _derive(base, base_name, expected):
    case = copy.deepcopy(base)
    case["baseCase"] = base_name
    case["expected"] = expected
    return case


def delete_key_evidence(base):
    case = _derive(
        base,
        "diagnosis",
        _expected(
            "不可靠",
            "错误放行风险",
            ["关键证据缺失"],
            ["本次仅登记随访日期"],
            ["材料中已有明确诊断"],
        ),
    )
    case["materials"] = ["门诊记录：本次仅登记随访日期。"]
    return case


def negate_diagnosis(base):
    case = _derive(
        base,
        "diagnosis",
        _expected(
            "不可靠",
            "错误放行风险",
            ["证据含义提取错误"],
            ["已明确排除测试病种"],
            ["材料支持明确诊断"],
        ),
    )
    case["materials"][0] = negate_claim(case["materials"][0])
    return case


def weaken_to_suspected(base):
    case = _derive(
        base,
        "diagnosis",
        _expected(
            "不可靠",
            "错误放行风险",
            ["过度推理"],
            ["疑似测试病种"],
            ["已经明确确诊"],
        ),
    )
    case["materials"][0] = weaken_claim(case["materials"][0])
    return case


def weaken_treatment(base):
    case = _derive(
        base,
        "treatment",
        _expected(
            "不可靠",
            "错误放行风险",
            ["过度推理"],
            ["建议评估是否需要长期治疗"],
            ["长期治疗事实已明确"],
        ),
    )
    case["materials"][0] = weaken_claim(case["materials"][0])
    return case


def flip_final(base):
    case = _derive(
        base,
        "diagnosis",
        _expected(
            "不可靠",
            "错误拒绝风险",
            ["最终结论翻转错误"],
            ["明确诊断为测试病种"],
            ["材料不支持诊断"],
        ),
    )
    case["audit"]["finalResult"] = flip_final_result(case["audit"]["finalResult"])
    return case


def and_to_or(base):
    case = _derive(
        base,
        "logic-and-rejection",
        _expected(
            "不可靠",
            "错误拒绝风险",
            ["OR 逻辑计算错误"],
            ["条件A已满足"],
            ["条件A也缺失"],
        ),
    )
    case["standard"] = case["standard"].replace("逻辑：且", "逻辑：或", 1)
    return case


def claim_missing_while_retaining_evidence(base):
    case = _derive(
        base,
        "treatment",
        _expected(
            "不可靠",
            "错误拒绝风险",
            ["误报缺失"],
            ["患者已经接受长期治疗三年"],
            ["材料确实没有治疗记录"],
        ),
    )
    case["audit"] = {
        "finalResult": "不通过",
        "advice": "缺少长期治疗证据",
    }
    return case


def contradict_reason_and_result(base):
    case = _derive(
        base,
        "diagnosis",
        _expected(
            "存在重大疑点",
            "暂时无法判断",
            ["审核理由与最终结论矛盾"],
            ["明确诊断为测试病种"],
            ["审核理由确认条件满足"],
        ),
    )
    case["audit"]["advice"] = "明确诊断条件不满足"
    return case


def reorder_case_materials(base):
    case = _derive(
        base,
        "compound",
        _expected(
            base["expected"]["expectedQcConclusion"],
            base["expected"]["expectedRisk"],
            base["expected"]["expectedIssues"],
            ["治疗记录：患者需继续治疗", "诊断证明：已明确诊断为测试病种"],
            ["材料顺序改变导致结论变化"],
            invariant=True,
        ),
    )
    case["materials"] = reorder_materials(case["materials"])
    return case


def add_unrelated_material(base):
    case = _derive(
        base,
        "diagnosis",
        _expected(
            base["expected"]["expectedQcConclusion"],
            base["expected"]["expectedRisk"],
            base["expected"]["expectedIssues"],
            ["挂号记录：就诊序号为001", "明确诊断为测试病种"],
            ["无关材料改变审核结论"],
            invariant=True,
        ),
    )
    case["materials"].insert(0, "挂号记录：就诊序号为001。")
    return case


def build_cases():
    return {
        "and-to-or": and_to_or(BASE_CORRECT["logic-and-rejection"]),
        "deleted-key-evidence": delete_key_evidence(BASE_CORRECT["diagnosis"]),
        "false-missing-with-evidence": claim_missing_while_retaining_evidence(
            BASE_CORRECT["treatment"]
        ),
        "flipped-final-result": flip_final(BASE_CORRECT["diagnosis"]),
        "negated-diagnosis": negate_diagnosis(BASE_CORRECT["diagnosis"]),
        "reason-result-contradiction": contradict_reason_and_result(
            BASE_CORRECT["diagnosis"]
        ),
        "reordered-materials": reorder_case_materials(BASE_CORRECT["compound"]),
        "unrelated-material-added": add_unrelated_material(BASE_CORRECT["diagnosis"]),
        "weakened-diagnosis": weaken_to_suspected(BASE_CORRECT["diagnosis"]),
        "weakened-treatment": weaken_treatment(BASE_CORRECT["treatment"]),
    }


def _absolute_lexical(path):
    return Path(os.path.abspath(os.fspath(path)))


def _reject_symlink_components(path, boundary):
    path = _absolute_lexical(path)
    boundary = _absolute_lexical(boundary)
    if path != boundary and boundary not in path.parents:
        raise ValueError("待检查路径必须位于安全边界内")
    current = boundary
    if current.is_symlink():
        raise ValueError(f"路径组件不能是符号链接：{current}")
    relative_parts = () if path == boundary else path.relative_to(boundary).parts
    for part in relative_parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"路径组件不能是符号链接：{current}")


def _validate_output_root(output_root, trusted_base, trusted_anchor):
    output_root = _absolute_lexical(output_root)
    trusted_base = _absolute_lexical(trusted_base)
    trusted_anchor = _absolute_lexical(trusted_anchor)
    if output_root.name != "generated":
        raise ValueError("输出目录名必须是 generated")
    if not trusted_anchor.exists() or not trusted_anchor.is_dir():
        raise ValueError("trusted_anchor 必须是已存在的普通目录")
    if trusted_anchor.is_symlink():
        raise ValueError("trusted_anchor 不能是符号链接")
    if trusted_base == trusted_anchor or trusted_anchor not in trusted_base.parents:
        raise ValueError("可信目录必须位于 trusted_anchor 内")
    if output_root == trusted_base or trusted_base not in output_root.parents:
        raise ValueError("输出目录必须位于可信目录内")

    _reject_symlink_components(trusted_base, trusted_anchor)
    _reject_symlink_components(output_root, trusted_anchor)
    if not trusted_base.exists() or not trusted_base.is_dir():
        raise ValueError("可信目录必须是已存在的普通目录")
    if trusted_base.is_symlink():
        raise ValueError("可信目录不能是符号链接")

    anchor_resolved = trusted_anchor.resolve(strict=True)
    trusted_resolved = trusted_base.resolve(strict=True)
    if trusted_resolved == anchor_resolved or anchor_resolved not in trusted_resolved.parents:
        raise ValueError("解析后的可信目录必须位于 trusted_anchor 内")
    output_resolved = output_root.resolve(strict=False)
    if output_resolved == trusted_resolved or trusted_resolved not in output_resolved.parents:
        raise ValueError("解析后的输出目录必须位于可信目录内")
    if output_root.exists() and not output_root.is_dir():
        raise ValueError("生成目录必须是普通目录")

    if not output_root.parent.exists() or not output_root.parent.is_dir():
        raise ValueError("生成目录的父目录必须是已存在的普通目录")
    return output_root


def _single_newline(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("文本 fixture 必须是非空字符串")
    return text.rstrip("\r\n") + "\n"


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _build_payloads():
    payloads = {}
    for name, case in sorted(build_cases().items()):
        if not CASE_NAME.fullmatch(name):
            raise ValueError(f"非法案例目录名：{name}")
        case_payloads = {
            "materials.txt": _single_newline("\n".join(case["materials"])),
            "standard.txt": _single_newline(case["standard"]),
            "audit-result.json": _json_text(case["audit"]),
            "expected.json": _json_text(case["expected"]),
        }
        if set(case_payloads) != CASE_FILES:
            raise ValueError(f"案例文件合同不完整：{name}")
        for filename, text in sorted(case_payloads.items()):
            payloads[Path(name) / filename] = text.encode("utf-8")
    return payloads


def _preflight_targets(root, trusted_anchor, payloads):
    root_resolved = root.resolve(strict=False)
    for relative in payloads:
        target = root / relative
        case_dir = target.parent
        _reject_symlink_components(target, trusted_anchor)
        if case_dir.exists() and not case_dir.is_dir():
            raise ValueError(f"案例路径不是普通目录：{relative.parent}")
        if target.is_symlink():
            raise ValueError(f"拒绝覆盖符号链接：{relative}")
        if target.exists() and not target.is_file():
            raise ValueError(f"目标必须是普通文件：{relative}")
        target_resolved = target.resolve(strict=False)
        if root_resolved not in target_resolved.parents:
            raise ValueError(f"目标越出生成目录：{relative}")


def _write_staged_file(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, mode)


def _cleanup_staging(staging):
    if staging is None or not staging.exists():
        return
    if staging.is_symlink() or not staging.name.startswith(".fixture-stage-"):
        raise RuntimeError("拒绝清理非事务 staging 目录")
    shutil.rmtree(staging)


def _restore_file(target, data, mode):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=".fixture-rollback-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _rollback_transaction(journal, created_dirs, staging, root, root_created):
    errors = []
    for entry in reversed(journal):
        target = entry["target"]
        try:
            if entry["existed"]:
                _restore_file(target, entry["original"], entry["mode"])
            elif target.exists() or target.is_symlink():
                target.unlink()
        except Exception as exc:
            errors.append(f"{target}: {exc}")
    for directory in reversed(created_dirs):
        try:
            directory.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            errors.append(f"{directory}: {exc}")
    try:
        _cleanup_staging(staging)
    except Exception as exc:
        errors.append(f"staging: {exc}")
    if root_created:
        try:
            root.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            errors.append(f"{root}: {exc}")
    return errors


def _transactional_write(root, trusted_anchor, payloads):
    root_created = False
    staging = None
    journal = []
    created_dirs = []
    try:
        if not root.exists():
            root.mkdir(mode=0o755)
            root_created = True
        _reject_symlink_components(root, trusted_anchor)
        if not root.is_dir():
            raise ValueError("生成目录必须是普通目录")
        staging = Path(tempfile.mkdtemp(prefix=".fixture-stage-", dir=root))
        payload_root = staging / "payload"
        backup_root = staging / "backup"

        staged = []
        for relative, data in sorted(payloads.items(), key=lambda item: item[0].as_posix()):
            target = root / relative
            existed = target.exists()
            original = target.read_bytes() if existed else None
            mode = stat.S_IMODE(target.stat().st_mode) if existed else 0o644
            payload_path = payload_root / relative
            _write_staged_file(payload_path, data, mode)
            if existed:
                _write_staged_file(backup_root / relative, original, mode)
            staged.append(
                {
                    "target": target,
                    "payload": payload_path,
                    "existed": existed,
                    "original": original,
                    "mode": mode,
                }
            )

        for entry in staged:
            target = entry["target"]
            case_dir = target.parent
            if not case_dir.exists():
                case_dir.mkdir(mode=0o755)
                created_dirs.append(case_dir)
            _reject_symlink_components(target, trusted_anchor)
            if target.is_symlink():
                raise ValueError(f"拒绝覆盖符号链接：{target}")
            journal.append(entry)
            os.replace(entry["payload"], target)

        _cleanup_staging(staging)
        staging = None
        return
    except Exception as exc:
        rollback_errors = _rollback_transaction(
            journal,
            created_dirs,
            staging,
            root,
            root_created,
        )
        detail = f"；回滚异常：{' | '.join(rollback_errors)}" if rollback_errors else ""
        raise RuntimeError(f"事务生成失败，已执行尽力回滚：{exc}{detail}") from exc


def generate(output_root=None, trusted_base=None, trusted_anchor=None):
    """Generate all fixtures as one transactional batch with best-effort rollback."""
    custom_paths = output_root is not None or trusted_base is not None
    if custom_paths and trusted_anchor is None:
        raise ValueError("非默认生成必须显式提供 trusted_anchor")
    anchor = ROOT if trusted_anchor is None else Path(trusted_anchor)
    trusted = FIXTURES if trusted_base is None else Path(trusted_base)
    output = GENERATED if output_root is None else Path(output_root)
    root = _validate_output_root(output, trusted, anchor)
    payloads = _build_payloads()
    _preflight_targets(root, _absolute_lexical(anchor), payloads)
    _transactional_write(root, _absolute_lexical(anchor), payloads)
    return root


def build_mutation_fixtures(
    generated_root=None,
    *,
    trusted_base=None,
    trusted_anchor=None,
):
    """Build fixtures at the fixed default path or an explicitly anchored custom path.

    Custom generation never infers a trust boundary: ``generated_root``,
    ``trusted_base``, and ``trusted_anchor`` must be supplied together.
    """
    values = (generated_root, trusted_base, trusted_anchor)
    if all(value is None for value in values):
        return generate()
    if any(value is None for value in values):
        raise ValueError(
            "自定义 generated_root 必须同时显式提供 trusted_base 和 trusted_anchor"
        )
    return generate(
        output_root=Path(generated_root),
        trusted_base=Path(trusted_base),
        trusted_anchor=Path(trusted_anchor),
    )


def main():
    generate()


if __name__ == "__main__":
    main()
