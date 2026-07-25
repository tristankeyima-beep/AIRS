# 模式 2 Flash 契约

## 处理顺序

模式 2 采用两阶段非盲复核，且顺序固定：

1. 先用患者材料和认定标准独立形成 `baseReview`，`method` 固定为 `two_stage_non_blind`。
2. 再读取并对照原审核主张、证据、规则和结论，形成 `auditComparison`。

这不是严格盲审。正式成果只能在用户确认材料清单完整后生成；`materialsConfirmedComplete` 必须为 `true`。

## 根对象

根对象不得有额外字段，字段必须恰好为：

`schemaVersion`、`mode`、`meta`、`inputProfile`、`sourceDocuments`、`analysisRecord`、`baseReview`、`auditComparison`、`dimensions`、`issues`、`recommendations`、`confirmation`。

- `schemaVersion` 固定为 `flash-1.0`；`mode` 固定为 `qc`。
- `meta` 字段恰好为 `reportTitle`、`diseaseName`、`generatedAt`，均为非空字符串。
- `inputProfile` 字段恰好为 `standardKind`、`auditDetail`、`materialsConfirmedComplete`。`standardKind` 只能是 `structured`、`natural_language`、`absent`；`auditDetail` 只能是 `detailed`、`brief`、`conclusion_only`；正式成果中的完整性字段必须是布尔值 `true`。
- `sourceDocuments` 是非空数组。每项字段恰好为 `name`、`type`、`content`，均为非空字符串；`type` 只能是 `patient_material`、`standard`、`audit_result`。`content` 必须保存收到的完整原文，不得摘要替代、删节或改写。
- `analysisRecord` 字段恰好为 `inputSummary`、`interpretations`、`evidenceFindings`、`uncertainties`、`preliminaryConclusion`。前四项都是字符串数组，结论是非空字符串。
- `recommendations` 是字符串数组，允许为空数组；数组中的字符串不得为空。

所有下述对象同样不得出现额外字段。

## `baseReview`

字段恰好为 `method`、`materialFacts`、`ruleJudgments`、`preliminaryResult`。

- `method` 固定为 `two_stage_non_blind`。
- `materialFacts` 是字符串数组。
- `ruleJudgments` 是数组，每项字段恰好为 `ruleId`、`result`、`evidence`、`reason`。`ruleId` 和 `reason` 是非空字符串；`result` 只能是 `met`、`not_met`、`unknown`；`evidence` 是字符串数组。
- `preliminaryResult` 只能是 `meets`、`does_not_meet`、`uncertain`。

## `auditComparison`

字段恰好为 `originalConclusion`、`qcConclusion`、`risk`、`summary`。`originalConclusion` 与 `summary` 为非空字符串。

- `qcConclusion` 只能是 `reliable`、`problematic`、`uncertain`。
- `risk` 只能是 `none`、`false_approval`、`false_rejection`、`both`、`unknown`。

## 五个质控维度

`dimensions` 必须按以下顺序各出现一次：

1. 材料缺失判断准确性
2. 证据提取准确性
3. 过度推理
4. 审核条件与结论一致性
5. 规则维护质量

每项字段恰好为 `name`、`status`、`summary`、`notCheckedReason`。`status` 只能是 `passed`、`issue`、`not_checked`；`summary` 为非空字符串；`notCheckedReason` 是字符串，且仅当 `status` 为 `not_checked` 时必须非空，其他状态必须为空字符串。

## 问题、确认与降级

- `issues` 是数组。每项字段恰好为 `id`、`dimension`、`severity`、`auditClaim`、`actualEvidence`、`sourceReference`、`impact`、`recommendation`，全部为非空字符串。`id` 从 `I001` 开始连续编号；`dimension` 必须是上述五个维度之一且对应维度状态为 `issue`；`severity` 只能是 `high`、`medium`、`low`。
- `confirmation` 字段恰好为 `confirmed`、`inventoryShown`、`userResponse`。`confirmed` 必须为布尔值 `true`；`inventoryShown` 是非空字符串数组；`userResponse` 是非空字符串。
- `standardKind=absent`：不得判断独立政策资格；`ruleJudgments` 必须为空数组，`preliminaryResult` 必须为 `uncertain`，“规则维护质量”必须为 `not_checked` 并写明原因。
- `auditDetail=conclusion_only`：不得编造审核证据或规则执行过程；“证据提取准确性”和“审核条件与结论一致性”必须为 `not_checked` 并写明原因。
- `auditDetail=brief`：只核查可见主张，无法获取的检查项标为 `not_checked` 并写明原因，不得编造缺失过程。
- `standardKind=natural_language`：可以构建仅用于本次质控的临时规则，编号从 `TMP-R001` 开始连续排列，但不得把它们称为正式业务规则。任何影响结论的含义歧义必须写入 `analysisRecord.uncertainties`，并令 `qcConclusion` 为 `uncertain`。

