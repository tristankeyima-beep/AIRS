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
  "assembledCertificationList": {
    "logicTopology": {
      "children": [
        {
          "ruleCode": "01001",
          "type": "RULE_REF"
        },
        {
          "ruleCode": "01002",
          "type": "RULE_REF"
        },
        {
          "ruleCode": "01003",
          "type": "RULE_REF"
        }
      ],
      "operator": "AND",
      "type": "GROUP"
    },
    "meta": {
      "chronicDiseaseCode": "SJ01",
      "chronicDiseaseName": "尿毒症透析",
      "createdAt": "2026-07-21",
      "description": "由 ADP 知识库检索结果生成",
      "sourceFile": "八类疾病准入条件及细则-20260517.xlsx",
      "version": "ADP-尿毒症透析-认定标准-v20260517"
    },
    "ruleRepository": [
      {
        "experience": "",
        "ruleCode": "01001",
        "ruleContent": "各种原因造成慢性肾脏损伤，并出现肾功能异常达到尿毒症期",
        "ruleKeywordGuide": [
          {
            "dataType": "enum",
            "enumOptions": ["是", "否", "无法判断"],
            "keywordCode": "01001001",
            "keywordContent": "肯定证据：有明确的慢性肾脏损伤诊断，且肾功能异常达到尿毒症期；排除边界：无慢性肾脏损伤诊断或肾功能未达尿毒症期则无法判定；优先材料位置：病案首页、出院记录或诊断证明",
            "required": true
          }
        ],
        "ruleSource": "八类疾病准入条件及细则-20260517.xlsx",
        "sourceMdFile": "尿毒症透析-认定标准-v20260517",
        "sourceRuleContent": "各种原因造成慢性肾脏损伤，并出现肾功能异常达到尿毒症期",
        "sourceSection": "认定标准"
      },
      {
        "experience": "",
        "ruleCode": "01002",
        "ruleContent": "需长期透析治疗",
        "ruleKeywordGuide": [
          {
            "dataType": "enum",
            "enumOptions": ["是", "否", "无法判断"],
            "keywordCode": "01002001",
            "keywordContent": "肯定证据：病历资料显示需要长期进行透析治疗；排除边界：仅需短期透析或无透析治疗需求则无法判定；优先材料位置：病案首页、出院记录或诊断证明",
            "required": true
          }
        ],
        "ruleSource": "八类疾病准入条件及细则-20260517.xlsx",
        "sourceMdFile": "尿毒症透析-认定标准-v20260517",
        "sourceRuleContent": "需长期透析治疗",
        "sourceSection": "认定标准"
      },
      {
        "experience": "",
        "ruleCode": "01003",
        "ruleContent": "有二级及以上医疗机构出具的病历资料",
        "ruleKeywordGuide": [
          {
            "dataType": "enum",
            "enumOptions": ["是", "否", "无法判断"],
            "keywordCode": "01003001",
            "keywordContent": "肯定证据：提供的病历资料出具机构为二级及以上医疗机构；排除边界：出具机构为二级以下医疗机构或无相关病历资料则无法判定；优先材料位置：所有提供的病历资料",
            "required": true
          }
        ],
        "ruleSource": "八类疾病准入条件及细则-20260517.xlsx",
        "sourceMdFile": "尿毒症透析-认定标准-v20260517",
        "sourceRuleContent": "有二级及以上医疗机构出具的病历资料",
        "sourceSection": "认定标准"
      }
    ]
  },
  "originalCertificationList": {
    "logicTopology": {
      "children": [
        {"ruleCode": "01001", "type": "RULE_REF"},
        {"ruleCode": "01002", "type": "RULE_REF"},
        {"ruleCode": "01003", "type": "RULE_REF"}
      ],
      "operator": "AND",
      "type": "GROUP"
    },
    "meta": {
      "chronicDiseaseCode": "SJ01",
      "chronicDiseaseName": "尿毒症透析",
      "createdAt": "2026-05-17",
      "description": "省局项目8个病种认定标准结构化版本",
      "sourceFile": "八类疾病准入条件及细则-20260517.xlsx",
      "version": "V20260517"
    },
    "ruleRepository": [
      {
        "experience": "",
        "ruleCode": "01001",
        "ruleContent": "各种原因造成慢性肾脏损伤，并出现肾功能异常达到尿毒症期",
        "ruleKeywordGuide": [
          {
            "dataType": "enum",
            "enumOptions": ["是", "否", "无法判断"],
            "keywordCode": "01001001",
            "keywordContent": "判断材料中是否明确记载慢性肾脏损伤、慢性肾脏病、慢性肾衰竭等慢性肾脏损害相关诊断或病史。肯定证据包括出院诊断、入院诊断、诊断证明或病程记录中明确描述慢性肾脏损伤；仅出现一次性肾功能指标异常、急性肾损伤或单项肌酐升高，不得判定为慢性肾脏损伤。优先查看病案首页、出院记录、入院记录、诊断证明。",
            "required": true
          },
          {
            "dataType": "enum",
            "enumOptions": ["是", "否", "无法判断"],
            "keywordCode": "01001002",
            "keywordContent": "判断材料中是否明确达到尿毒症期或终末期肾病阶段。肯定证据包括诊断为尿毒症、终末期肾病、CKD5期、慢性肾衰竭尿毒症期，或病历明确写明肾功能异常已达尿毒症期；仅出现肾功能不全、肌酐升高、CKD但无5期/尿毒症期描述，不得判定为达标。优先查看出院诊断、诊断证明、出院记录。",
            "required": true
          }
        ],
        "ruleSource": "八类疾病准入条件及细则-20260517.xlsx",
        "sourceMdFile": "尿毒症透析-认定标准-v20260517.md",
        "sourceRuleContent": "1.各种原因造成慢性肾脏损伤，并出现肾功能异常达到尿毒症期。\n2.需长期透析治疗。\n3.有二级及以上医疗机构出具的病历资料。",
        "sourceSection": ""
      },
      {
        "experience": "",
        "ruleCode": "01002",
        "ruleContent": "需长期透析治疗",
        "ruleKeywordGuide": [
          {
            "dataType": "enum",
            "enumOptions": ["是", "否", "无法判断"],
            "keywordCode": "01002001",
            "keywordContent": "判断材料中是否明确需要或已经接受长期透析治疗。肯定证据包括维持性血液透析、规律血透、腹膜透析、长期透析治疗、透析医嘱或透析记录；仅出现一次临时透析、建议评估透析或未明确长期/维持性治疗，不得判定为肯定。优先查看出院记录、治疗经过、医嘱、透析记录。",
            "required": true
          }
        ],
        "ruleSource": "八类疾病准入条件及细则-20260517.xlsx",
        "sourceMdFile": "尿毒症透析-认定标准-v20260517.md",
        "sourceRuleContent": "1.各种原因造成慢性肾脏损伤，并出现肾功能异常达到尿毒症期。\n2.需长期透析治疗。\n3.有二级及以上医疗机构出具的病历资料。",
        "sourceSection": ""
      },
      {
        "experience": "",
        "ruleCode": "01003",
        "ruleContent": "有二级及以上医疗机构出具的病历资料",
        "ruleKeywordGuide": [
          {
            "dataType": "enum",
            "enumOptions": ["二级及以上", "二级以下", "无法判断"],
            "keywordCode": "01003001",
            "keywordContent": "判断病历资料出具机构是否为二级及以上医疗机构。肯定证据包括医院等级字段、病案首页、诊断证明或病历抬头明确显示二级、三级、二甲、三甲等；仅有医院名称但无法确认等级时应判无法判断；社区卫生服务中心、乡镇卫生院、一级医院不得判二级及以上。优先查看医院等级字段、病案首页、诊断证明、病历首页。",
            "required": true
          }
        ],
        "ruleSource": "八类疾病准入条件及细则-20260517.xlsx",
        "sourceMdFile": "尿毒症透析-认定标准-v20260517.md",
        "sourceRuleContent": "1.各种原因造成慢性肾脏损伤，并出现肾功能异常达到尿毒症期。\n2.需长期透析治疗。\n3.有二级及以上医疗机构出具的病历资料。",
        "sourceSection": ""
      }
    ]
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
