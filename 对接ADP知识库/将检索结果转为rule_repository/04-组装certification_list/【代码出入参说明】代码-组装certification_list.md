# 代码节点出入参说明：组装 certification_list

对应代码：`代码-组装certification_list.py`

## 节点职责

将 ADP 分支已经生成的病种信息、规则库、逻辑树和确定性文档名组装为完整 `certification_list`，直接接入既有审核流程。

## 入参

| 字段 | 类型 | 必填 | 绑定来源 |
| --- | --- | --- | --- |
| `chronicDiseaseName` | `str` | 是 | 根据 certification_list 获取备案病种节点输出。 |
| `chronicDiseaseCode` | `str` | 是 | 根据 certification_list 获取备案病种节点输出。 |
| `documentName` | `str` | 是 | 提取相关性最高的知识库结果节点输出。 |
| `ruleRepository` | `[obj]` 或 `obj` 或 `str` | 是 | 将 ADP 提取出的 ruleRepository 结构化节点输出。 |
| `logicTopology` | `obj` 或 `str` | 是 | 将 ADP 提取出的 ruleRepository 结构化节点输出。 |

推荐腾讯绑定：

```text
chronicDiseaseName = 根据 certification_list 获取备案病种.chronicDiseaseName
chronicDiseaseCode = 根据 certification_list 获取备案病种.chronicDiseaseCode
documentName = 提取相关性最高的知识库结果.documentName
ruleRepository = 将 ADP 提取出的 ruleRepository 结构化.ruleRepository
logicTopology = 将 ADP 提取出的 ruleRepository 结构化.logicTopology
```

## 可直接粘贴测试的入参示例

```json
{
  "chronicDiseaseName": "尿毒症透析",
  "chronicDiseaseCode": "M07801",
  "documentName": "尿毒症透析-认定标准-v20260517.md",
  "ruleRepository": [
    {
      "ruleCode": "01001",
      "ruleContent": "各种原因造成慢性肾脏损伤，并出现肾功能异常达到尿毒症期",
      "ruleSource": "八类疾病准入条件及细则-20260517.xlsx",
      "experience": "",
      "ruleKeywordGuide": [
        {
          "keywordCode": "01001001",
          "dataType": "enum",
          "required": true,
          "keywordContent": "判断材料中是否明确存在慢性肾脏损伤；仅一次性肾功能指标异常不得判定为慢性肾脏损伤。",
          "enumOptions": ["是", "否", "无法判断"]
        },
        {
          "keywordCode": "01001002",
          "dataType": "enum",
          "required": true,
          "keywordContent": "判断材料中是否明确达到尿毒症期或终末期肾病阶段。",
          "enumOptions": ["是", "否", "无法判断"]
        }
      ],
      "sourceRuleContent": "1.各种原因造成慢性肾脏损伤，并出现肾功能异常达到尿毒症期。",
      "sourceMdFile": "尿毒症透析-认定标准-v20260517.md",
      "sourceSection": "认定标准"
    },
    {
      "ruleCode": "01002",
      "ruleContent": "需长期透析治疗",
      "ruleSource": "八类疾病准入条件及细则-20260517.xlsx",
      "experience": "",
      "ruleKeywordGuide": [
        {
          "keywordCode": "01002001",
          "dataType": "enum",
          "required": true,
          "keywordContent": "判断材料中是否明确需要或已经接受长期透析治疗。",
          "enumOptions": ["是", "否", "无法判断"]
        }
      ],
      "sourceRuleContent": "2.需长期透析治疗。",
      "sourceMdFile": "尿毒症透析-认定标准-v20260517.md",
      "sourceSection": "认定标准"
    }
  ],
  "logicTopology": {
    "type": "GROUP",
    "operator": "AND",
    "children": [
      {"type": "RULE_REF", "ruleCode": "01001"},
      {"type": "RULE_REF", "ruleCode": "01002"}
    ]
  }
}
```

## 出参

```text
certification_list: obj
  meta: obj
    version: str
    chronicDiseaseName: str
    chronicDiseaseCode: str
    createdAt: str
    description: str
    sourceFile: str
  ruleRepository: [obj]
  logicTopology: obj
```

## 元信息生成规则

```text
documentName = 尿毒症透析-认定标准-v20260517.md
version = ADP-尿毒症透析-认定标准-v20260517
createdAt = 节点执行日期，例如 2026-07-21
description = 由 ADP 知识库检索结果生成
sourceFile = ruleRepository 第一条规则的 ruleSource；缺失时为 ADP知识库检索结果
```

## 校验

病种名称、病种编码、文档名、规则库和逻辑树均不能为空。每条规则必须有唯一 `ruleCode`；逻辑树只能使用 GROUP / RULE_REF，且每个 `RULE_REF.ruleCode` 必须在 `ruleRepository` 中存在。

## 下游绑定

把本节点的 `certification_list` 直接绑定到既有审核流程“规则库转可迭代数组”节点的 `certification_list` 入参，类型选 `obj`。
