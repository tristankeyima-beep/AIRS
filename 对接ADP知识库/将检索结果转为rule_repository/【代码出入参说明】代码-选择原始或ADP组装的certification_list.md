# 代码节点出入参说明：选择原始或 ADP 组装的 certification_list

对应代码：`代码-选择原始或ADP组装的certification_list.py`

## 节点职责

该节点位于“是否有检索结果”分支汇合处，统一向结束节点输出 `certification_list`，并以条件节点输出的 `ConditionIndex` 为唯一判断依据。

- `ConditionIndex=1`：没有合适的知识库检索结果，输出初始 `originalCertificationList`。
- `ConditionIndex=2`：存在合适的知识库检索结果，输出 ADP 分支组装的 `assembledCertificationList`。

节点不判断 `knowledgeContent`，也不根据 `assembledCertificationList` 是否为空推断分支。

## 入参

| 字段 | 类型 | 必填 | 绑定来源 | 说明 |
| --- | --- | --- | --- | --- |
| `ConditionIndex` | `int` | 是 | 是否有检索结果.`ConditionIndex` | 条件节点的分支编号。`1` 为无合适检索结果，`2` 为有合适检索结果。兼容字符串 `"1"` / `"2"`。 |
| `originalCertificationList` | `obj` | 是 | 工作流初始入参 `certification_list` | 完整的原始对象；当 `ConditionIndex=1` 时输出。 |
| `assembledCertificationList` | `obj` | 否 | 组装 certification_list.`certification_list` | 完整 ADP 组装对象；当 `ConditionIndex=2` 且对象存在时输出。 |

两个 `certification_list` 字段都应绑定完整对象，不能只传 `ruleRepository` 或 JSON 字符串。

## 选择规则

1. `ConditionIndex=1`：直接输出 `originalCertificationList`，不读取 `assembledCertificationList`。
2. `ConditionIndex=2` 且 `assembledCertificationList` 为完整对象：输出 `assembledCertificationList`。
3. `ConditionIndex=2` 但 `assembledCertificationList` 未传入、为 `null` 或为空字符串：回退输出 `originalCertificationList`。
4. `ConditionIndex` 未传入、不是数字，或不是 `1` / `2`：报错 `ConditionIndex 必须是 1 或 2`。
5. 节点不合并、不改写两个对象中的 `meta`、`ruleRepository` 或 `logicTopology`。

## 腾讯平台配置

代码节点输入：

```text
ConditionIndex = 是否有检索结果.ConditionIndex
类型 = int

originalCertificationList = 工作流初始入参 certification_list
类型 = obj

assembledCertificationList = 组装 certification_list.certification_list
类型 = obj
```

## 可直接粘贴测试的入参示例

### 无合适检索结果：ConditionIndex 为 1

```json
{
  "ConditionIndex": 1,
  "originalCertificationList": {
    "meta": {"version": "v20260517"},
    "ruleRepository": [{"ruleCode": "01001"}],
    "logicTopology": {"type": "RULE_REF", "ruleCode": "01001"}
  }
}
```

出参：

```json
{
  "certification_list": {
    "meta": {"version": "v20260517"},
    "ruleRepository": [{"ruleCode": "01001"}],
    "logicTopology": {"type": "RULE_REF", "ruleCode": "01001"}
  }
}
```

### 有合适检索结果：ConditionIndex 为 2

```json
{
  "ConditionIndex": 2,
  "originalCertificationList": {
    "meta": {"version": "v20260517"}
  },
  "assembledCertificationList": {
    "meta": {"version": "ADP-尿毒症透析-认定标准-v20260517"},
    "ruleRepository": [{"ruleCode": "01001"}, {"ruleCode": "01002"}],
    "logicTopology": {
      "type": "GROUP",
      "operator": "AND",
      "children": [
        {"type": "RULE_REF", "ruleCode": "01001"},
        {"type": "RULE_REF", "ruleCode": "01002"}
      ]
    }
  }
}
```

此时出参 `certification_list` 即为 `assembledCertificationList`。

## 出参

```text
certification_list: obj
```

将本节点的 `certification_list` 绑定到最终“结束”节点的 `Output.certification_list`。

## 联调定位

| 现象 | 原因与处理 |
| --- | --- |
| 无检索结果却输出 ADP 规则 | 检查 `ConditionIndex` 是否错误传为 `2`。 |
| 有检索结果却输出原始规则 | 检查 `ConditionIndex` 是否错误传为 `1`。 |
| `ConditionIndex=2` 却输出原始规则 | “组装 certification_list”节点没有向 `assembledCertificationList` 提供完整对象；当前代码会安全回退。 |
| `ConditionIndex 必须是 1 或 2` | 条件节点的 `ConditionIndex` 未绑定，或分支编号与当前两分支约定不一致。 |
