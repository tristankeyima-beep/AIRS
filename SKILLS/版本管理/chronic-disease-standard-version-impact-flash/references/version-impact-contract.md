# 认定标准版本比对与影响分析 Flash 契约

## 根对象

根对象必须且只能包含：`schemaVersion`、`mode`、`meta`、`standardInputs`、`analysisRecord`、`conditionGroups`、`changes`、`materialDocuments`、`versionAssessments`、`assessmentDelta`、`confirmation`。

- `schemaVersion` 固定为 `flash-1.0`，`mode` 固定为 `standard_version_impact`。
- `meta` 必须且只能包含 `reportTitle`、`diseaseName`、`comparisonOrder`、`orderBasis`、`generatedAt`，均为非空字符串。
- 排序依据 `orderBasis` 只能是 `来源原文明确`、`用户指定` 或 `无法确认`；无法确认时 `comparisonOrder` 必须为 `多版本差异，不区分新旧`。

## 标准输入与可比条件

`standardInputs` 是长度至少为 2 的数组，每项必须且只能包含 `standardKey`、`name`、`documentVersion`、`effectiveInfo`、`sourceName`、`content`、`ruleNamespace`。

- `standardKey` 连续使用 `S1`、`S2`、`S3`；`ruleNamespace` 等于对应 `standardKey`。
- 所有字段为非空字符串；`effectiveInfo` 不明确时固定写 `原文未明确`。
- `documentVersion` 仅记录文件明确版本标识；不得把成果生成日期单独当作政策生效日期。

`conditionGroups` 是非空数组，每项必须且只能包含 `id`、`title`、`members`、`matchingStatus`。`members` 是非空数组，每项包含 `standardKey`、`scopedRuleId`、`sourceReference`；`scopedRuleId` 使用 `S1:R001` 形式。`matchingStatus` 只能是 `可比` 或 `待人工确认`。

## 差异与可选材料判读

`changes` 是数组，每项必须且只能包含 `id`、`conditionGroupId`、`type`、`summary`、`affectedRules`、`sourceReferences`、`manualReviewRequired`。

- `type` 只能是 `条件新增`、`条件删除`、`条件修改`、`逻辑变化` 或 `仅表述变化`。
- `affectedRules` 与 `sourceReferences` 均为非空字符串数组；规则标识必须带版本命名空间。
- `manualReviewRequired` 是布尔值；`仅表述变化` 必须为 `true`。

`materialDocuments` 是数组，每项必须且只能包含 `name`、`type`、`content`；`type` 固定为 `patient_material`。未提供材料时它必须为空数组。

`versionAssessments` 是数组。每项必须且只能包含 `standardKey`、`materialFacts`、`ruleJudgments`、`referenceResult`。`ruleJudgments` 每项必须且只能包含 `ruleId`、`result`、`evidence`、`reason`；`ruleId` 使用 `S1:R001` 形式，`result` 只能是 `met`、`not_met` 或 `unknown`。`referenceResult` 只能是 `meets`、`does_not_meet` 或 `uncertain`。无材料时数组必须为空。

`assessmentDelta` 是数组，每项必须且只能包含 `id`、`fromStandardKey`、`toStandardKey`、`changedRules`、`differenceType`、`summary`、`sourceReferences`。它只记录跨版本材料判读变化；无材料或无变化时为空数组。

## 分析与确认

`analysisRecord` 必须且只能包含 `inputSummary`、`interpretations`、`evidenceFindings`、`uncertainties`、`preliminaryConclusion`；前四项为字符串数组，结论非空且说明不构成最终资格结论。

`confirmation` 必须且只能包含 `standardsConfirmed`、`standardsSummaryShown`、`standardsUserResponse`、`materialsConfirmedComplete`、`inventoryShown`、`materialsUserResponse`。

- `standardsConfirmed` 必须为 `true`；前三项非空。
- 没有材料时 `materialsConfirmedComplete=false`、`inventoryShown=[]`、`materialsUserResponse="未提供申请材料"`。
- 有材料时 `materialsConfirmedComplete=true`，清单与 `materialDocuments` 完全一致且用户回复非空。

不得包含原审核结果、风险、质控问题、五维检查或正式资格结论字段。
