# 模式 2 Flash 契约

## 处理顺序

模式 2 采用两阶段非盲复核，且顺序固定：

1. 先只用患者材料和认定标准独立形成 `baseReview` 的 `materialFacts`、`ruleJudgments` 和 `preliminaryResult`，`method` 固定为 `two_stage_non_blind`；此阶段不得读取或引用任何 `audit_result`。
2. `baseReview` 三部分全部形成后，才能读取原审核，并对照其主张、证据、规则和结论形成 `auditComparison`。

这不是严格盲审。正式成果只能在用户明确确认材料清单完整后生成；用户未明确确认时，不得默认材料完整，不得生成正式 JSON 或 HTML；`materialsConfirmedComplete` 必须为 `true`。

## 根对象

根对象不得有额外字段，字段必须恰好为：

`schemaVersion`、`mode`、`meta`、`inputProfile`、`sourceDocuments`、`analysisRecord`、`baseReview`、`auditComparison`、`dimensions`、`issues`、`recommendations`、`confirmation`。

- `schemaVersion` 固定为 `flash-1.0`；`mode` 固定为 `qc`。
- `meta` 字段恰好为 `reportTitle`、`diseaseName`、`generatedAt`，均为非空字符串。
- `inputProfile` 字段恰好为 `standardKind`、`auditDetail`、`materialsConfirmedComplete`。`standardKind` 只能是 `structured`、`natural_language`、`absent`；`auditDetail` 只能是 `detailed`、`brief`、`conclusion_only`；正式成果中的完整性字段必须是布尔值 `true`。
- `sourceDocuments` 是非空数组。一份输入材料对应 `sourceDocuments` 中的一条记录，不得合并材料或以摘要替代，`content` 保存该份材料的完整原文。每项字段恰好为 `name`、`type`、`content`，均为非空字符串；文档名不得重复；`type` 只能是 `patient_material`、`standard`、`audit_result`。每份报告必须包含至少一项 `patient_material` 和至少一项 `audit_result`；`structured`、`natural_language` 必须至少有一项 `standard`，`absent` 不得有 `standard`。不得删节或改写 `content`。
- `analysisRecord` 字段恰好为 `inputSummary`、`interpretations`、`evidenceFindings`、`uncertainties`、`preliminaryConclusion`。前四项都是字符串数组，结论是非空字符串。
- `recommendations` 是字符串数组，允许为空数组；数组中的字符串不得为空。

所有下述对象同样不得出现额外字段。

## `baseReview`

字段恰好为 `method`、`materialFacts`、`ruleJudgments`、`preliminaryResult`。

- `method` 固定为 `two_stage_non_blind`。
- `materialFacts` 是字符串数组。
- `ruleJudgments` 是数组，每项字段恰好为 `ruleId`、`result`、`evidence`、`reason`。`ruleId` 和 `reason` 是非空字符串；`result` 只能是 `met`、`not_met`、`unknown`；`evidence` 是字符串数组。
- `preliminaryResult` 只能是 `meets`、`does_not_meet`、`uncertain`。
- 当 `standardKind` 不是 `absent` 时，不论 `auditDetail` 是何种取值，`materialFacts`、`ruleJudgments` 及每项判断的 `evidence` 都不得为空。
- `standardKind=structured` 时，`ruleJudgments[].ruleId` 必须直接复用结构化标准中的正式规则码，并覆盖标准逻辑树中的全部规则，不得重编号或遗漏。
- `standardKind=natural_language` 时，可以构建仅用于本次质控的临时规则；其 `ruleJudgments[].ruleId` 必须从 `TMP-R001` 开始连续且唯一，不得称为正式业务规则。

## `auditComparison`

字段恰好为 `originalConclusion`、`qcConclusion`、`risk`、`summary`。`originalConclusion` 与 `summary` 为非空字符串。

- `qcConclusion` 只能是 `reliable`、`problematic`、`uncertain`。
- `risk` 只能是 `none`、`false_approval`、`false_rejection`、`both`、`unknown`。
- `false_approval` 表示原审核通过，但独立复核结果为不满足，存在错误通过风险；`false_rejection` 表示原审核不通过，但独立复核结果为满足，存在错误拒绝风险；`both` 表示同时存在错误通过和错误拒绝风险；`unknown` 表示现有信息不足以确定风险方向。
- 仅当五个维度全部为 `passed` 且 `issues` 为空，才能使用 `reliable`；`reliable` 时 `risk` 必须为 `none`。
- 存在任何实际问题时，必须使用 `problematic`；`problematic` 时必须至少有一个 `issue` 维度和对应问题记录。`problematic` 时允许 `risk=none`，但仅限方向一致的局部问题；这类问题使用 `problematic`、`risk=none`，表示问题不改变通过/不通过方向。
- 只有仅有 `not_checked` 且不存在实际问题时，才使用 `uncertain`、`risk=unknown`；`uncertain` 时 `risk` 必须为 `unknown`。任何实际问题的 `problematic` 优先级高于 `not_checked` 带来的不确定性。

