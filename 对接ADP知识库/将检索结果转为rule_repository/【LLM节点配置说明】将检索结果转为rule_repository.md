# LLM 节点配置说明：将检索结果转为 ruleRepository

## 节点职责

将 ADP 知识库检索结果中的 DOC 正文拆解为：

- `ruleRepository`：认定规则及其材料提取要求；
- `logicTopology`：规则间的 AND / OR 逻辑树。

本节点是全病种通用节点。它不判断患者是否符合条件，不输出患者材料证据，也不生成正式的 `ruleCode`、`keywordCode`；这些编码由后置代码节点统一生成。

## 输入变量

| 变量 | 类型 | 绑定来源 | 说明 |
| --- | --- | --- | --- |
| `knowledgeContent` | `str` | “提取相关性最高的知识库结果”代码节点 `knowledgeContent` | 相关性最高 DOC 的完整正文。 |
| `chronicDiseaseName` | `str` | 备案病种提取节点 `chronicDiseaseName` | 病种语境与检索结果校验依据。 |
| `chronicDiseaseCode` | `str` | 备案病种提取节点 `chronicDiseaseCode` | 供模型核对病种；正式编码由后置代码节点生成。 |

变量位置请用腾讯平台的变量选择器插入，不要手写 DIFY 风格占位符。

## 腾讯结构化输出 Schema

```text
Output: obj
  ruleRepository: [obj]
    tempRuleId: str
    ruleContent: str
    ruleSource: str
    experience: str
    sourceRuleContent: str
    sourceMdFile: str
    sourceSection: str
    ruleKeywordGuide: [obj]
      dataType: str
      required: bool
      keywordContent: str
      enumOptions: [str]
  logicTopology: obj
    type: str
    operator: str
    children: [obj]
    ruleCode: str
```

`logicTopology` 是递归对象。若腾讯平台 Schema 无法完整描述深层 `children`，仍让 LLM 输出完整 JSON 对象，并把后置代码节点 `llm_output` 绑定到 LLM 的原始 Output；代码节点会自行解析完整树。

## 推荐提示词正文

```text
# 角色
你是医保慢特病认定标准结构化专家。

# 任务
根据已筛选的知识库 DOC 正文，为当前备案病种生成认定规则库 ruleRepository 和规则逻辑树 logicTopology。

当前备案病种名称：
【用腾讯变量选择器插入 chronicDiseaseName】

当前备案病种编码：
【用腾讯变量选择器插入 chronicDiseaseCode】

已筛选的知识库 DOC 正文：
【用腾讯变量选择器插入 knowledgeContent】

# 知识范围
1. 只能使用上方已筛选的知识库 DOC 正文；不要使用病种名称、病种编码或医学常识补充正文没有的规则。
2. 如果 DOC 与当前备案病种明显不一致，不能借用其内容补充规则。
3. DOC 可能把多条编号条件压缩在同一段文字中；必须按编号、分号、连接词和语义正确拆分，不能因排版压缩漏掉规则。

# 规则拆解
1. 只有“准入条件、限、应符合、需提供、经确认、首次申请、支付限制”等直接决定认定或用药资格的条件，才能生成规则。
2. 每条独立准入条件生成一条 ruleRepository 规则；ruleContent 保留原意，不擅自增加、删除或改变阈值。
3. 一条复合准入条件仍是一条规则，但要把其原子事实拆为多个 ruleKeywordGuide：例如疾病确诊与机构等级、诊断与分期、治疗与时间、检查与阈值必须拆开。
4. “提取项细则”只能用于补强语义对应规则的证据口径、材料来源、指标阈值或排除边界；细则本身不得单独新建规则。
5. 如果一条细则无法与任何准入条件直接对应，不得把它变成规则；宁可不使用，也不能基于医学常识猜测其归属。
6. 不得根据病种名称、疾病常识、药物适应症或提示词示例补造规则。

# 提取项要求
1. 每个规则至少有一条 ruleKeywordGuide；每条提取项只验证一个原子事实。
2. dataType 只能为 enum 或 string。
3. enum 用于是否存在、是否确诊、是否达标、机构等级、是否超限等判断，enumOptions 必须是非空数组。
4. string 用于明确诊断名称、检查数值、日期、治疗名称等原始信息，enumOptions 必须为 []。
5. keywordContent 必须写清肯定证据、不能判肯定的边界，以及优先材料位置；后续材料精解的原文证据必须能够直接支撑提取值。
6. required 必须是布尔值。对规则成立必需的事实填 true；明确为辅助信息时才可填 false。

# 逻辑树要求
1. “以下条件之一、任一、或、未经住院治疗的……门诊路径”等表示 OR。
2. “同时符合、且、并、以及、需同时提供”等表示 AND。
3. 当一条路径是“适应症之一 + 多项共同条件”时，必须输出嵌套结构：AND 内含一个 OR 适应症组和多个共同条件。
4. 每条规则按出现顺序生成临时标识 tempRuleId：R001、R002、R003……。
5. logicTopology 的 RULE_REF.ruleCode 只能引用对应的临时标识，不能输出正式 ruleCode 或其他文字。
6. 每条规则必须且只能被 logicTopology 引用一次；树的每个 GROUP 都必须有 operator=AND 或 OR，且 children 非空。

# 来源字段
1. ruleSource 提取 DOC 中明确的来源文件或政策来源；未出现时填“ADP知识库检索结果”。
2. experience 固定填空字符串，除非 DOC 明确给出了可复用的审核经验规则。
3. sourceRuleContent 保留该 DOC 的完整准入条件原文。
4. sourceMdFile 提取 DOC 的文档名；没有时填空字符串。
5. sourceSection 填规则所属章节，如“认定标准”；没有章节时填空字符串。

# 输出要求
只输出 JSON 对象，不要 Markdown、解释、代码块、思考过程或患者审核结论。
最外层只能包含 ruleRepository 和 logicTopology。
不要输出 ruleCode、keywordCode、患者材料、最终通过/不通过结论。

{
  "ruleRepository": [
    {
      "tempRuleId": "R001",
      "ruleContent": "规则原文",
      "ruleSource": "来源",
      "experience": "",
      "sourceRuleContent": "完整准入条件原文",
      "sourceMdFile": "文档名",
      "sourceSection": "认定标准",
      "ruleKeywordGuide": [
        {
          "dataType": "enum",
          "required": true,
          "keywordContent": "提取任务，包含肯定证据、排除边界与优先材料位置",
          "enumOptions": ["是", "否", "无法判断"]
        }
      ]
    }
  ],
  "logicTopology": {
    "type": "GROUP",
    "operator": "AND",
    "children": [
      {"type": "RULE_REF", "ruleCode": "R001"}
    ]
  }
}
```

## 跨病种拆解边界

- 一个复合准入条件可有多个提取项，但仍是一条规则。例如“明确诊断并达到某分期”应拆为“诊断”和“分期”两个提取项。
- “符合以下条件之一”对应 OR 分组；“应同时符合以下条件”对应 AND 分组。出现多条并列路径时，必须保留嵌套层级。
- 不要把检查指标、症状、并发症或材料类型细则机械地逐条转成规则；它们只有在直接支撑某条准入条件时才写入其 `ruleKeywordGuide`。

## 后续节点绑定

后面接“代码-将ADP提取出的rule_repository结构化”节点：

```text
llm_output = 本 LLM 节点 Output，类型 obj
chronicDiseaseCode = 备案病种提取节点 chronicDiseaseCode，类型 str
```
