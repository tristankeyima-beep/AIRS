#!/usr/bin/env python3
"""Render a versioned ADP audit result with a fixed offline template."""

import argparse
import json
import os
import pathlib
import re
import sys
import tempfile
import unicodedata
from html.parser import HTMLParser


SCHEMA_VERSION = "adp-audit-result-1.0"
TEMPLATE_VERSION = "audit-result-template-1.0"
PLACEHOLDER = "__AUDIT_DATA_JSON__"
SLOT = (
    '<script id="audit-data" type="application/json">'
    + PLACEHOLDER
    + "</script>"
)
SLOT_PATTERN = re.compile(
    r'(<script id="audit-data" type="application/json">)'
    r"(.*?)"
    r"(</script>)",
    re.DOTALL,
)


class RenderError(Exception):
    """A safe, user-facing audit rendering failure."""


class ArgumentInputError(Exception):
    """A command argument failure that does not retain raw argument text."""


class StableArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentInputError("命令参数无效")


class AuditDataSlotInspector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.elements = []
        self.active_script = None
        self.has_duplicate_attributes = False

    def handle_starttag(self, tag, attrs):
        attribute_map = {}
        for name, value in attrs:
            normalized_name = name.lower()
            if normalized_name in attribute_map:
                self.has_duplicate_attributes = True
                continue
            attribute_map[normalized_name] = value
        if attribute_map.get("id") != "audit-data":
            return
        element = {
            "tag": tag,
            "type": attribute_map.get("type"),
            "content": [],
        }
        self.elements.append(element)
        if tag == "script":
            self.active_script = element

    def handle_data(self, data):
        if self.active_script is not None:
            self.active_script["content"].append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.active_script = None


def _require_text(value, field):
    if not isinstance(value, str):
        raise RenderError("审核结果字段无效: " + field)


def _require_integer(value, field):
    if isinstance(value, bool) or not isinstance(value, int):
        raise RenderError("审核结果字段无效: " + field)


def _validate_audit_id(value):
    _require_text(value, "audit.auditId")
    if (
        not value
        or value in (".", "..")
        or "/" in value
        or "\\" in value
        or any(unicodedata.category(character) == "Cc" for character in value)
    ):
        raise RenderError("审核流水号包含不安全的文件名字符")


def _validate_rules(rules):
    if not isinstance(rules, list):
        raise RenderError("审核结果字段无效: ruleResults")
    for index, rule in enumerate(rules):
        prefix = "ruleResults[" + str(index) + "]"
        if not isinstance(rule, dict):
            raise RenderError("审核结果字段无效: " + prefix)
        for name in (
            "ruleCode",
            "ruleContent",
            "ruleResult",
            "reasoningContent",
        ):
            _require_text(rule.get(name), prefix + "." + name)
        for name in ("ruleKeywordGuide", "suspicionList"):
            if not isinstance(rule.get(name), list):
                raise RenderError(
                    "审核结果字段无效: " + prefix + "." + name
                )
        _validate_guides(rule["ruleKeywordGuide"], prefix)
        _validate_suspicions(rule["suspicionList"], prefix)


def _validate_guides(guides, rule_prefix):
    for guide_index, guide in enumerate(guides):
        prefix = (
            rule_prefix
            + ".ruleKeywordGuide["
            + str(guide_index)
            + "]"
        )
        if not isinstance(guide, dict):
            raise RenderError("审核结果字段无效: " + prefix)
        _require_text(guide.get("keyword"), prefix + ".keyword")
        results = guide.get("results")
        if not isinstance(results, list):
            raise RenderError("审核结果字段无效: " + prefix + ".results")
        for result_index, evidence in enumerate(results):
            evidence_prefix = (
                prefix + ".results[" + str(result_index) + "]"
            )
            if not isinstance(evidence, dict):
                raise RenderError("审核结果字段无效: " + evidence_prefix)
            for name in (
                "materialName",
                "materialId",
                "materialSource",
                "rawText",
                "value",
            ):
                _require_text(
                    evidence.get(name),
                    evidence_prefix + "." + name,
                )


def _validate_suspicions(suspicions, rule_prefix):
    for suspicion_index, suspicion in enumerate(suspicions):
        prefix = (
            rule_prefix
            + ".suspicionList["
            + str(suspicion_index)
            + "]"
        )
        if not isinstance(suspicion, dict):
            raise RenderError("审核结果字段无效: " + prefix)
        for name in ("suspicionType", "detail"):
            _require_text(suspicion.get(name), prefix + "." + name)
        sources = suspicion.get("sources")
        if not isinstance(sources, list):
            raise RenderError("审核结果字段无效: " + prefix + ".sources")
        for source_index, source in enumerate(sources):
            source_prefix = (
                prefix + ".sources[" + str(source_index) + "]"
            )
            if isinstance(source, str):
                continue
            if not isinstance(source, dict):
                raise RenderError("审核结果字段无效: " + source_prefix)
            for name in ("materialName", "materialId"):
                _require_text(
                    source.get(name),
                    source_prefix + "." + name,
                )


