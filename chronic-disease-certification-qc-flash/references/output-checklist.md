# Flash 成果自检

- 模式 2 风险方向：交叉核对 `baseReview.preliminaryResult` 与 `auditComparison.originalConclusion`；原审核通过而独立复核不满足对应 `false_approval（错误通过）`，原审核不通过而独立复核满足对应 `false_rejection（错误拒绝）`，仅同时存在两种方向时使用 `both（双向风险）`，信息不足时使用 `unknown`。
