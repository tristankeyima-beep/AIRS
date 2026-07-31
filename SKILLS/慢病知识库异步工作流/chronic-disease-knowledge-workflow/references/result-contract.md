# 智能审核结果契约

正式结果顶层必须是对象，并严格使用以下稳定版本与字段。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schemaVersion` | string | 固定为 `adp-audit-result-1.0` |
| `templateVersion` | string | 固定为 `audit-result-template-1.0` |
| `generatedAt` | string | UTC ISO-8601 生成时间 |
| `audit` | object | 本次审核业务摘要 |
| `ruleResults` | array<object> | 工作流返回的逐条认定结果 |
| `execution` | object | 排障所需的最小执行标识 |

## `audit`

`audit` 必须完整包含：

- `auditId`：审核流水号；
- `diseaseName`：病种名称；
- `diseaseCode`：病种编码；
- `finalResult`：总审核结论；
- `advice`：审核建议；
- `materialCount`：申请材料数量，类型为整数。

## `ruleResults`

`ruleResults` 必须是对象数组，并遵守以下嵌套契约：

- `ruleResults` 的每一项必须是 object。
- `ruleCode`、`ruleContent`、`ruleResult`、`reasoningContent` 必须是 string。
- `ruleKeywordGuide` 必须是 array<object>；每个 guide 的 `keyword` 必须是 string；每个 guide 的 `results` 必须是 array<object>。
- 每条 evidence result 的 `materialId`、`materialName`、`materialSource`、`rawText`、`value` 必须是 string；来源缺失时允许空字符串，但禁止补造。
- `suspicionList` 若存在，必须是 array<object>；每项的 `suspicionType` 与 `detail` 必须是 string，`sources` 若存在，必须是 array。`sources` 的每个元素只能是 string 或 object；object 至少包含 `materialId` 或 `materialName` 之一，且 object 中存在的字段值均必须是 string。除上述受约束 object 外，禁止数字、布尔值和任意对象。

“原样保留”仅指字段值不改写，不改变工作流给出的规则结论、证据或建议。“类型规范化”仅允许解包 JSON 字符串，以及把缺失的可选 `suspicionList` 视为空数组；不得强制转换其他字段或填充推测值，不生成新事实。

正式结果不复制完整申请材料，只保留工作流已纳入逐条规则结果的必要证据片段，以减少敏感信息扩散。

## `execution`

`execution` 必须完整包含：

- `profile`：`cloud` 或 `provincial_intranet`；
- `runEnv`：运行环境整数；
- `workflowRunId`：工作流运行实例 ID；
- `requestId`：服务端请求 ID。

不得加入密钥、签名、完整请求体、节点日志或原始 API 响应。

## JSON 与 HTML 一致性

JSON 是唯一事实源。HTML 必须由版本为 `audit-result-template-1.0` 的固定模板生成；渲染后重新解析唯一数据槽，确认与交付 JSON 逐字段等值。HTML 不得新增、删减、改写或推断业务字段；若等值校验失败，不得交付部分 HTML。

智能审核结果供业务复核，不表述为最终医保资格决定。
