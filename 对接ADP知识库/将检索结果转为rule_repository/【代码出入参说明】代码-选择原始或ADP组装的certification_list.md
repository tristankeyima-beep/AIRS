# 代码节点出入参说明：选择原始或 ADP 组装的 certification_list

对应代码：`代码-选择原始或ADP组装的certification_list.py`

## 节点职责

作为“从知识库检索认定标准”分支的最后一个节点，依据“提取相关性最高的知识库结果”节点的 `knowledgeContent` 是否为空，选择输出原始 `certification_list` 或 ADP 分支新组装的 `certification_list`。

本节点不改写、不合并两个对象中的 `meta`、`ruleRepository` 或 `logicTopology`。

## 入参

| 字段 | 类型 | 必填 | 绑定来源 | 说明 |
| --- | --- | --- | --- | --- |
| `knowledgeContent` | `str` | 否 | 提取相关性最高的知识库结果.`knowledgeContent` | 空字符串、空白字符串或未传入，表示未检索到包含当前病种名称的有效 DOC。 |
| `originalCertificationList` | `obj` | 是 | 流程最初接收的 `certification_list` | 原始完整对象，用于检索未命中时回退。 |
| `assembledCertificationList` | `obj` | 是 | 组装 certification_list.`certification_list` | ADP 分支生成的完整对象，用于检索命中时替换原始规则。 |

两个 `certification_list` 入参必须绑定为完整对象，不能只传 `ruleRepository` 或 JSON 字符串。

## 选择规则

1. 当 `knowledgeContent` 为 `null`、`""` 或仅含空白字符时，输出 `originalCertificationList`。
2. 当 `knowledgeContent` 存在非空正文时，输出 `assembledCertificationList`。
3. 输出对象保持所选入参的原有内容，不生成新版本号、不修改规则编号。

## 腾讯平台配置

代码节点输入：

```text
knowledgeContent = 提取相关性最高的知识库结果.knowledgeContent
类型 = str

originalCertificationList = 工作流初始入参 certification_list
类型 = obj

assembledCertificationList = 组装 certification_list.certification_list
类型 = obj
```

## 可直接粘贴测试的入参示例

### 知识库未命中，回退原始规则

```json
{
  "knowledgeContent": "",
  "originalCertificationList": {
    "meta": {
      "version": "v20260517",
      "chronicDiseaseName": "尿毒症透析",
      "chronicDiseaseCode": "M07801"
    },
    "ruleRepository": [{"ruleCode": "01001"}],
    "logicTopology": {"type": "RULE_REF", "ruleCode": "01001"}
  },
  "assembledCertificationList": {
    "meta": {
      "version": "ADP-尿毒症透析-认定标准-v20260517",
      "chronicDiseaseName": "尿毒症透析",
      "chronicDiseaseCode": "M07801"
    },
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

对应出参：

```json
{
  "certification_list": {
    "meta": {
      "version": "v20260517",
      "chronicDiseaseName": "尿毒症透析",
      "chronicDiseaseCode": "M07801"
    },
    "ruleRepository": [{"ruleCode": "01001"}],
    "logicTopology": {"type": "RULE_REF", "ruleCode": "01001"}
  }
}
```

## 出参

```text
certification_list: obj
```

将本节点的 `certification_list` 直接绑定到既有“认定标准提取”流程的 `certification_list` 入参。

## 联调定位

| 现象 | 原因与处理 |
| --- | --- |
| 始终返回原始规则 | 检查 `knowledgeContent` 是否正确绑定到“提取相关性最高的知识库结果”节点；空白正文会触发回退。 |
| `originalCertificationList 必须是完整 certification_list 对象` | 原始对象未绑定，或传入了字符串 / 规则数组。 |
| `assembledCertificationList 必须是完整 certification_list 对象` | 组装节点应绑定其完整 `certification_list` 出参。 |
