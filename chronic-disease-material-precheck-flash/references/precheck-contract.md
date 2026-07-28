# 申请材料预检与补件清单 Flash 契约

## 业务边界

成果只描述已确认标准下的条件—证据预检和可追溯补充项。不得包含原审核结果、风险或正式资格结论，也不得使用通过、不通过、错误通过、错误拒绝或审核质控问题语义。

## 根对象

根对象必须且只能包含：`schemaVersion`、`mode`、`meta`、`standardProfile`、`sourceDocuments`、`analysisRecord`、`precheckItems`、`supplementList`、`confirmation`。

- `schemaVersion` 固定为 `flash-1.0`，`mode` 固定为 `material_precheck`。
- `meta` 必须且只能包含 `reportTitle`、`diseaseName`、`generatedAt`，均为非空字符串。

## 采用标准与来源材料

`standardProfile` 必须且只能包含 `name`、`sourceName`、`version`、`adoptionMethod`、`ruleSummary`、`logicSummary`，均为非空字符串。`adoptionMethod` 只能是 `确认的自然语言标准`、`确认的知识库标准` 或 `已确认的结构化标准`。

`sourceDocuments` 是非空数组，每项必须且只能包含 `name`、`type`、`content`，均为非空字符串；`type` 只能是 `standard` 或 `patient_material`。至少有一项 `standard` 和一项 `patient_material`，每份输入各自保存完整原文，文档名不得重复。

## 分析记录

`analysisRecord` 必须且只能包含 `inputSummary`、`interpretations`、`evidenceFindings`、`uncertainties`、`preliminaryConclusion`。前四项为字符串数组；前三项非空，`uncertainties` 可为空。`preliminaryConclusion` 非空且必须说明不构成正式资格审核结论。

## 预检项与补充清单

`precheckItems` 是非空数组，每项必须且只能包含 `id`、`ruleId`、`extractionItemId`、`condition`、`status`、`evidence`、`sourceReferences`、`detail`、`preferredSource`。

- `id` 从 `P001` 开始连续唯一；`ruleId` 与 `extractionItemId` 均非空，分别对应本次采用标准中的规则和提取项。
- `status` 只能是 `已定位证据`、`信息不足`、`未定位证据`、`材料形式待确认`。
- `evidence` 和 `sourceReferences` 都是字符串数组；已定位证据时两者均非空，其他状态允许为空数组。
- `detail` 与 `preferredSource` 均为非空字符串；未定位证据不得写成患者未提交材料的事实。

`supplementList` 是数组，每项必须且只能包含 `id`、`precheckItemId`、`status`、`priority`、`title`、`reason`、`action`、`sourceReference`。

- 只能收录信息不足、未定位证据或材料形式待确认，且每项 `precheckItemId` 唯一引用对应状态的预检项。
- `priority` 只能是 `高`、`中`、`低`，其他字段均为非空字符串。
- 材料形式待确认的 `action` 只能要求人工确认可接受的证据或材料形式，不能凭空指定诊断证明、检查单或其他特定文件。

## 确认记录

`confirmation` 必须且只能包含 `standardConfirmed`、`standardSummaryShown`、`standardUserResponse`、`materialsConfirmedComplete`、`inventoryShown`、`materialsUserResponse`。

- `standardConfirmed` 和 `materialsConfirmedComplete` 均为 `true`。
- 两份用户回复和标准摘要均为非空字符串。
- `inventoryShown` 为非空字符串数组，必须与全部患者材料名称的顺序和内容完全一致。

文件名固定为 `<病种>-材料预检-flash-<日期>.json` 与 `<病种>-材料预检-flash-<日期>.html`。
