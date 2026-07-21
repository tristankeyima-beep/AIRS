# ADP 分支组装 certification_list 节点设计

## 目标

在 ADP 知识库检索分支末尾新增代码节点，将备案病种信息、最高相关 DOC 正文、结构化规则库和逻辑树重新组装为完整 `certification_list`，供既有智能审核流程直接消费。

## 节点输入

- `chronicDiseaseName`：备案病种提取节点输出的病种名称。
- `chronicDiseaseCode`：备案病种提取节点输出的病种编码。
- `knowledgeContent`：最高相关 DOC 提取节点输出的唯一正文。
- `ruleRepository`：规则库结构化节点输出的规则数组。
- `logicTopology`：规则库结构化节点输出的 AND / OR 逻辑树，兼容对象或 JSON 字符串。

## 元信息生成

`knowledgeContent` 是生成文档级元信息的确定来源，不依赖 LLM 已提取的规则字段：

- 从首个 `文档名：` 或 `文档名:` 行提取文档名，去除 `.md` 后缀；`meta.version` 固定为 `ADP-<文档名>`。
- 从首个 `来源：` 行提取来源；若未找到，再取第一条规则的非空 `ruleSource`；两者都没有时抛出错误。
- `meta.createdAt` 使用代码节点运行当日，格式 `YYYY-MM-DD`。
- `meta.description` 固定为 `由 ADP 知识库检索结果生成`。

## 输出协议

```json
{
  "certification_list": {
    "meta": {
      "version": "ADP-尿毒症透析-认定标准-v20260517",
      "chronicDiseaseName": "尿毒症透析",
      "chronicDiseaseCode": "M07801",
      "createdAt": "2026-07-21",
      "description": "由 ADP 知识库检索结果生成",
      "sourceFile": "八类疾病准入条件及细则-20260517.xlsx"
    },
    "ruleRepository": [],
    "logicTopology": {}
  }
}
```

## 校验

节点必须拒绝以下输入：

- 病种名称、病种编码或 `knowledgeContent` 为空；
- 文档名无法从 `knowledgeContent` 提取；
- 规则库不是非空对象数组；
- 逻辑树无法解析、节点类型非法、GROUP 缺少合法 AND / OR 与 children；
- `RULE_REF.ruleCode` 为空或未出现在 `ruleRepository` 中；
- 文档正文和规则库都没有可用来源信息。

校验通过后，`certification_list` 可直接绑定既有审核流程的同名 `obj` 入参。

## 交付

在 `对接ADP知识库/将检索结果转为rule_repository/` 新增：

- `代码-组装certification_list.py`
- `【代码出入参说明】代码-组装certification_list.md`

使用尿毒症检索正文、`M07801`、结构化规则库和 AND 逻辑树验证：版本包含文档名、来源正确、逻辑树引用完整并成功输出完整对象。