def validate_result(result):
    if not isinstance(result, dict):
        raise RenderError("审核结果必须是对象")
    if result.get("schemaVersion") != SCHEMA_VERSION:
        raise RenderError("审核结果 Schema 版本不受支持")
    if result.get("templateVersion") != TEMPLATE_VERSION:
        raise RenderError("审核结果模板版本不受支持")

    _require_text(result.get("generatedAt"), "generatedAt")

    audit = result.get("audit")
    execution = result.get("execution")
    if not isinstance(audit, dict) or not isinstance(execution, dict):
        raise RenderError("审核结果结构不完整")

    _validate_audit_id(audit.get("auditId"))
    for name in (
        "diseaseName",
        "diseaseCode",
        "finalResult",
        "advice",
    ):
        _require_text(audit.get(name), "audit." + name)
    _require_integer(audit.get("materialCount"), "audit.materialCount")

    _validate_rules(result.get("ruleResults"))

    for name in ("profile", "workflowRunId", "requestId"):
        _require_text(execution.get(name), "execution." + name)
    _require_integer(execution.get("runEnv"), "execution.runEnv")


def _safe_embedded_json(result):
    try:
        serialized = json.dumps(
            result,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise RenderError("审核结果无法安全序列化") from error
    return (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _validate_template_slot(template):
    inspector = AuditDataSlotInspector()
    inspector.feed(template)
    inspector.close()
    if inspector.has_duplicate_attributes or len(inspector.elements) != 1:
        raise RenderError("固定模板数据槽无效")
    element = inspector.elements[0]
    if (
        element["tag"] != "script"
        or element["type"] != "application/json"
        or "".join(element["content"]) != PLACEHOLDER
    ):
        raise RenderError("固定模板数据槽无效")


def render_result(result, template_path):
    validate_result(result)
    try:
        template = pathlib.Path(template_path).read_text(encoding="utf-8")
    except OSError as error:
        raise RenderError("无法读取固定审核结果模板") from error

    _validate_template_slot(template)
    matches = list(SLOT_PATTERN.finditer(template))
    if (
        len(matches) != 1
        or matches[0].group(2) != PLACEHOLDER
        or template.count(PLACEHOLDER) != 1
        or template.count(SLOT) != 1
    ):
        raise RenderError("固定模板数据槽无效")

    embedded = _safe_embedded_json(result)
    html = template.replace(PLACEHOLDER, embedded, 1)
    rendered_matches = list(SLOT_PATTERN.finditer(html))
    if len(rendered_matches) != 1:
        raise RenderError("可视化数据与审核 JSON 不一致")
    try:
        rendered_result = json.loads(rendered_matches[0].group(2))
    except json.JSONDecodeError as error:
        raise RenderError("可视化数据与审核 JSON 不一致") from error
    if rendered_result != result:
        raise RenderError("可视化数据与审核 JSON 不一致")
    return html


def write_html(result, template_path, output_dir):
    html = render_result(result, template_path)
    directory = pathlib.Path(output_dir)
    audit_id = result["audit"]["auditId"]
    filename = audit_id + "-智能审核结果.html"
    temporary_path = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=filename + ".",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = pathlib.Path(temporary.name)
            temporary.write(html)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        return path
    except OSError as error:
        raise RenderError("无法原子写入审核结果 HTML") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def main(argv=None, stdout=sys.stdout):
    parser = StableArgumentParser(
        description="从固定模板生成慢病智能审核 HTML"
    )
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--output-dir", required=True)
    try:
        args = parser.parse_args(argv)
        result = json.loads(
            pathlib.Path(args.input_json).read_text(encoding="utf-8")
        )
        html_path = write_html(
            result,
            args.template,
            args.output_dir,
        ).resolve()
        response = {"ok": True, "htmlPath": str(html_path)}
        status = 0
    except ArgumentInputError:
        response = {
            "ok": False,
            "error": {
                "type": "render",
                "message": "命令参数无效",
            },
        }
        status = 1
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        MemoryError,
        RenderError,
    ):
        response = {
            "ok": False,
            "error": {
                "type": "render",
                "message": "无法生成智能审核结果 HTML",
            },
        }
        status = 1
    print(
        json.dumps(
            response,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        file=stdout,
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
