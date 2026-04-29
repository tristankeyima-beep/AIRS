# LLM 节点配置说明：1精解

参考 DIFY 提示词：

`DIFY工程-智能审核流程/节点3-迭代/1精解/【prompt】材料精解V6`

## 本次要改的关键句

如果你已经在腾讯里配好了提示词，不用整篇重抄，重点检查并替换下面 4 处。

### 1. 变量必须用腾讯变量选择器插入

不要手写：

```text
{{ruleCode}}
{{ruleContent}}
{{ruleKeywordGuide}}
{{material_list}}
```

要在对应位置用腾讯平台变量选择器插入：

```text
开始.iterator_selector.ruleCode
开始.iterator_selector.ruleContent
开始.iterator_selector.ruleKeywordGuide
开始.material_list
```

### 2. `materialSource` 这句要改成下面这样

```text
results[].materialSource 必须优先取材料对象里的 sourceHospital；如果 sourceHospital 为空或不存在，则必须取材料对象里的 materialSource；两者都没有时，才允许输出空字符串。
```

### 3. `rawText` 这句要改成下面这样

```text
rawText 不允许为空。优先取 materialContent 中的原文片段；若依据的是结构化字段，可使用标准化证据串。
```

你这次测试里 `materialSource` 和 `rawText` 为空，主要就是第 2、3 句需要补强。

### 4. 输出格式必须从“数组”改成“对象包数组”

腾讯结构化输出 schema 里最外层是 `Output` 对象，里面有 `extraction_data` 数组，所以提示词不能再写“只输出 JSON 数组”。

把旧句子：

```text
只输出 JSON 数组
```

改成：

```text
只输出 JSON 对象，对象里必须包含 extraction_data 数组
```

## 一、输入变量怎么配

腾讯平台这个 LLM 节点建议配置 4 个输入变量。

| 变量名称 | 数据来源 | 类型 | 推荐绑定 |
| --- | --- | --- | --- |
| `ruleCode` | 引用 | str | `开始.iterator_selector.ruleCode` |
| `ruleKeywordGuide` | 引用 | obj 或 [obj] | `开始.iterator_selector.ruleKeywordGuide` |
| `material_list` | 引用 | str | `开始.material_list` |
| `ruleContent` | 引用 | str | `开始.iterator_selector.ruleContent` |

说明：

- `ruleKeywordGuide` 如果腾讯平台允许选 `[obj]`，优先选 `[obj]`。
- 如果平台只能选 `obj`，也可以先选 `obj`，核心是绑定到 `开始.iterator_selector.ruleKeywordGuide`。
- `ruleContent` 不是精解必需字段，但建议放进提示词，能让模型理解这条规则在审核什么。

## 二、每个变量是什么意思

```text
ruleCode: String
  当前规则编码，例如 1002001

ruleContent: String
  当前规则原文，例如 二型糖尿病确诊

ruleKeywordGuide: Array<Object>
  当前规则需要提取的字段列表

material_list: String
  患者材料列表 JSON 字符串
```

## 三、推荐提示词正文

把下面这段放到腾讯 LLM 节点的提示词里。变量位置建议用腾讯平台右侧变量选择器插入，不建议手打占位符。

```text
# 任务
根据 ruleKeywordGuide 的要求，从 material_list 中提取结构化结果。

# 当前规则
- ruleCode: {{ruleCode}}
- ruleContent: {{ruleContent}}

# 提取项要求
{{ruleKeywordGuide}}

# 患者材料
{{material_list}}

# 证据范围
可用于提取和判断的证据，既包括材料正文，也包括材料结构化字段：
- materialContent
- materialName
- materialType
- sourceHospital
- hospitalLevel
- reportDate
- uploadTime

# 提取原则
1. 只能依据输入材料中已有信息提取，禁止使用常识补全、推测或改写原意。
2. 每个 ruleKeywordGuide 项都必须输出一个结果对象。
3. 若 dataType=enum，value 必须严格从 enumOptions 中选择。
4. 找到明确否定、排除、未见、否认、未诊断等反向证据时，仍视为已找到相关证据：
   - found=true
   - results 正常返回
   - value 取最匹配的枚举值
5. 只有完全找不到相关证据时，才返回：
   - found=false
   - results=[]

# 结构化字段取证规则
1. 若规则涉及医院级别、医疗机构资质、材料来源、报告时间等信息，优先使用结构化字段判断，不要求必须在 materialContent 中命中。
2. 若证据来自结构化字段，允许 rawText 使用标准化证据串，格式如下：
   - sourceHospital=泰安市中心医院；hospitalLevel=三级
   - materialName=住院病历-1；reportDate=2025-12-26 00:00:00
3. 若正文和结构化字段均可支持，优先返回更直接、更稳定的证据。

# 结果字段要求
results 中每条结果必须包含以下字段：
- materialId
- materialName
- materialSource
- rawText
- value

字段取值规则：
- materialSource：优先取材料对象的 sourceHospital；没有 sourceHospital 时取 materialSource；两者都没有才输出空字符串。
- rawText：不允许为空。优先取 materialContent 中的原文片段；如果证据来自结构化字段，可使用标准化证据串。
- value：必须能被 rawText 或对应结构化字段直接支持。

# keywordCode 规则
1. 若当前 ruleKeywordGuide 中存在 keywordCode，必须原样输出。
2. 若不存在 keywordCode，使用稳定兜底编码：
   - 格式：{{ruleCode}}_01、{{ruleCode}}_02……
   - 按 ruleKeywordGuide 在输入中的顺序编号。
3. 禁止生成临时编码，如 kw1、kw2。
4. 禁止直接用 keywordContent 充当 keywordCode。

# 多结果规则
1. 同一字段命中多条证据时，全部返回。
2. 按时间新到旧排序；无法判断时间时按材料出现顺序返回。
3. 同一材料内多个命中片段可返回多条，也可合并为一条最有代表性的证据。

# 输出格式
只输出 JSON 对象，不要输出解释、Markdown、前后缀、思考过程或 <think>。
最外层必须是对象，并且必须包含 extraction_data 数组。

找到证据时：
{
  "extraction_data": [
    {
      "keywordCode": "关键词编码",
      "keywordContent": "提取项说明",
      "found": true,
      "results": [
        {
          "materialId": "材料ID",
          "materialName": "材料名称",
          "materialSource": "材料来源医院",
          "rawText": "原文证据片段或结构化字段证据串",
          "value": "规范化结果"
        }
      ]
    }
  ]
}

未找到证据时：
{
  "extraction_data": [
    {
      "keywordCode": "关键词编码",
      "keywordContent": "提取项说明",
      "found": false,
      "results": []
    }
  ]
}

现在请直接输出 JSON 对象结果：
```

