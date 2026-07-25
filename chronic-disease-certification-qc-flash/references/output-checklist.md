# Flash 成果自检

## 通用

- [ ] JSON 可解析，不含注释或尾逗号。
- [ ] `schemaVersion`、`mode` 和当前模式必填字段完整。
- [ ] 完整原文已进入 `sourceDocuments`。
- [ ] 可审阅分析已进入 `analysisRecord`。
- [ ] 用户确认记录与当前输入一致。
- [ ] HTML 使用当前模式的正确模板。
- [ ] 替换前，模板的 `flash-data` 数据槽中 `__FLASH_DATA_JSON__` 占位符恰好出现一次。
- [ ] 替换后，提取 `flash-data` 数据槽并确认内容已装载、可解析为 JSON，且不再是纯占位符。
- [ ] 完整 HTML 中同名字面串可作为用户数据合法存在，不以全文搜索判定残留。
- [ ] 模板 CSS 和 JavaScript 未修改。
- [ ] HTML 内嵌数据可以还原为交付 JSON，并逐字段等值。
- [ ] 页面不直接展示英文状态、风险或严重程度。
- [ ] HTML 的规则、证据、结论、风险、问题和建议均来自 JSON。
- [ ] 疑似秘密已触发立即停止；脱敏告警不含具体值，且没有回显、记录或上传秘密。
- [ ] 外部发送已同时确认目标服务或地址、具体动作和材料范围；任一项不清楚时仍保持本地处理。

## 模式 1

- [ ] JSON 可解析，不含注释或尾逗号。
- [ ] 根字段恰好符合模式 1 契约，没有缺失或额外字段。
- [ ] 逐份输入材料各对应一条 `sourceDocuments`，`content` 保存完整来源原文且未合并、摘要、截断或改写。
- [ ] 每条规则的 `sourceQuote` 是单一来源中的连续原句，未拼接且未改写文字或标点。
- [ ] 规则 ID 从 `R001` 开始连续且唯一。
- [ ] 提取项 ID 在全部规则中从 `K001` 开始连续且唯一。
- [ ] 每条规则在逻辑树中恰好出现一次，AND/OR、阈值、单位和范围与用户确认一致。
- [ ] 每个提取项恰好有七个字段且均为非空字符串，`dataType` 只能为 `enum` 或 `text`。
- [ ] 用户确认已明确取得，记录与当前输入一致，且不存在影响规则含义的未决歧义。
- [ ] `flash-data` 数据槽已装载可解析 JSON，与交付 JSON 逐字段等值，模板 CSS 和 JavaScript 未修改。

## 模式 2

- [ ] 逐份来源材料各对应一条 `sourceDocuments`，`content` 保留完整原文，未合并或摘要。
- [ ] 五个质控维度各出现一次。
- [ ] `baseReview` 三部分在 `auditComparison` 之前形成，形成期间未读取任何 `audit_result`。
- [ ] `standardKind=structured` 时，`ruleJudgments[].ruleId` 复用正式规则码并覆盖逻辑树全部规则；自然语言标准仍使用 `TMP-R001` 分支。
- [ ] 原审核引用的所有材料 ID 均已在患者材料名称或完整原文定位；未定位项已按证据提取问题记录，严重程度至少为 `medium`，且 ID 原样进入 `sourceReference`。
- [ ] 每个问题都有证据、来源、影响和建议。
- [ ] 无标准、简要结果或仅结论输入的受限检查标记为 `not_checked`。
- [ ] 总体结论优先级正确：仅五维全 `passed` 且无问题时为 `reliable`；任何实际问题为 `problematic`；仅有 `not_checked` 且无实际问题时为 `uncertain`。
- [ ] 风险方向：交叉核对 `baseReview.preliminaryResult` 与 `auditComparison.originalConclusion`；原审核通过而独立复核不满足对应 `false_approval（错误通过）`，原审核不通过而独立复核满足对应 `false_rejection（错误拒绝）`，仅同时存在两种方向时使用 `both（双向风险）`，信息不足时使用 `unknown`。
- [ ] 局部问题：允许 `problematic + none`，但问题必须不改变通过/不通过方向；`reliable + none` 仍要求没有任何问题维度或问题记录。
- [ ] 仅结论输入：前三个过程依赖维度必须为 `not_checked`，并分别写明无法核查的原因。
- [ ] 仅结论且方向相反：第四维“审核条件与结论一致性”标为 `issue`，总体结论为 `problematic`，并按错误通过或错误拒绝方向使用 `false_approval` 或 `false_rejection`。
- [ ] 仅结论且方向一致、无实际问题：因前三维未检查，方向一致也必须使用不确定结论，总体结论为 `uncertain`、风险为 `unknown`，禁止标为可靠。
- [ ] 仅结论存在规则维护实际问题：无论方向是否一致，均按问题优先级使用 `problematic + none`，并记录规则维护质量问题。
- [ ] 仅结论且方向未知：第四维标为 `not_checked`，总体结论为 `uncertain`、风险为 `unknown`；只有此分支已由现有信息证实的局部规则维护问题可例外使用 `problematic + none`。
- [ ] 仅结论且标准缺失（标准缺失且仅有原审核结论）：第四维和规则维护质量均标为 `not_checked`，总体结论为 `uncertain`、风险为 `unknown`。
- [ ] 确认清单：`confirmation.inventoryShown` 必须与 `sourceDocuments[].name` 顺序和内容完全一致，且文档名不得重复。
