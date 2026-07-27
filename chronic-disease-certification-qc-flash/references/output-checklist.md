# 审核质控 Flash 成果自检

## 通用

- [ ] JSON 可解析，不含注释或尾逗号。
- [ ] `schemaVersion`、`mode` 和必填字段完整。
- [ ] 完整原文已进入 `sourceDocuments`。
- [ ] 可审阅分析已进入 `analysisRecord`。
- [ ] 用户确认记录与当前输入一致。
- [ ] HTML 使用 `assets/qc-report-template.html`。
- [ ] 替换前，模板的 `flash-data` 数据槽中 `__FLASH_DATA_JSON__` 占位符恰好出现一次。
- [ ] 替换后，提取 `flash-data` 数据槽并确认内容已装载、可解析为 JSON，且不再是纯占位符。
- [ ] 完整 HTML 中同名字面串可作为用户数据合法存在，不以全文搜索判定残留。
- [ ] 模板 CSS 和 JavaScript 未修改。
- [ ] HTML 内嵌数据可以还原为交付 JSON，并逐字段等值。
- [ ] 页面不直接展示英文状态、风险或严重程度。
- [ ] HTML 的规则、证据、结论、风险、问题和建议均来自 JSON。
- [ ] 疑似秘密已触发立即停止；脱敏告警不含具体值，且没有回显、记录或上传秘密。
- [ ] 外部发送已同时确认目标服务或地址、具体动作和材料范围；任一项不清楚时仍保持本地处理。

## 审核质控

- [ ] 逐份来源材料各对应一条 `sourceDocuments`，`content` 保留完整原文，未合并或摘要。
- [ ] 五个质控维度各出现一次。
- [ ] `baseReview` 三部分在 `auditComparison` 之前形成，形成期间未读取任何 `audit_result`。
- [ ] `standardKind=structured` 时，`ruleJudgments[].ruleId` 复用正式规则码并覆盖逻辑树全部规则；自然语言标准仍使用 `TMP-R001` 分支。
- [ ] 病种来源：`meta.diseaseName`、`meta.reportTitle` 中的病种名均来自本轮输入，未沿用上一轮上下文。
- [ ] 原审核引用的所有材料 ID 均已在患者材料名称或完整原文定位；未定位项已按证据提取问题记录，严重程度至少为 `medium`，且 ID 原样进入 `sourceReference`。
- [ ] 每个问题都有证据、来源、影响和建议。
- [ ] 无标准、简要结果或仅结论输入的受限检查标记为 `not_checked`。
- [ ] 总体结论优先级正确：仅五维全 `passed` 且无问题时为 `reliable`；任何实际问题为 `problematic`；仅有 `not_checked` 且无实际问题时为 `uncertain`。
- [ ] 风险方向：交叉核对 `baseReview.preliminaryResult` 与 `auditComparison.originalConclusion`；原审核通过而独立复核不满足对应 `false_approval（错误通过）`，原审核不通过而独立复核满足对应 `false_rejection（错误拒绝）`，仅同时存在两种方向时使用 `both（双向风险）`，信息不足时使用 `unknown`。
- [ ] 局部问题：仅在已确认局部问题但无已确认方向性风险时使用 `problematic + none`，包括方向一致或因输入受限而方向不明确的场景；`reliable + none` 仍要求没有任何问题维度或问题记录。
- [ ] 仅结论输入：前三个过程依赖维度必须为 `not_checked`，并分别写明无法核查的原因。
- [ ] 仅结论且方向相反：第四维“审核条件与结论一致性”标为 `issue`，总体结论为 `problematic`，并按错误通过或错误拒绝方向使用 `false_approval` 或 `false_rejection`。
- [ ] 仅结论且方向一致、无实际问题：因前三维未检查，方向一致也必须使用不确定结论，总体结论为 `uncertain`、风险为 `unknown`，禁止标为可靠。
- [ ] 仅结论存在规则维护实际问题：方向相反时始终保留对应的 `false_approval` 或 `false_rejection`；仅在无已确认方向性风险时使用 `problematic + none`，并记录规则维护质量问题。
- [ ] 仅结论且方向未知：第四维标为 `not_checked`，总体结论为 `uncertain`、风险为 `unknown`；只有此分支已由现有信息证实的局部规则维护问题可例外使用 `problematic + none`。
- [ ] 仅结论且标准缺失（标准缺失且仅有原审核结论）：第四维和规则维护质量均标为 `not_checked`，总体结论为 `uncertain`、风险为 `unknown`。

### 结论语义自检（生成前必做）

- [ ] 只有五维全 `passed` 且 `issues` 为空时，结论才是 `reliable`，并且 `risk=none`。
- [ ] 任一维度为 `issue` 或 `issues` 非空时，结论必须为 `problematic`，不受方向一致影响。
- [ ] `problematic` 且方向相反时，按原审核通过/独立复核不通过或原审核不通过/独立复核通过，分别使用对应的 `false_approval` 或 `false_rejection`。
- [ ] 问题为局部问题且方向一致或方向不明确时，使用 `problematic + none`。
- [ ] 只有 `not_checked` 且无实际问题时，才使用 `uncertain + unknown`。
- [ ] 任何实际问题的 `problematic` 优先于 `not_checked` 带来的 `uncertain`。

- [ ] 确认清单：`confirmation.inventoryShown` 必须与 `sourceDocuments[].name` 顺序和内容完全一致，且文档名不得重复。
