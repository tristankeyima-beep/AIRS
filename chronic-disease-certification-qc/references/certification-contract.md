# 慢特病认定标准数据契约

本契约定义门诊慢特病智能审核系统使用的完整认定标准对象。系统直接消费整个对象，以读取规则、取证指引和规则逻辑；它不依赖任何特定工作流平台、接口或配置。

## Formal root

正式标准是一个 JSON 对象，根节点**直接**且仅以业务结构承载以下三个字段：

- `meta`：对象，标准元数据。
- `ruleRepository`：非空数组，规则库。
- `logicTopology`：对象，规则逻辑拓扑。

输入兼容层可以从 `certification_list`、`output`、`result`、`data` 任意层级的嵌套包装中取出该对象。包装仅用于输入兼容；正式输出绝不保留包装。

## Metadata

`meta` 必须包含以下非空字符串：

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | string | 标准版本，例如 `V20260724` |
| `chronicDiseaseName` | string | 病种名称 |
| `chronicDiseaseCode` | string | 病种编码，必须以两位数字结尾 |
| `createdAt` | string | 创建日期或时间文本 |
| `description` | string | 标准说明 |
| `sourceFile` | string | 标准来源文件 |

## Rules and keyword guides

`ruleRepository` 必须为非空数组；每一项都是规则对象，包含：

| Field | Type | Requirement |
| --- | --- | --- |
| `ruleCode` | string | 必填，全文唯一 |
| `ruleContent` | string | 必填且非空，表达认定要求 |
| `ruleSource` | string | 必须是字符串，可为空 |
| `experience` | string | 必须是字符串，可为空 |
| `sourceRuleContent` | string | 必填且非空，保留来源规则内容 |
| `sourceMdFile` | string | 必须是字符串，可为空 |
| `sourceSection` | string | 必须是字符串，可为空 |
| `ruleKeywordGuide` | array | 非空，取证/判断指引 |

每个 `ruleKeywordGuide` 条目必须为对象，包含全文唯一的非空字符串 `keywordCode`、`dataType`、布尔值 `required`、非空字符串 `keywordContent` 与 `enumOptions`。

- `dataType` 只能是 `enum` 或 `string`。
- 当 `dataType` 为 `enum` 时，`enumOptions` 必须是非空数组，且每个选项都是非空字符串。
- 当 `dataType` 为 `string` 时，`enumOptions` 必须严格为 `[]`。

正式契约没有 `number`、`time` 或其他扩展数据类型。数值阈值、计量单位、时间跨度和持续时间须清楚写在 `ruleContent` 或 `keywordContent` 中。

## Logic topology

`logicTopology` 是递归节点，节点类型只允许：

- `GROUP`：必须有 `operator`（仅 `AND` 或 `OR`）和非空 `children` 数组；每个 child 也是一个拓扑节点。
- `RULE_REF`：必须有 `ruleCode`，且该值引用 `ruleRepository` 中现有的规则编码。

每条规则必须被拓扑引用一次，且不能重复引用。这样审核系统可以完整、无歧义地解释认定关系。

## Deterministic finalization

草稿使用临时规则 ID，例如 `R001`。每个 `tempRuleId` 必须匹配 `R` 后跟三位数字，且在草稿中唯一。最终编码由程序确定，不由模型选择：

1. 取 `meta.chronicDiseaseCode` 的末两位数字为前缀。
2. 按草稿 `ruleRepository` 的 1 起始顺序生成规则编码：`<prefix><三位规则序号>`，例如病种编码 `CS01` 的第一条规则是 `01001`。
3. 按每条规则内指引的 1 起始顺序生成关键词编码：`<ruleCode><三位指引序号>`，例如 `01001001`。
4. 将拓扑中的临时规则 ID 重写为最终规则编码；未知临时引用会使定稿失败。

定稿结果必须通过本契约校验，并移除 `tempRuleId`。正式结构不应添加未定义的扩展字段来表达额外类型或执行语义。

## Canonical example

[`../tests/fixtures/valid-certification.json`](../tests/fixtures/valid-certification.json) 是最小、有效的正式标准示例：它包含病种 `CS01` 的一个规则、一个枚举取证指引和 `AND` 规则引用拓扑。它也是实现和集成测试的规范化参考。
