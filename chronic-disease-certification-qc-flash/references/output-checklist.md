# Flash 成果自检

- 模式 2 风险方向：交叉核对 `baseReview.preliminaryResult` 与 `auditComparison.originalConclusion`；原审核通过而独立复核不满足对应 `false_approval（错误通过）`，原审核不通过而独立复核满足对应 `false_rejection（错误拒绝）`，仅同时存在两种方向时使用 `both（双向风险）`，信息不足时使用 `unknown`。
- 模式 2 局部问题：允许 `problematic + none`，但问题必须不改变通过/不通过方向；`reliable + none` 仍要求没有任何问题维度或问题记录。
- 模式 2 仅结论输入：前三个过程依赖维度必须为 `not_checked`；用明确中文结论方向和独立复核方向检查“审核条件与结论一致性”。方向相反必须标问题及错误通过/错误拒绝风险；方向一致也必须使用不确定结论与 `unknown`，即使有规则维护问题也禁止标为可靠或改成 `problematic + none`；方向未知时第四维不检查且总体为不确定与 `unknown`，仅此分支的局部规则维护问题可使用 `problematic + none`。标准缺失且仅有原审核结论时，第四维和规则维护质量均不检查，总体必须不确定。
- 模式 2 确认清单：`confirmation.inventoryShown` 必须与 `sourceDocuments[].name` 顺序和内容完全一致，且文档名不得重复。
