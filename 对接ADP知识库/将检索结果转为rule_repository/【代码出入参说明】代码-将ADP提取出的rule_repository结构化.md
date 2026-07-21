# 代码节点出入参说明：将 ADP 提取出的 ruleRepository 结构化

对应代码：`代码-将ADP提取出的rule_repository结构化.py`

## 节点职责

将上一 LLM 节点输出的临时规则库转成后续审核流程可使用的标准结构：

- 校验 `ruleRepository`、提取项和 `logicTopology`；
- 将 `R001` 等临时标识转换为正式五位 `ruleCode`；
- 生成八位 `keywordCode`；
- 将逻辑树中的规则引用同步改为正式 `ruleCode`。

代码节点不理解具体病种医学规则，不创建规则、不推断 AND/OR 关系；语义拆解只能由上游 LLM 完成。

## 入参

| 字段 | 类型 | 必填 | 腾讯平台绑定 |
| --- | --- | --- | --- |
| `llm_output` | `obj` 或 `str` | 是 | LLM 节点的完整 `Output`。推荐选 `obj`；也兼容 JSON 文本或 Markdown JSON 代码块。 |
| `chronicDiseaseCode` | `str` | 是 | 备案病种提取节点的 `chronicDiseaseCode`。必须以两位数字结尾。 |
| `logicTopology` | `obj` 或 `str` | 否 | 仅在 LLM 规则库与逻辑树分开绑定时使用；正常情况不用配置。 |

推荐配置：

```text
llm_output = 将检索结果转为 ruleRepository LLM.Output
类型 = obj

chronicDiseaseCode = 根据 certification_list 获取备案病种.chronicDiseaseCode
类型 = str
```

### `llm_output` 最小层级

```text
llm_output: Object
  ruleRepository: Array
    - item: Object
        tempRuleId: String，例如 R001
        ruleContent: String
        ruleKeywordGuide: Array<Object>，至少 1 项
  logicTopology: Object
    type: GROUP 或 RULE_REF
```

## 出参

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ruleRepository` | `[obj]` | 标准规则库，规则已带正式 `ruleCode`，提取项已带 `keywordCode`。 |
| `logicTopology` | `obj` | 已把临时规则引用替换为正式 `ruleCode` 的 AND / OR 树。 |

腾讯平台输出 Schema：

```text
ruleRepository: [obj]
  ruleCode: str
  ruleContent: str
  ruleSource: str
  experience: str
  ruleKeywordGuide: [obj]
    keywordCode: str
    dataType: str
    required: bool
    keywordContent: str
    enumOptions: [str]
  sourceRuleContent: str
  sourceMdFile: str
  sourceSection: str
logicTopology: obj
```

## 编码规则

规则编码由 `chronicDiseaseCode` 的末两位数字和三位顺序号组成：

```text
M07801
  R001 -> ruleCode 01001
  R002 -> ruleCode 01002

01001
  第 1 个提取项 -> keywordCode 01001001
  第 2 个提取项 -> keywordCode 01001002
```

这是可跨病种复用的稳定五位编码规则。知识库 DOC 不含既有业务系统编码时，本节点不会臆测或复刻某个病种的历史分支编码。

## 可直接粘贴测试的入参

```json
{
  "llm_output": {
    "ruleRepository": [
      {
        "tempRuleId": "R001",
        "ruleContent": "需长期透析治疗",
        "ruleSource": "八类疾病准入条件及细则-20260517.xlsx",
        "experience": "",
        "sourceRuleContent": "1.需长期透析治疗。\n2.有二级及以上医疗机构出具的病历资料。",
        "sourceMdFile": "尿毒症透析-认定标准-v20260517.md",
        "sourceSection": "认定标准",
        "ruleKeywordGuide": [
          {
            "dataType": "enum",
            "required": true,
            "keywordContent": "判断材料中是否明确需要或已经接受长期透析治疗；仅一次临时透析不得判肯定；优先查看透析记录、医嘱和出院记录。",
            "enumOptions": ["是", "否", "无法判断"]
          }
        ]
      },
      {
        "tempRuleId": "R002",
        "ruleContent": "有二级及以上医疗机构出具的病历资料",
        "ruleKeywordGuide": [
          {
            "dataType": "enum",
            "required": true,
            "keywordContent": "判断病历资料出具机构是否为二级及以上；仅有机构名称但无法确认等级时不得判肯定；优先查看医院等级字段和病历首页。",
            "enumOptions": ["二级及以上", "二级以下", "无法判断"]
          }
        ]
      }
    ],
    "logicTopology": {
      "type": "GROUP",
      "operator": "AND",
      "children": [
        {"type": "RULE_REF", "ruleCode": "R001"},
        {"type": "RULE_REF", "ruleCode": "R002"}
      ]
    }
  },
  "chronicDiseaseCode": "M07801"
}
```

## 对应出参示例

```json
{
  "ruleRepository": [
    {
      "ruleCode": "01001",
      "ruleContent": "需长期透析治疗",
      "ruleSource": "八类疾病准入条件及细则-20260517.xlsx",
      "experience": "",
      "ruleKeywordGuide": [
        {
          "keywordCode": "01001001",
          "dataType": "enum",
          "required": true,
          "keywordContent": "判断材料中是否明确需要或已经接受长期透析治疗；仅一次临时透析不得判肯定；优先查看透析记录、医嘱和出院记录。",
          "enumOptions": ["是", "否", "无法判断"]
        }
      ],
      "sourceRuleContent": "1.需长期透析治疗。\n2.有二级及以上医疗机构出具的病历资料。",
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

## 错误与联调定位

| 现象 | 原因与处理 |
| --- | --- |
| `llm_output 中缺少 logicTopology` | LLM 未输出完整对象，检查结构化 Schema 和绑定是否引用完整 Output。 |
| `chronicDiseaseCode 必须以两位数字结尾` | 上游备案病种编码不符合编码规则，不能生成五位规则码。 |
| `ruleRepository 至少包含一条规则` | LLM 没有从 DOC 生成规则，检查是否把 `knowledge_result` 插入提示词。 |
| `enum 提取项必须包含非空 enumOptions` | LLM 为 enum 漏了选项；修正 LLM 输出，不要改代码节点兜底。 |
| `logicTopology 引用了不存在的规则` | `RULE_REF.ruleCode` 不是某个 `tempRuleId`，或临时标识重复/拼写不一致。 |
| `logicTopology 未引用规则` | 规则库与逻辑树不一致；每条规则必须在树中恰好被使用。 |
