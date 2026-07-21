# ADP 知识库对接：备案病种提取节点设计

## 目标

在“对接 ADP 知识库”分支的第一步，从上游完整认定标准 `certification_list` 中提取备案病种名称和编码，为下一步知识库检索提供稳定、最小的查询条件。

## 节点边界

节点只负责读取 `certification_list.meta`，输出：

- `chronicDiseaseName`：备案病种名称。
- `chronicDiseaseCode`：备案病种编码。

节点不检索知识库、不读取或改写 `ruleRepository`，也不透传完整认定标准。知识库检索及其结果重组为新 `rule_repository` 是后续节点的职责。

## 输入兼容性

入参变量名固定为 `certification_list`，兼容三种来源：

1. 腾讯智能体平台的 `obj`（推荐）。
2. 只包含一个完整认定标准对象的数组（取第一个对象）。
3. 历史流程传入的 JSON 字符串（解析后按前两种方式处理）。

有效认定标准必须是对象，且含 `meta.chronicDiseaseName`、`meta.chronicDiseaseCode` 两个非空字符串。输入为空、JSON 无法解析、数组为空、结构不正确或字段缺失时，节点抛出明确错误，避免使用空条件检索知识库。

## 输出协议

```json
{
  "chronicDiseaseName": "糖尿病",
  "chronicDiseaseCode": "M01603"
}
```

腾讯平台输出 Schema 配置为：

```text
chronicDiseaseName: str
chronicDiseaseCode: str
```

## 文件交付

目标目录新增两个文件：

- `【代码出入参说明】代码节点.md`：平台配置、字段契约、错误行为和测试示例。
- `代码节点.py`：可直接粘贴到腾讯智能体平台代码节点的 Python 实现。

## 验证

用 0604 智能审核流程中“糖尿病”的测试入参验证：输入完整 `certification_list` 后，输出 `糖尿病` 和 `M01603`。同时验证对象数组、JSON 字符串，以及缺少 `meta`、缺少任一病种字段、空数组等错误输入。
