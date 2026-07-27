# 材料证据编目与归位 Flash 契约

## 输出边界

成果只描述来源材料中可定位的客观信息、时间归位、材料关系与待核对项。不得包含规则判断、资格结论、审核结论、风险、问题或建议字段，也不得使用“通过”“不通过”“缺少材料”“规则不符”等审核语义。

## 根对象

根对象必须且只能包含：

`schemaVersion`、`mode`、`meta`、`sourceDocuments`、`analysisRecord`、`catalog`、`timelines`、`relationships`、`confirmation`。

- `schemaVersion` 固定为 `flash-1.0`。
- `mode` 固定为 `material_catalog`。
- `meta` 必须且只能包含 `reportTitle`、`subjectName`、`generatedAt`，均为字符串。`reportTitle` 与 `generatedAt` 非空；没有用户提供的主体名称时，`subjectName` 使用空字符串，不能猜测。

## 来源材料

`sourceDocuments` 是非空数组，每项必须且只能包含 `name`、`type`、`content`，均为非空字符串。

- `type` 固定为 `patient_material`。
- 每份输入材料必须各自对应一项来源记录，文档名不得重复。
- `content` 保存该份材料完整的用户提供文本；不得合并、摘要、截断或改写。

## 分析记录

`analysisRecord` 必须且只能包含 `inputSummary`、`catalogingBasis`、`evidenceFindings`、`uncertainties`、`preliminaryConclusion`。

- 前四项均为字符串数组，`inputSummary`、`catalogingBasis`、`evidenceFindings` 非空；`uncertainties` 可以为空。
- `preliminaryConclusion` 是非空字符串，必须明确说明成果不构成资格、材料充分性或审核结论。

## 材料目录

`catalog` 必须是非空数组，长度、顺序和 `catalog[].sourceName` 必须分别与 `sourceDocuments` 的长度、顺序和名称完全一致。每项必须且只能包含：

`sourceName`、`documentType`、`readability`、`issuer`、`dateRange`、`facts`、`pendingChecks`。

- `documentType` 只能是 `病历`、`检查报告`、`处方`、`其他` 或 `未识别`。
- `readability` 只能是 `可编目`、`部分可编目` 或 `无法编目`。
- `issuer` 是原文明确的机构名称，未明确时固定写 `未识别`。
- `dateRange` 必须且只能包含 `start`、`end`、`display`，均为字符串；`start`、`end` 只允许 `YYYY-MM-DD` 或空字符串；`display` 记录原文日期表达或 `日期待核对`。
- `facts` 是数组；每项必须且只能包含 `text`、`category`、`sourceReference`，均为非空字符串；`category` 只能是 `诊断`、`检查`、`治疗`、`用药`、`住院` 或 `其他`。`sourceReference` 必须可回指同一份来源材料，不能伪造页码、段落号或材料标识。
- `pendingChecks` 是字符串数组。`facts` 为空时，`pendingChecks` 必须非空说明原因；`readability=无法编目` 时，`facts` 必须为空。

## 时间线

`timelines` 是数组，每项必须且只能包含 `sourceName`、`date`、`display`、`sortStatus`，均为字符串。

- `sourceName` 必须引用一个已存在的材料目录项，且每份材料恰好出现一次。
- `sortStatus` 只能是 `已确认` 或 `待核对`。
- `sortStatus=已确认` 时，`date` 必须是 `YYYY-MM-DD`，并等于对应目录项的 `dateRange.start`；这些项目按 `date` 升序排列。
- `sortStatus=待核对` 时，`date` 必须为空字符串，`display` 说明原文日期表达或日期待核对；这些项目排在全部已确认项目之后。

## 材料关系

`relationships` 是数组，每项必须且只能包含 `sourceNames`、`type`、`basis`、`status`。

- `sourceNames` 是包含两个或以上不同材料名称的数组，所有名称均存在于 `sourceDocuments`。
- `type` 只能是 `同次就诊`、`同一检查`、`疑似重复` 或 `关联线索`。
- `basis` 是非空字符串，必须说明可回指至少一份相关来源材料的原文依据。
- `status` 只能是 `已明确` 或 `待核对`。
- 疑似重复只能使用待核对，且不得删除、合并或忽略任何来源材料。

## 确认记录

`confirmation` 必须且只能包含 `confirmed`、`inventoryShown`、`userResponse`。

- `confirmed` 必须为布尔值 `true`。
- `inventoryShown` 是非空字符串数组，必须与 `sourceDocuments[].name` 的顺序和内容完全一致。
- `userResponse` 是用户明确确认材料完整的非空原话。

交付文件名固定为 `<主体或材料>-材料证据编目-flash-<日期>.json` 与 `<主体或材料>-材料证据编目-flash-<日期>.html`。
