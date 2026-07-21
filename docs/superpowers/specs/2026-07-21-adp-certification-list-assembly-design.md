# ADP 检索分支：文档名传递与 certification_list 组装设计

## 目标

完善 ADP 知识库检索分支的收口：最高相关 DOC 选择节点输出确定性文档名，新增代码节点将病种元信息、规则库和逻辑树组装为现有审核流程可直接消费的完整 `certification_list`。

## 最高相关 DOC 节点变更

现有输出从单字段改为：

```json
{
  "knowledgeContent": "DOC 的完整 Content",
  "documentName": "尿毒症透析-认定标准-v20260517.md"
}
```

文档名优先取最高相关候选的 `DocName`。若该字段为空，再从 `Content` 的首行 `文档名：...` 解析；两者都不可用时抛出错误。`knowledgeContent` 选择规则保持不变：只选有效 DOC，取最高 `Confidence`，同分保留原列表中较早结果。

## 新增组装节点

节点接收：

- `chronicDiseaseName`、`chronicDiseaseCode`：备案病种提取节点输出；
- `documentName`：最高相关 DOC 节点输出；
- `ruleRepository`、`logicTopology`：规则库结构化节点输出。

节点输出：

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

`version` 由去除 `.md` 后缀的 `documentName` 加 `ADP-` 前缀生成。`sourceFile` 优先使用第一条规则的 `ruleSource`；没有时使用固定值 `ADP知识库检索结果`。`createdAt` 使用节点执行日期（`YYYY-MM-DD`）。

## 校验与下游

组装节点必须校验病种名称、病种编码、文档名、规则库和逻辑树非空；并递归检查每个 `RULE_REF.ruleCode` 都存在于 `ruleRepository`。失败时抛出 `ValueError`，不产生半成品 `certification_list`。

最终输出的 `certification_list` 直接绑定到既有“规则库转可迭代数组”节点的同名入参。

## 交付文件

在 `对接ADP知识库/将检索结果转为rule_repository/`：

- 修改 `代码-提取相关性最高的知识库结果.py` 及其出入参说明；
- 新增 `代码-组装certification_list.py`；
- 新增 `【代码出入参说明】代码-组装certification_list.md`；
- 更新 LLM 节点说明中的前置节点输出说明。
