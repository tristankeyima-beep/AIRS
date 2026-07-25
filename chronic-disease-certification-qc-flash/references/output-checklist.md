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

- [ ] 规则和提取项 ID 连续且唯一。
- [ ] 每条规则都有非空来源原文。
- [ ] 每条规则在逻辑树中恰好出现一次。
- [ ] AND/OR、阈值、单位和范围与用户确认一致。
- [ ] 不存在影响规则含义的未决歧义。

## 模式 2

- [ ] 五个质控维度各出现一次。
- [ ] `baseReview` 在 `auditComparison` 之前形成。
- [ ] 每个问题都有证据、来源、影响和建议。
- [ ] 无标准、简要结果或仅结论输入的受限检查标记为 `not_checked`。
- [ ] 总体结论、风险方向、问题严重程度和详细问题一致。
- [ ] 风险方向：交叉核对 `baseReview.preliminaryResult` 与 `auditComparison.originalConclusion`；原审核通过而独立复核不满足对应 `false_approval（错误通过）`，原审核不通过而独立复核满足对应 `false_rejection（错误拒绝）`，仅同时存在两种方向时使用 `both（双向风险）`，信息不足时使用 `unknown`。
- [ ] 局部问题：允许 `problematic + none`，但问题必须不改变通过/不通过方向；`reliable + none` 仍要求没有任何问题维度或问题记录。
- [ ] 仅结论输入：前三个过程依赖维度必须为 `not_checked`，并分别写明无法核查的原因。
- [ ] 仅结论且方向相反：第四维“审核条件与结论一致性”标为 `issue`，总体结论为 `problematic`，并按错误通过或错误拒绝方向使用 `false_approval` 或 `false_rejection`。
- [ ] 仅结论且方向一致：方向一致也必须使用不确定结论，总体结论为 `uncertain`、风险为 `unknown`；即使发现规则维护问题，也禁止标为可靠或改成 `problematic + none`。
- [ ] 仅结论且方向未知：第四维标为 `not_checked`，总体结论为 `uncertain`、风险为 `unknown`；只有此分支已由现有信息证实的局部规则维护问题可例外使用 `problematic + none`。
- [ ] 仅结论且标准缺失（标准缺失且仅有原审核结论）：第四维和规则维护质量均标为 `not_checked`，总体结论为 `uncertain`、风险为 `unknown`。
- [ ] 确认清单：`confirmation.inventoryShown` 必须与 `sourceDocuments[].name` 顺序和内容完全一致，且文档名不得重复。