交付文件名固定为 `<病种>-审核质控-flash-<日期>.json` 和 `<病种>-审核质控-flash-<日期>.html`。

## 完整示例

```json
{
  "schemaVersion": "flash-1.0",
  "mode": "qc",
  "meta": {
    "reportTitle": "测试审核质控报告",
    "diseaseName": "测试病种甲",
    "generatedAt": "2026-07-25"
  },
  "inputProfile": {
    "standardKind": "structured",
    "auditDetail": "detailed",
    "materialsConfirmedComplete": true
  },
  "sourceDocuments": [
    {
      "name": "患者材料",
      "type": "patient_material",
      "content": "患者材料明确记载证据 A。"
    },
    {
      "name": "认定标准",
      "type": "standard",
      "content": "认定标准要求满足证据 A。"
    },
    {
      "name": "原审核结果",
      "type": "audit_result",
      "content": "原审核认定证据 A 缺失，结论为不通过。"
    }
  ],
  "analysisRecord": {
    "inputSummary": [
      "已收到患者材料、结构化标准和详细审核结果"
    ],
    "interpretations": [
      "按标准中的证据 A 要求进行复核"
    ],
    "evidenceFindings": [
      "患者材料明确存在证据 A"
    ],
    "uncertainties": [],
    "preliminaryConclusion": "原审核的缺失判断与材料不一致"
  },
  "baseReview": {
    "method": "two_stage_non_blind",
    "materialFacts": [
      "患者材料明确记载证据 A"
    ],
    "ruleJudgments": [
      {
        "ruleId": "R001",
        "result": "met",
        "evidence": [
          "患者材料：证据 A"
        ],
        "reason": "材料中的证据 A 满足标准要求"
      }
    ],
    "preliminaryResult": "meets"
  },
  "auditComparison": {
    "originalConclusion": "不通过",
    "qcConclusion": "problematic",
    "risk": "false_rejection",
    "summary": "原审核错误地将已提供证据判断为缺失，可能导致错误拒绝"
  },
  "dimensions": [
    {
      "name": "材料缺失判断准确性",
      "status": "issue",
      "summary": "原审核将材料中已存在的证据 A 判断为缺失",
      "notCheckedReason": ""
    },
    {
      "name": "证据提取准确性",
      "status": "passed",
      "summary": "复核能够从患者材料中准确定位证据 A",
      "notCheckedReason": ""
    },
    {
      "name": "过度推理",
      "status": "passed",
      "summary": "未发现原审核使用材料之外的信息进行推理",
      "notCheckedReason": ""
    },
    {
      "name": "审核条件与结论一致性",
      "status": "issue",
      "summary": "证据 A 已满足标准要求，但原审核仍给出不通过结论",
      "notCheckedReason": ""
    },
    {
      "name": "规则维护质量",
      "status": "passed",
      "summary": "本次复核未发现认定标准本身存在维护问题",
      "notCheckedReason": ""
    }
  ],
  "issues": [
    {
      "id": "I001",
      "dimension": "材料缺失判断准确性",
      "severity": "high",
      "auditClaim": "原审核主张证据 A 缺失",
      "actualEvidence": "患者材料明确记载证据 A",
      "sourceReference": "患者材料：测试段落",
      "impact": "可能导致符合条件的申请被错误拒绝",
      "recommendation": "重新提取证据 A 并复核审核结论"
    }
  ],
  "recommendations": [
    "重新提取患者材料中的证据 A",
    "复核最终审核结论"
  ],
  "confirmation": {
    "confirmed": true,
    "inventoryShown": [
      "患者材料",
      "认定标准",
      "原审核结果"
    ],
    "userResponse": "确认材料完整"
  }
}
```
