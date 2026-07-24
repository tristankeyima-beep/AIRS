# 质控报告规范对象

文本报告和 HTML 报告必须由同一个规范对象渲染；先以 `inspect_standard.py` 的权威结果确定 `standardKind`，再构造、展示和摘要 inventory。在完成已收输入清点、无条件询问“是否遗漏任何内容？”并得到用户明确确认完整前，`inputScope.confirmedByUser` 必须为 `false`，不得输出任何正式文本或 HTML。用户补充后先重新分类、再重新清点和再次确认；分类或输入变化必须递增 revision 并使旧确认失效。原审核已说“没有漏传”、输入很急或结论已经可见均不替代用户确认。

根对象必须且只能包含：`case`、`inputScope`、`capabilities`、`originalResult`、`qcConclusion`、`riskDirection`、`recommendedAction`、`issues`、`ruleReviews`、`unperformedChecks`、`rawInput`。

- `case` 必须含非空字符串 `patientName`、`diseaseName`、`auditId`。
- `inputScope` 必须含布尔值 `confirmedByUser`、字符串数组 `materials`、`standardKind`、`auditResultKind`、`inventory`、`confirmation`、`independentReview`；正式输出时确认值必须为真。`standardKind` 严格为 `structured_complete`、`structured_incomplete`、`natural_language`、`absent`，`auditResultKind` 严格为 `detailed`、`brief`、`conclusion_only`。
- `inventory` 必须且只能含正整数 `revision`、`materials`、与 `inputScope` 相同的权威 `standardKind`/`auditResultKind`、布尔 `hasAuditProcess`、恒为 true 的 `hasFinalConclusion`、字符串数组 `referencedButMissing` 和 64 位小写十六进制 `rawInputSha256`；后者严格为 `sha256(json.dumps(rawInput, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False))`，`inventory.materials` 必须与 `inputScope.materials` 完全相同。`detailed` 必须有审核过程，`brief`/`conclusion_only` 必须没有。
- `confirmation` 必须且只能含等于当前 inventory revision 的正整数 `confirmedRevision`、64 位小写十六进制 `inventorySha256`、非空 `userStatement`、枚举唯一值 `outcome=confirmed_complete` 和恒为 true 的 `confirmedAfterInventory`；摘要必须等于 `sha256(json.dumps(inventory, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False))`。`userStatement` 仅做空白规范化，必须包含“没有更多内容/无更多内容/没有遗漏/没有漏传/已全部提供/以上为全部/确认完整”之一；它记录清点后的用户答复，绝不从工作人员、审核文字或紧急程度推断。补充输入必须生成新 revision 和摘要，旧确认不可复用。
- `independentReview` 必须且只能含 `mode`（`isolated_blind` 或 `independent_non_blind`）、恒为 true 的 `completedBeforeComparison`、`artifact` 和 64 位小写十六进制 `artifactSha256`。`artifact` 必须且只能含 JSON 数组 `materialFacts`、与 `inputScope.standardKind` 一致的 `standardKind`、唯一 `ruleCode` 的 `ruleResults` 数组和规则结果枚举 `finalResult`；摘要必须等于确定性 artifact JSON 的 SHA-256。标准缺失时 `ruleResults` 必须为空且 `finalResult=无法判断`；其他可用标准只有“审核条件与结论一致性”能力明确为 `not_run`（能力或输入阻断独立计算）时才可为空。后者证明冻结独立复核 JSON 已在比较前保存并哈希；`independent_non_blind` 必须披露确认偏差限制，不能称为盲审。
- 可选 `interpretationPaths` 只能用于会改变结论的自然语言标准歧义：它是至少 2 条的数组；每条必须且只能含唯一非空 `pathId`、非空 `interpretation`、非空 `ruleResults`、`finalResult`。每条路径 `ruleResults` 的 `ruleCode` 必须唯一且所有路径使用同一集合；每项只含非空 `ruleCode` 和“满足/不满足/无法判断/不适用”之一的 `result`；`finalResult` 同样取该四值。各路径 `finalResult` 不得全部相同，且此时 `qcConclusion` 必须是“无法确定”，总体建议必须要求人工确认。不会改变结论的歧义不使用该字段，而作为正常问题或说明记录。
- `capabilities` 是对象数组；每项必须含 `name`、`status`、`reason`，其中状态为 `completed`、`partial` 或 `not_run`。`completed` 的 `reason` 可为空字符串，`partial` 和 `not_run` 必须有非空原因；名称必须唯一。
- `originalResult` 为非空字符串；`qcConclusion` 采用量规中的结论枚举，根级 `riskDirection` 采用量规中的风险枚举，`recommendedAction` 为非空字符串。
- `issues` 的每项必须含 `category`、`issueType`、`severity`、`ruleCode`、`keywordCode`、`modelClaim`、`evidenceStatus`、`materialEvidence`、`qcFinding`、`possibleImpact`、`impactOnFinalResult`、`riskDirection`、`recommendation`、`confidence`。其中 `category` 与同名 canonical capability 一一对应，能力为 `not_run` 时该类别不得出现问题，`partial`/`completed` 才可出现问题。`modelClaim` 是模型主张，`materialEvidence` 是实际材料或标准，`qcFinding` 说明问题原因，`possibleImpact` 说明可能影响，`recommendation` 是建议；这五项和置信度、evidenceStatus、可追溯原文与位置缺一不可。严重度和置信度为 `high`、`medium`、`low`；最终结论影响为 `changed`、`potentially_changed`、`unchanged`、`unknown`；问题风险代码为 `false_approval`、`false_rejection`、`both`、`none`；证据状态采用量规枚举。
- 问题风险代码 `none` 的清晰业务渲染固定为“未发现明显风险”，与根级风险枚举同名；不得使用其他风险文案。问题代码与根级风险枚举仍是不同字段。
- 每条 `materialEvidence` 必须含 `materialId`、`materialName`、`page`、`section`、`rawText`、`normalizedText`、`location`。`page` 为正整数，`normalizedText` 可为空字符串；`location` 为 `null`（精确位置不可得）或含非负整数 `start`、`end` 的对象，且 `start < end`。偏移量按 `materialId` 对应源文本的 Unicode 码点从零计数，`start` 包含、`end` 不包含；不得编造坐标。原始输入提供该材料文本时，范围必须精确切出 `rawText`。结构化 `rawInput.materials` 中每个声明了字符串 `materialId` 的条目都必须唯一，即使该条目没有可用于切片核验的正文。
- `ruleReviews` 每项必须含 `ruleCode`、`result`、`modelClaim`、`evidenceStatus`、`materialEvidence`、`qcFinding`、`recommendation`，结果和证据状态采用量规枚举。
- `unperformedChecks` 每项必须含 `name`、`reason`；若提供 `status`，其值只能为 `not_run`。名称必须唯一，并与 `capabilities` 中所有且仅有的 `not_run` 名称及原因完全一致；`completed`、`partial` 不得出现在此列表。
- `rawInput` 可为任意 JSON 值，但不能含循环、重复键、元组等非 JSON 容器、非 JSON 值、超深结构或非字符串对象键。JSON 字符串和文件输入也会拒绝每层的重复键。校验返回的规范对象保留有效原始 JSON 字符串（包括控制字符和孤立代理项）；仅渲染时做显示安全化。

