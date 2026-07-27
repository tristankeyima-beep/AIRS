# 材料证据编目与归位 Flash Skill 设计

## 1. 目标与边界

新增独立 Skill `chronic-disease-material-catalog-flash`。它把用户提供的患者申请材料、OCR 文本或转写内容整理成可追溯的材料目录和证据归位报告，并交付 JSON 与离线 HTML。

本 Skill 只做客观编目：不读取认定标准、不生成规则判断、不判定材料是否充分、不输出通过或不通过结论，也不评价原审核结果。

## 2. 输入与确认门禁

输入至少包含一份患者材料。每份输入材料独立保留原始文件名和完整原文；图片、PDF 等非文本材料使用用户提供的 OCR 或转写内容作为可编目文本，不补造无法识别的内容。

执行顺序：

1. 清点每份材料的名称与可用内容类型，生成材料清单。
2. 向用户展示材料清单并询问是否有遗漏；用户补充后重新展示。
3. 仅在用户明确确认材料完整后，进行编目、事实摘录和归位。
4. 生成并校验正式 JSON 与 HTML。

确认门禁复用审核质控 Flash 的材料完整性原则，但不读取或要求认定标准、原审核结果。

## 3. 数据模型

根对象使用 `flash-1.0`，模式为 `material_catalog`。业务数据只在 JSON 中定义，HTML 只渲染该 JSON。

```json
{
  "schemaVersion": "flash-1.0",
  "mode": "material_catalog",
  "meta": {
    "reportTitle": "材料证据编目与归位报告",
    "subjectName": "",
    "generatedAt": ""
  },
  "sourceDocuments": [],
  "analysisRecord": {
    "inputSummary": [],
    "catalogingBasis": [],
    "evidenceFindings": [],
    "uncertainties": [],
    "preliminaryConclusion": ""
  },
  "catalog": [],
  "timelines": [],
  "relationships": [],
  "confirmation": {
    "confirmed": true,
    "inventoryShown": [],
    "userResponse": ""
  }
}
```

`sourceDocuments` 的每一项包含 `name`、`type`、`content`，其中 `type` 固定为 `patient_material`。它保留完整输入原文，不合并、不摘要、不改写。

`catalog` 按 `sourceDocuments` 顺序为每份材料生成一项，且 `sourceName` 必须唯一对应一个来源材料：

```json
{
  "sourceName": "材料名称",
  "documentType": "病历/检查报告/处方/其他/未识别",
  "readability": "可编目/部分可编目/无法编目",
  "issuer": "原文明确的机构名称或未识别",
  "dateRange": {
    "start": "YYYY-MM-DD 或空字符串",
    "end": "YYYY-MM-DD 或空字符串",
    "display": "原文日期表述或日期待核对"
  },
  "facts": [
    {
      "text": "仅摘录原文明确事实",
      "category": "诊断/检查/治疗/用药/住院/其他",
      "sourceReference": "可定位的页码、段落、行号或原文片段"
    }
  ],
  "pendingChecks": ["待核对事项"]
}
```

未能从原文确定的字段应使用明确的“未识别”或“待核对”状态，不得猜测。`facts` 允许为空数组，但此时必须在 `pendingChecks` 说明原因；`readability=无法编目` 时不得虚构事实摘录。

`timelines` 包含 `sourceName`、`date`、`display` 和 `sortStatus`。只有原文明确到日的日期才可以进入 `sortStatus=confirmed` 的时间线；只有年月、相对时间或无日期的材料使用 `sortStatus=pending` 单列，不强行置入时间线。

`relationships` 的每项包含 `sourceNames`、`type`、`basis` 和 `status`。`type` 只能是 `同次就诊`、`同一检查`、`疑似重复` 或 `关联线索`；`basis` 必须可回指至少一份相关材料的原文；`status` 只能是 `已明确` 或 `待核对`。任何“疑似重复”只能为 `待核对`，绝不删除或合并材料。

`analysisRecord.preliminaryConclusion` 固定说明本报告是客观编目，不构成资格、材料充分性或审核结论。

## 4. 编目规则

- 只摘录材料原文明确出现的事实，例如文件类型、日期、机构、诊断名称、检查项目、治疗/用药记录和住院记录。
- 每个摘录必须能回指单一材料的原文位置；无法精确定位时标为“原文存在但位置待核对”，不能伪造页码或段落号。
- “未识别到某信息”只说明当前材料文本未定位，不代表事实不存在。
- 不依据医学常识补齐诊断、机构、日期、患者关系或材料用途。
- 不依据标准评价材料是否足以证明任何资格条件。

## 5. HTML 报告

复制现有 Flash 的离线、单文件和 `flash-data` 注入模式，但新建专用模板，不修改现有认定标准或审核质控模板。

页面包含：

1. 报告概览与编目边界说明。
2. 已确认材料清单与可读状态。
3. 按材料类型归档的目录。
4. 按可确认日期排列的时间线，以及日期待核对材料。
5. 材料事实与原文定位。
6. 材料关联/疑似重复线索。
7. 待核对项、分析记录、完整原始材料和确认记录。

页面不得展示英文状态码，不得出现“通过”“不通过”“缺少材料”“规则不符”等审核语义。

## 6. 复用与隔离

直接复用：不受信任输入处理、逐份原文留存、材料清单确认、`analysisRecord`、离线 HTML 数据槽注入与等值校验、敏感信息与外部发送防护。

仅作参考：审核质控 Flash 的材料事实和原文定位表现方式。

不复用：审核质控的 `baseReview`、规则判断、原审核对照、五维质控、风险和问题模型；认定标准 Flash 的规则、逻辑树、提取项与标准确认模型。

## 7. 验收与测试

至少覆盖：单份材料、多份有日期材料、日期缺失材料、机构缺失材料、OCR 不可读、疑似重复但不得合并、关系缺少依据、用户未确认清单、确认后 JSON/HTML 等值、敏感信息拦截。

验收时验证：每份输入对应一条来源记录；所有事实可回溯；无规则或资格结论；HTML 内嵌数据可解析并与交付 JSON 逐字段等值；模板 CSS 与 JavaScript 在生成时未被修改。