## 五个质控维度

`dimensions` 必须按以下顺序各出现一次：

1. 材料缺失判断准确性
2. 证据提取准确性
3. 过度推理
4. 审核条件与结论一致性
5. 规则维护质量

每项字段恰好为 `name`、`status`、`summary`、`notCheckedReason`。`status` 只能是 `passed`、`issue`、`not_checked`；`summary` 为非空字符串；`notCheckedReason` 是字符串，且仅当 `status` 为 `not_checked` 时必须非空，其他状态必须为空字符串。

## 问题、确认与降级

- `issues` 是数组。每项字段恰好为 `id`、`dimension`、`severity`、`auditClaim`、`actualEvidence`、`sourceReference`、`impact`、`recommendation`，全部为非空字符串。`id` 从 `I001` 开始连续编号；问题记录的维度集合必须与状态为 `issue` 的维度集合完全相等，非问题维度不得出现在问题记录中；`severity` 只能是 `high`、`medium`、`low`。
- 原审核引用的每个材料 ID 都必须在患者材料的名称或完整原文中定位。无法定位时，必须记录为“证据提取准确性”问题，`severity` 至少为 `medium`，并把该材料 ID 原样写入 `issue.sourceReference`。
- `confirmation` 字段恰好为 `confirmed`、`inventoryShown`、`userResponse`。`confirmed` 必须为布尔值 `true`；`confirmation.inventoryShown` 是非空字符串数组，必须与 `sourceDocuments[].name` 的顺序和内容完全一致；`userResponse` 是非空字符串。
- `standardKind=absent`：不得判断独立政策资格；不得包含 `standard` 来源，`ruleJudgments` 必须为空数组，`preliminaryResult` 必须为 `uncertain`，“规则维护质量”必须为 `not_checked` 并写明原因。
- `auditDetail=conclusion_only`：不得编造或推断未展示的审核主张、证据、推理和规则执行过程；前三个过程依赖维度（材料缺失判断准确性、证据提取准确性、过度推理）必须为 `not_checked` 并写明原因。对明确中文结论“通过”“不通过”，第四个“审核条件与结论一致性”维度按 `baseReview.preliminaryResult` 机械比较：方向相反时必须为 `issue`，使用 `qcConclusion=problematic` 及对应的 `false_approval` 或 `false_rejection`；方向一致时第四维为 `passed`。方向一致且规则维护质量为 `passed` 时，因为仅有 `not_checked` 且无实际问题，必须使用 `qcConclusion=uncertain`、`risk=unknown`，禁止使用 `reliable`；规则维护质量存在实际问题时必须为 `issue`，并使用 `qcConclusion=problematic`、`risk=none`。原审核结论方向不明确时第四维为 `not_checked`；规则维护质量无问题时使用 `qcConclusion=uncertain`、`risk=unknown`，规则维护质量存在明确局部问题时使用 `qcConclusion=problematic`、`risk=none`。规则维护质量不依赖 `auditDetail`：标准可见时必须检查为 `passed` 或 `issue`，标准缺失时为 `not_checked`；方向相反时，规则维护问题不得覆盖方向性风险。`standardKind=absent` 且 `auditDetail=conclusion_only` 时，不存在可独立得出的方向，第四维和规则维护质量均为 `not_checked`，总体必须为 `uncertain`、`unknown`。
- `auditDetail=brief`：只核查可见主张，无法获取的检查项标为 `not_checked` 并写明原因，不得编造缺失过程。
- `standardKind=natural_language`：出现任何影响结论的歧义时，`analysisRecord.uncertainties` 必须非空；只有不存在实际问题时，`qcConclusion` 才使用 `uncertain`，`risk` 使用 `unknown`，存在实际问题仍按总体结论优先级使用 `problematic`。

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
    },
    {
      "id": "I002",
      "dimension": "审核条件与结论一致性",
      "severity": "high",
      "auditClaim": "原审核以证据 A 缺失为由给出不通过结论",
      "actualEvidence": "患者材料中的证据 A 满足认定标准要求",
      "sourceReference": "患者材料：测试段落；认定标准：测试条款",
      "impact": "可能导致审核条件判断与最终结论不一致并造成错误拒绝",
      "recommendation": "根据证据 A 已满足的事实重新判定审核条件并修正结论"
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
