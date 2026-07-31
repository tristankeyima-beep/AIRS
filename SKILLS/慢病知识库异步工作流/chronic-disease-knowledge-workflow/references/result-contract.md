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

`ruleResults` 必须是对象数组。每条规则原样保留工作流返回的 `ruleCode`、`ruleContent`、`ruleResult`、`reasoningContent`、`ruleKeywordGuide` 与 `suspicionList`；只做必要的字符串化数组解包和类型规范化，不改变规则结论、证据或建议。

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
