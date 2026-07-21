# ADP 检索结果转 ruleRepository 设计

## 目标

将 ADP 知识库检索结果中的 DOC 正文转换为可被现有审核流程消费的 `ruleRepository` 和 `logicTopology`。患者材料审核不在本次范围内。

## 数据来源与范围

输入是 ADP 检索节点输出对象，正文位于 `KnowledgeList[].Content`。LLM 仅使用 `KnowledgeType=DOC` 的条目；若有多条 DOC，按内容去重后合并阅读。QA 条目一律忽略。

DOC 中“准入条件”定义规则条目，“提取项细则”定义这些规则的证据提取要求：

- 每一条准入条件生成一条 `ruleRepository` 规则。
- 复合准入条件拆成多个原子 `ruleKeywordGuide` 项，但不拆成多条规则。
- 提取项细则必须按语义归入对应准入条件，用于补足指标、症状、材料来源、阈值或证据范围。
- 细则不能脱离准入条件单独生成规则。
- 同时识别“以下条件之一”“同时符合”“未经住院治疗的”等逻辑连接词，输出嵌套的 AND / OR `logicTopology`；树中每个叶子只引用已生成的规则。

例如，尿毒症透析的“慢性肾脏损伤，并出现肾功能异常达到尿毒症期”是一条规则，拆为“慢性肾脏损伤”和“达到尿毒症期”两个提取项；“需长期透析治疗”和“二级及以上医疗机构出具病历资料”分别是另外两条规则。

## 节点职责

### LLM 节点

输入：

- `knowledge_result`：ADP 检索结果对象。
- `chronicDiseaseName`：备案病种名称。
- `chronicDiseaseCode`：备案病种编码。

输出 `Output.ruleRepository` 和 `Output.logicTopology`。LLM 负责读 DOC、拆准入条件、关联提取项细则，并输出：

- `ruleContent`
- `ruleSource`
- `experience`
- `sourceRuleContent`
- `sourceMdFile`
- `sourceSection`
- `ruleKeywordGuide[]`，其中每项有 `dataType`、`required`、`keywordContent`、`enumOptions`
- `logicTopology`，其中 `RULE_REF.ruleCode` 先使用稳定临时标识 `R001`、`R002`……引用对应规则

LLM 不生成正式 `ruleCode` 与 `keywordCode`，避免模型造成编码重复、跳号或格式不一致。临时标识只用于 LLM 输出内的规则与逻辑树关联。

### 后置代码节点

输入：

- `llm_output`：LLM 的结构化对象或 JSON 文本。
- `chronicDiseaseCode`：备案病种编码。

代码负责拆开腾讯 `Output` 外层、校验 LLM 输出、补默认字段、分配确定性编码并排序，同时将 `logicTopology` 中的临时标识重写为正式规则编码。输出为 `ruleRepository` 和 `logicTopology`。

规则编码取 `chronicDiseaseCode` 的末两位数字并拼接三位序号：`M07801` 的第一条规则为 `01001`。每条规则的第一个提取项编码为 `01001001`，后续提取项按三位序号递增。这个规则生成的是通用、稳定的五位编码；检索 DOC 不含既有系统编码时，不尝试复刻特定病种的历史分支前缀。病种编码不以两位数字结尾、规则数或单规则提取项数超过 999、规则或提取项字段不合规则、逻辑树引用不存在的临时标识或正式编码时必须抛出错误，阻止不完整规则库进入下游。

## 输出协议

```json
{
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
          "keywordContent": "……",
          "enumOptions": ["是", "否", "无法判断"]
        }
      ],
      "sourceRuleContent": "1.…\n2.…\n3.…",
      "sourceMdFile": "尿毒症透析-认定标准-v20260517.md",
      "sourceSection": "认定标准"
    }
  ],
  "logicTopology": {
    "type": "GROUP",
    "operator": "AND",
    "children": [
      {"type": "RULE_REF", "ruleCode": "01001"}
    ]
  }
}
```

## 文件交付与验证

在 `对接ADP知识库/将检索结果转为rule_repository/` 新增：

- `代码-将ADP提取出的rule_repository结构化.py`
- `【代码出入参说明】代码-将ADP提取出的rule_repository结构化.md`
- `【LLM节点配置说明】将检索结果转为rule_repository.md`

验证以 `output.json` 中尿毒症透析 DOC 为例：规则库必须输出三条规则、编码依次为 `01001`、`01002`、`01003`；逻辑树为引用三条规则的 AND 组；每个规则至少有一个提取项；所有枚举提取项有非空 `enumOptions`；JSON 文本与腾讯结构化对象都可被代码节点解析。