## 四、腾讯平台里变量插入的注意点

上面正文里的：

```text
{{ruleCode}}
{{ruleContent}}
{{ruleKeywordGuide}}
{{material_list}}
```

在腾讯平台里最好用变量选择器插入成平台自己的变量 token。不要直接复制 DIFY 的写法：

```text
{{#1767236686721.item#}}
{{items.ruleKeywordGuide}}
{{#context#}}
```

这些是 DIFY 节点 ID 和变量写法，腾讯平台不能直接识别。

如果测试结果里出现这些现象，说明变量没有真正插入：

```json
{
  "ruleCode": "ruleCode",
  "ruleContent": "ruleContent"
}
```

或者 LLM 推理里说“这些内容是占位符”。这时要回到 LLM 节点提示词，把变量位置删除后，用腾讯平台的变量选择器重新插入变量 token。

## 五、LLM 节点输出示例

### 示例 1：找到明确证据

```json
{
  "extraction_data": [
    {
      "keywordCode": "1002001001",
      "keywordContent": "是否确诊为二型糖尿病",
      "found": true,
      "results": [
        {
          "materialId": "2018496043368521728",
          "materialName": "住院病案首页",
          "materialSource": "济南市医保局",
          "rawText": "无糖尿病史。",
          "value": "未确诊"
        }
      ]
    }
  ]
}
```

### 示例 2：找到反向证据

说明：反向证据也算找到了，所以 `found=true`。

```json
{
  "extraction_data": [
    {
      "keywordCode": "1002001001",
      "keywordContent": "是否确诊为二型糖尿病",
      "found": true,
      "results": [
        {
          "materialId": "2018496043368521728",
          "materialName": "住院病案首页",
          "materialSource": "济南市医保局",
          "rawText": "既往史：否认糖尿病史。",
          "value": "未确诊"
        }
      ]
    }
  ]
}
```

### 示例 3：完全找不到证据

```json
{
  "extraction_data": [
    {
      "keywordCode": "1002001001",
      "keywordContent": "是否确诊为二型糖尿病",
      "found": false,
      "results": []
    }
  ]
}
```

## 六、LLM 输出后接哪个节点

这个 LLM 节点输出的是 JSON 对象，里面包含 `extraction_data` 数组。后面接：

```text
代码-将精解结果结构化.py
```

它的入参建议这样配：

```text
extraction_data = 1精解 LLM 节点输出文本
```

在腾讯平台里具体就是：

```text
代码节点：代码-将精解结果结构化
变量名：extraction_data
数据来源：引用
绑定：1精解 LLM 节点的 Output.extraction_data
类型：[obj]
```

不要留空，也不要绑定到“开始.material_list”。这里必须绑定精解 LLM 的 `Output.extraction_data`。

结构化代码节点会把 LLM 输出解析成数组，并输出：

```json
{
  "extractionList": [
    {
      "keywordCode": "1002001001",
      "found": true,
      "results": []
    }
  ]
}
```

后面的“逐条认定”LLM 节点里，`text` 就绑定这个 `extractionList`。

## 七、联调踩坑记录

1. 腾讯结构化输出 schema 是对象包数组。
   如果 schema 里是 `Output.extraction_data: [obj]`，提示词就必须要求输出：

```json
{
  "extraction_data": []
}
```

不要再写“只输出 JSON 数组”，否则容易得到 `extraction_data: null`。

2. 原文精解 LLM 的输出字段里，精解证据必须叫 `rawText`。
   `refContent` 是后面审核结论引用证据用的字段，不要在精解阶段使用。

3. `rawText` 不应为空。
   如果材料中有 `materialContent`，必须摘取能支持 `value` 的原文片段；结构化字段取证时才使用标准化证据串。

4. `materialSource` 取值要简洁处理。
   优先取材料里的 `sourceHospital`，没有时取 `materialSource`，两者都没有才为空。

5. 变量必须用腾讯变量选择器插入。
   如果模型输出里出现 `ruleCode`、`ruleContent` 这类字面量，通常是提示词中手写了变量名，平台没有真正替换。