文本部分按如下顺序：质控结论、输入与检查范围、影响最终结论的问题、材料缺失复核、证据准确性、过度推理、条件一致性、规则维护质量、逐规则复核、建议、未执行检查、原始输入。每一空集合均须显示明确空状态。所有动态文本使用单行 JSON 字符串表示；控制字符及所有 `splitlines` 分隔符均转义，原始输入使用安全 JSON 序列化，不能形成额外报告标题或字段。

## 能力矩阵与结论风险

`capabilities` 必须恰好各一次包含：材料缺失判断准确性、证据提取准确性、过度推理、审核条件与结论一致性、规则维护质量。`conclusion_only` 的材料缺失、证据提取、过度推理均为 `not_run`，审核条件与结论一致性只能为部分完成/未执行；`brief` 的材料缺失和过度推理可根据可见主张为完成/部分完成/未执行，审核条件与结论一致性必须为未执行。两者的证据提取均为 `not_run` 且原因严格为“未提供原审核证据或规则过程”，并且没有 `ruleReviews`。无标准时规则维护为 `not_run`、没有 `ruleReviews`，条件一致性不能完成；不完整结构化的条件一致性不能完成，规则维护可完成/部分完成；自然语言的规则维护只能部分完成/未执行。

任一 `changed`/`potentially_changed` 问题禁止“可靠”“基本可靠”，且其问题风险不得为 `none`，只能是 `false_approval`、`false_rejection` 或 `both`。全为 `false_approval` 时根风险必须为“错误放行风险”，全为 `false_rejection` 时必须为“错误拒绝风险”，`both` 或混合方向时必须为“暂时无法判断”；根风险不得相反。问题风险 `both` 渲染为“错误放行与错误拒绝风险”，`none` 渲染为“未发现明显风险”。

## 生成、交付与一致性核验

确认关口通过后，先构造并校验上述规范对象；所有已执行和未执行维度都必须在 `capabilities`、`unperformedChecks`、`issues` 或 `ruleReviews` 中可见。不得手写与对象分叉的正文。只允许运行：

```text
python3 scripts/render_qc_html.py <对象JSON> <HTML> --text-output <临时文本>
```

该渲染器从同一个对象同时生成文本和 HTML；`interpretationPaths` 存在时，两份输出均在“输入与检查范围”逐条展示路径、解释、逐规则结果和最终结果。读取生成的临时文本并直接返回其内容给用户，将 HTML 作为文件交付。随后重新读取文本和 HTML 做一致性核验：质控结论、根级风险、问题数量、每个高风险问题、关键证据、建议、已执行/未执行检查以及解释路径必须一致；发现分歧时只修正规范对象，再由渲染器重建两份输出。

CLI 将所有请求输出先在各自目标目录中暂存，再共同替换目标；输入、HTML 输出和可选文本输出在规范化路径相同（含可发现的符号链接别名）时被拒绝。已有路径会安全使用同文件判定；不存在叶节点则以解析后的父目录、Unicode NFC 和大小写折叠比较。任一暂存或替换失败时，既有目标内容会恢复，且不会留下新建的部分输出；若回滚本身失败，命令会明确报告输出可能不一致及受影响路径。
