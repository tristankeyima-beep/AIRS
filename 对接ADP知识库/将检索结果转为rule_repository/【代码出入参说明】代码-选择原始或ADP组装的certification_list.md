# 代码节点出入参说明：选择原始或 ADP 组装的 certification_list

对应代码：`代码-选择原始或ADP组装的certification_list.py`

## 节点职责

该节点位于“是否有检索结果”两个分支的**汇合位置**，统一向结束节点输出 `certification_list`。

上游条件节点负责判断是否有检索结果，并决定哪条路径到达本节点：

- 无检索结果：直接到本节点；此路径没有 ADP 组装出参，节点返回原始 `certification_list`。
- 有检索结果：依次经过 LLM、结构化和“组装 certification_list”节点后到达本节点；节点返回 ADP 组装的 `certification_list`。

本节点不接收或判断 `knowledgeContent`；条件节点的分支路径决定 `assembledCertificationList` 是否可用。

## 入参

| 字段 | 类型 | 必填 | 绑定来源 | 说明 |
| --- | --- | --- | --- | --- |
| `originalCertificationList` | `obj` | 是 | 工作流初始入参 `certification_list` | 完整的原始对象，用于无检索结果的回退。 |
| `assembledCertificationList` | `obj` | 否 | 组装 certification_list.`certification_list` | 完整的 ADP 组装对象；仅“有检索结果”路径到达本节点时存在。 |

两个字段都应绑定完整对象，不能只传 `ruleRepository` 或 JSON 字符串。

## 选择规则

1. `assembledCertificationList` 未传入、为 `null` 或为空字符串：输出 `originalCertificationList`。
2. `assembledCertificationList` 为对象：输出 `assembledCertificationList`。
3. 节点不合并、不改写两个对象中的 `meta`、`ruleRepository` 或 `logicTopology`。

## 腾讯平台配置

代码节点输入：

```text
originalCertificationList = 工作流初始入参 certification_list
类型 = obj

assembledCertificationList = 组装 certification_list.certification_list
类型 = obj
```

“是否有检索结果”节点只负责控制路径：

```text
无检索结果分支 → 直接进入本节点
有检索结果分支 → LLM → 结构化 → 组装 certification_list → 本节点
```

## 可直接粘贴测试的入参示例

### 无检索结果分支

```json
{
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

### 有检索结果分支

```json
{
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
| 无检索结果却输出 ADP 规则 | 检查“无检索结果”分支是否误经过了组装节点，或是否传入了旧的 `assembledCertificationList`。 |
| 有检索结果却输出原始规则 | 检查“组装 certification_list”节点的完整出参是否绑定到 `assembledCertificationList`。 |
| `originalCertificationList 必须是完整 certification_list 对象` | 初始对象未绑定，或传入了字符串 / 规则数组。 |
| `assembledCertificationList 必须是完整 certification_list 对象` | 有检索结果路径传入的组装结果不是完整对象。 |
