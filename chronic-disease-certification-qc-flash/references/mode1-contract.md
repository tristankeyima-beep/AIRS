# 模式 1 Flash 契约

仅使用来源原文生成认定标准。阻断性歧义未解决时，不得生成正式 JSON 或 HTML；`analysisRecord.uncertainties` 只能记录不影响定稿的非阻断性不确定项。

## 输出约束

- 根对象必须且只能包含 `schemaVersion`、`mode`、`meta`、`sourceDocuments`、`analysisRecord`、`rules`、`logic`、`confirmation`。
- `schemaVersion` 固定为 `flash-1.0`，`mode` 固定为 `certification`。
- `meta` 必须且只能包含 `diseaseName`、`diseaseCode`、`version`、`description`，四项均为字符串；`diseaseName`、`version`、`description` 不得为空，`diseaseCode` 可以为空字符串。
- `sourceDocuments` 必须是非空数组。每个对象必须且只能包含 `name`、`type`、`content`，三项均为字符串；`type` 固定为 `standard`，`name` 和保存完整来源原文的 `content` 不得为空，禁止只存摘要或截断内容。
- `analysisRecord` 必须且只能包含 `inputSummary`、`interpretations`、`evidenceFindings`、`uncertainties`、`preliminaryConclusion`。前四项必须是字符串数组；前三个数组必须非空且所有成员不得为空，`uncertainties` 可以是空数组，但存在成员时成员不得为空。`preliminaryConclusion` 必须是非空字符串。
- `rules` 必须是非空数组。每条规则必须且只能包含 `id`、`content`、`sourceQuote`、`extractionItems`；`id`、`content`、`sourceQuote` 均为非空字符串，`extractionItems` 是非空数组。规则 `id` 从 `R001` 开始按数组顺序连续且唯一。
- 每条规则的 `sourceQuote` 必须是至少一项 `sourceDocuments[].content` 中真实存在的逐字子串。
- 每个提取项必须且只能包含 `id`、`name`、`dataType`、`expectedEvidence`、`negativeEvidence`、`unknownWhen`、`preferredSource`，各项均为字符串且不得为空；`dataType` 只能是 `enum` 或 `text`。提取项 `id` 在全部规则中从 `K001` 开始连续且唯一。
- `logic` 只允许嵌套 `group` 和 `rule` 节点。`group.operator` 只能是 `AND` 或 `OR`，且 `children` 非空；`rule.ruleId` 引用已声明规则。每条规则必须且只能被引用一次。
- `confirmation` 必须且只能包含 `confirmed`、`summaryShown`、`userResponse`；`confirmed` 必须是布尔值，并且只有取得用户确认后才能设为 `true` 和生成正式成果；另外两项必须是非空字符串。
- 文件名固定为 `<病种>-认定标准-flash-<版本>.json` 和 `<病种>-认定标准-flash-<版本>.html`。

## 规范 JSON 示例

以下结构与字段名必须原样遵守；内容替换为当前病种和来源：

```json
{
  "schemaVersion": "flash-1.0",
  "mode": "certification",
  "meta": {
    "diseaseName": "测试病种甲",
    "diseaseCode": "",
    "version": "V20260725",
    "description": "仅用于 Flash Skill 验收"
  },
  "sourceDocuments": [
    {
      "name": "测试认定标准",
      "type": "standard",
      "content": "满足条件 A 或条件 B，可认定为测试病种甲。"
    }
  ],
  "analysisRecord": {
    "inputSummary": [
      "来源包含一个 OR 准入关系"
    ],
    "interpretations": [
      "将条件 A 与条件 B 作为两个独立规则"
    ],
    "evidenceFindings": [
      "原文明确使用“或”"
    ],
    "uncertainties": [],
    "preliminaryConclusion": "采用 R001 OR R002"
  },
  "rules": [
    {
      "id": "R001",
      "content": "满足条件 A",
      "sourceQuote": "满足条件 A 或条件 B",
      "extractionItems": [
        {
          "id": "K001",
          "name": "条件 A",
          "dataType": "enum",
          "expectedEvidence": "测试材料明确记载条件 A 已满足",
          "negativeEvidence": "测试材料明确记载条件 A 未满足",
          "unknownWhen": "测试材料未提供足以判断条件 A 的信息",
          "preferredSource": "测试认定材料"
        }
      ]
    },
    {
      "id": "R002",
      "content": "满足条件 B",
      "sourceQuote": "满足条件 A 或条件 B",
      "extractionItems": [
        {
          "id": "K002",
          "name": "条件 B",
          "dataType": "enum",
          "expectedEvidence": "测试材料明确记载条件 B 已满足",
          "negativeEvidence": "测试材料明确记载条件 B 未满足",
          "unknownWhen": "测试材料未提供足以判断条件 B 的信息",
          "preferredSource": "测试认定材料"
        }
      ]
    }
  ],
  "logic": {
    "type": "group",
    "operator": "OR",
    "children": [
      {
        "type": "rule",
        "ruleId": "R001"
      },
      {
        "type": "rule",
        "ruleId": "R002"
      }
    ]
  },
  "confirmation": {
    "confirmed": true,
    "summaryShown": "R001 或 R002 任一满足即可认定",
    "userResponse": "确认"
  }
}
```
