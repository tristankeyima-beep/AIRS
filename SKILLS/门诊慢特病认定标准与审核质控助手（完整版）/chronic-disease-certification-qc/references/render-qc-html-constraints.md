# `render_qc_html.py` 约束手册

本手册面向构造 `qc_report_object.json` 的模型、人工维护者和测试人员。正式对象不满足任一硬约束时，渲染器会 fail-closed，不生成文本或 HTML。优先使用 `scripts/prepare_qc_report.py` 生成机械字段。

## 1. 根对象

根对象必须且只能包含 11 个字段：

```text
case
inputScope
capabilities
originalResult
qcConclusion
riskDirection
recommendedAction
issues
ruleReviews
unperformedChecks
rawInput
```

整个对象必须是合法 JSON，不能包含循环、非字符串对象键、NaN、Infinity 或超深结构。任何位置出现疑似凭据或秘密时拒绝渲染。

## 2. 常用枚举

| 字段 | 合法值 |
|---|---|
| `standardKind` | `structured_complete` / `structured_incomplete` / `natural_language` / `absent` |
| `auditResultKind` | `detailed` / `brief` / `conclusion_only` |
| 规则结果 | `满足` / `不满足` / `无法判断` / `不适用` |
| `evidenceStatus` | `SUPPORTED` / `CONTRADICTED` / `INSUFFICIENT` / `CONFLICTED` / `NOT_FOUND` / `NOT_APPLICABLE` |
| `severity`、`confidence` | `high` / `medium` / `low` |
| `impactOnFinalResult` | `changed` / `potentially_changed` / `unchanged` / `unknown` |
| 问题 `riskDirection` | `false_approval` / `false_rejection` / `both` / `none` |
| 根 `riskDirection` | `错误放行风险` / `错误拒绝风险` / `局部判断错误` / `仅影响规则质量` / `暂时无法判断` / `未发现明显风险` |
| `qcConclusion` | `可靠` / `基本可靠` / `存在重大疑点` / `不可靠` / `无法确定` |
| 能力状态 | `completed` / `partial` / `not_run` |
| 独立复核模式 | `isolated_blind` / `independent_non_blind` |

五项固定能力为：

1. 材料缺失判断准确性
2. 证据提取准确性
3. 过度推理
4. 审核条件与结论一致性
5. 规则维护质量

## 3. 三处 SHA-256

三处摘要均使用：

```python
hashlib.sha256(
    json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
).hexdigest()
```

| 字段 | 计算来源 |
|---|---|
| `inputScope.inventory.rawInputSha256` | 根 `rawInput` |
| `inputScope.confirmation.inventorySha256` | 当前 `inputScope.inventory` |
| `inputScope.independentReview.artifactSha256` | 当前独立复核 `artifact` |

不要手算。使用：

```bash
python3 scripts/prepare_qc_report.py draft.json qc_report_object.json
```

`rawInput`、inventory 或 artifact 任何内容改变后，对应摘要都必须重算。

## 4. `materialEvidence`

`issues[].materialEvidence` 和 `ruleReviews[].materialEvidence` 一律为数组：

- `NOT_FOUND`、`NOT_APPLICABLE`：必须为 `[]`。
- `SUPPORTED`、`CONTRADICTED`、`INSUFFICIENT`、`CONFLICTED`：必须为非空数组。

真实证据对象必须且只能包含：

```text
materialId, materialName, page, section,
rawText, normalizedText, location
```

`page` 为正整数。`location` 为 `null`，或 `{start, end}` 且 `0 <= start < end`。有精确位置时，原文必须能从对应 `rawInput.materials[].content` 中按 Unicode 码点精确切出。材料正文标准键只使用 `content`；外部 `materialContent`、`text`、`rawText` 由准备工具归一。

最小示例：

```json
{
  "evidenceStatus": "SUPPORTED",
  "materialEvidence": [
    {
      "materialId": "M001",
      "materialName": "出院记录",
      "page": 1,
      "section": "出院情况",
      "rawText": "神志清楚，言语清晰",
      "normalizedText": "神志清楚，言语清晰",
      "location": null
    }
  ]
}
```

## 5. 输入确认与独立复核

正式输出要求：

- `confirmedByUser=true`。
- inventory revision 为正整数。
- `confirmation.confirmedRevision` 等于 inventory revision。
- `confirmedAfterInventory=true`。
- `outcome=confirmed_complete`。
- 用户确认语句必须整句匹配白名单。

白名单：

```text
确认没有更多内容
没有更多内容
无更多内容
没有遗漏
没有漏传
已全部提供
以上为全部
确认完整
我确认完整
我确认没有更多内容
材料已全部提供
```

可只在末尾加“了”和句号/叹号。长句、疑问、不确定表达或附加指令不算确认。

独立复核必须在比较前冻结。`artifact` 只包含：

```text
materialFacts, standardKind, ruleResults, finalResult
```

标准缺失时，`ruleResults=[]` 且 `finalResult=无法判断`。隔离不可用或原结果已暴露时使用 `independent_non_blind`，不得称为盲审。

## 6. 能力、未执行检查与问题

`capabilities` 必须恰好包含五项固定能力各一次。`partial/not_run` 必须有非空原因。

正式对象中的 `unperformedChecks` 必须与全部 `not_run` 能力的名称和原因一致。准备工具会自动生成，不应由模型重复维护。

问题的 `category` 是主能力；可选 `relatedCapabilities` 表示同一根因影响的其他能力。相关能力不得重复主能力，数组内不得重复。可选 `issueId` 在整份报告中必须唯一。

一处根因只写一条问题。例如“不存在的材料 ID 指向另一份材料中的真实原文”是一条证据溯源错误，不拆成“材料缺失”和“证据提取”两个问题。

能力为 `not_run` 时，该能力不能作为问题主 `category`。应删除无法证明的问题，或在确实执行了部分检查时把能力调整为 `partial`。

无具体规则归属的问题可以使用空 `ruleCode/keywordCode`；页面显示“不适用”，不得制造虚假规则编码。

## 7. 结论与风险

- `changed/potentially_changed` 问题必须为高严重度，且问题风险不能为 `none`。
- 有改变或可能改变最终结论的问题时，根结论不能是“可靠/基本可靠”。
- 有中/高等级问题时，根风险不能是“未发现明显风险”。
- 只有规则质量问题时使用“仅影响规则质量”。
- 最终结论不变但存在证据或判断问题时，通常使用“局部判断错误”。

## 8. 七步速查

1. 根 11 字段齐全、无多余字段。
2. 所有枚举来自本手册。
3. 原始材料正文归一到 `content`。
4. `materialEvidence` 使用正确的空/非空数组。
5. inventory 展示后取得白名单整句确认。
6. 独立复核在比较前冻结。
7. 用准备工具生成哈希和未执行检查，再用渲染器输出文本与 HTML。

## 9. 实测踩坑对照

| 现象 | 根因 | 正确处理 |
|---|---|---|
| `requires empty` 后又报类型错误 | 用空字典表示无证据 | 使用 `[]` |
| issue 可过、ruleReview 不可过 | 两处证据结构不一致 | 两处都使用数组 |
| 改正文键后哈希失配 | rawInput 已改变 | 重新运行准备工具 |
| inventory 哈希失配 | inventory 已改变 | 重新运行准备工具 |
| artifact 哈希失配 | 冻结对象已改变 | 重新冻结并重算 |
| reason 只差几个字 | 两份原因手工重复 | 由准备工具生成 |
| location 无法定位 | 正文键不是 `content` | 先归一材料正文键 |

渲染失败时可运行：

```bash
python3 scripts/render_qc_html.py --explain
```
