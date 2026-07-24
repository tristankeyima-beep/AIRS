# 质控报告规范对象

文本报告和 HTML 报告必须由同一个规范对象渲染；在 `inputScope.confirmedByUser` 为 `true` 前，不得输出任何正式文本或 HTML。

根对象必须且只能包含：`case`、`inputScope`、`capabilities`、`originalResult`、`qcConclusion`、`riskDirection`、`recommendedAction`、`issues`、`ruleReviews`、`unperformedChecks`、`rawInput`。

- `case` 必须含非空字符串 `patientName`、`diseaseName`、`auditId`。
- `inputScope` 必须含布尔值 `confirmedByUser`、字符串数组 `materials`、非空字符串 `standardKind`、`auditResultKind`；正式输出时确认值必须为真。
- `capabilities` 是对象数组；每项必须含 `name`、`status`、`reason`，其中状态为 `completed`、`partial` 或 `not_run`。`completed` 的 `reason` 可为空字符串，`partial` 和 `not_run` 必须有非空原因。
- `originalResult` 为非空字符串；`qcConclusion` 采用量规中的结论枚举，根级 `riskDirection` 采用量规中的风险枚举，`recommendedAction` 为非空字符串。
- `issues` 的每项必须含 `category`、`issueType`、`severity`、`ruleCode`、`keywordCode`、`modelClaim`、`evidenceStatus`、`materialEvidence`、`qcFinding`、`possibleImpact`、`impactOnFinalResult`、`riskDirection`、`recommendation`、`confidence`。严重度和置信度为 `high`、`medium`、`low`；最终结论影响为 `changed`、`potentially_changed`、`unchanged`、`unknown`；问题风险代码为 `false_approval`、`false_rejection`、`both`、`none`；证据状态采用量规枚举。
- 每条 `materialEvidence` 必须含 `materialId`、`materialName`、`page`、`section`、`rawText`、`normalizedText`、`location`。`page` 为正整数，`normalizedText` 可为空字符串；`location` 是含非负整数 `start`、`end` 的对象，且 `start <= end`。
- `ruleReviews` 每项必须含 `ruleCode`、`result`、`modelClaim`、`evidenceStatus`、`materialEvidence`、`qcFinding`、`recommendation`，结果和证据状态采用量规枚举。
- `unperformedChecks` 每项必须含 `name`、`reason`；若提供 `status`，其值只能为 `not_run`。
- `rawInput` 可为任意 JSON 值，但不能含循环、重复键、元组等非 JSON 容器、非 JSON 值、超深结构或非字符串对象键。JSON 字符串和文件输入也会拒绝每层的重复键。

文本部分按如下顺序：质控结论、输入与检查范围、影响最终结论的问题、材料缺失复核、证据准确性、过度推理、条件一致性、规则维护质量、逐规则复核、建议、未执行检查、原始输入。每一空集合均须显示明确空状态。
