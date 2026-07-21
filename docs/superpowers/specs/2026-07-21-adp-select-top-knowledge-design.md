# ADP 检索结果最高相关 DOC 提取节点设计

## 目标

在“将检索结果转为 ruleRepository”的 LLM 节点之前新增一个代码节点，从 ADP 知识库检索结果中选出相关性最高的一条有效 DOC，仅将其 `Content` 输出为 `knowledgeContent`。

## 输入与选择规则

节点输入变量为 `knowledge_result`，接受 ADP 检索节点的对象或 JSON 字符串。有效候选必须同时满足：

1. 位于 `KnowledgeList` 数组中；
2. `KnowledgeType` 严格等于 `DOC`；
3. `Content` 是非空字符串；
4. `Confidence` 可转换为数字。

候选按 `Confidence` 从高到低选择。若分值相同，保持 `KnowledgeList` 的原始顺序，因此第一个同分 DOC 被选中。QA、空内容、缺失或不可解析置信度的条目一律忽略。

没有有效候选、输入 JSON 无法解析、顶层不是对象或 `KnowledgeList` 不是数组时，节点抛出 `ValueError`，防止 LLM 在空上下文或错误上下文中生成规则。

## 输出协议

节点只输出一个字段：

```json
{
  "knowledgeContent": "知识库中相关性最高 DOC 的完整 Content"
}
```

不输出检索列表、置信度、文档名或 QA 内容，避免把其他病种和无关上下文传入 LLM。

腾讯平台输出 Schema：

```text
knowledgeContent: str
```

## 下游变更

现有“将检索结果转为 ruleRepository”LLM 节点将输入变量从 `knowledge_result: obj` 改为 `knowledgeContent: str`。提示词只读取这个已筛选的 DOC 正文，不再自行筛选 `KnowledgeList`、忽略 QA 或处理多 DOC 去重。

`chronicDiseaseName`、`chronicDiseaseCode` 继续保留为 LLM 的上下文变量。后置“将 ADP 提取出的 ruleRepository 结构化”代码节点不变。

## 文件交付与验证

在 `对接ADP知识库/将检索结果转为rule_repository/` 新增：

- `代码-提取相关性最高的知识库结果.py`
- `【代码出入参说明】代码-提取相关性最高的知识库结果.md`

并更新：

- `【LLM节点配置说明】将检索结果转为rule_repository.md`

验证使用 `output (1).json`：应只输出尿毒症透析 DOC 的 `Content`。同时验证 JSON 字符串输入、QA 被忽略、置信度同分保持原顺序和没有有效 DOC 时抛错。
