# LLM 节点配置说明：逐条认定

参考 DIFY 提示词：

`DIFY工程-智能审核流程/节点3-迭代/2逐条认定/【prompt】根据精解结果逐条认定提示词V6`

## 本次要改的关键句

如果你已经在腾讯里配好了提示词，不用整篇重抄，重点检查并替换下面 4 处。

### 1. 变量必须用腾讯变量选择器插入

不要手写：

```text
{{ruleCode}}
{{ruleContent}}
{{experience}}
{{suspicion_type_options}}
{{text}}
```

要在对应位置用腾讯平台变量选择器插入：

```text
开始.iterator_selector.ruleCode
开始.iterator_selector.ruleContent
开始.iterator_selector.experience
开始.suspicion_type_options
精解结果结构化.extractionList
```

你这次测试里输出了 `"ruleCode": "ruleCode"`、`"ruleContent": "ruleContent"`，就是变量没有真正插入成功。

如果“逐条认定”的推理里说没有结构化审核证据，先检查上一个代码节点：

```text
精解结果结构化.extractionList
```

它不能是空数组。若为空，说明“精解结果结构化”没有拿到“1精解 LLM”的 Output。

### 2. 输出格式示例里不要手写变量占位符

把这种：

```json
{
  "ruleCode": "{{ruleCode}}",
  "ruleResult": "通过",
  "ruleContent": "{{ruleContent}}"
}
```

改成这种：

```json
{
  "ruleCode": "使用上方规则信息中的实际 ruleCode",
  "ruleResult": "通过",
  "ruleContent": "使用上方规则信息中的实际 ruleContent"
}
```

### 3. 再加一句防占位符要求

```text
禁止把变量名本身作为结果输出，例如禁止输出 "ruleCode": "ruleCode" 或 "ruleContent": "ruleContent"；必须输出上方规则信息中的实际值。
```

### 4. 明确 rawText 和 refContent 的关系

```text
结构化审核证据中的 rawText 是精解阶段提取的原始证据片段；只有在输出不通过结论时，才把 rawText 摘录到 suspicionList.sources[].refContent。不要要求结构化审核证据里自带 refContent。
```

## 一、输入变量怎么配

腾讯平台这个 LLM 节点建议配置 5 个输入变量。

| 变量名称 | 数据来源 | 类型 | 推荐绑定 |
| --- | --- | --- | --- |
| `suspicion_type_options` | 引用 | str | `开始.suspicion_type_options` |
| `text` | 引用 | obj 或 [obj] | 上一个“精解结果结构化”代码节点的 `extractionList` |
| `ruleCode` | 引用 | str | `开始.iterator_selector.ruleCode` |
| `ruleContent` | 引用 | str | `开始.iterator_selector.ruleContent` |
| `experience` | 引用 | str | `开始.iterator_selector.experience` |

截图里 `suspicion_type_op` 看起来像被截断了，建议完整变量名写成：

```text
suspicion_type_options
```

## 二、每个变量是什么意思

```text
suspicion_type_options: String
  例如：指标异常;信息缺失;资质不符;临床表现不足;材料不全

text: Array<Object>
  来自精解结果结构化节点的 extractionList
  是这条规则的结构化审核证据

ruleCode: String
  当前规则编码

ruleContent: String
  当前规则原文

experience: String
  当前规则的经验判断补充，没有就为空字符串
```

## 三、推荐提示词正文

把下面这段放到腾讯 LLM 节点的提示词里。变量位置用腾讯平台右侧变量选择器插入，不建议纯手打变量占位符。

```text
# 任务
你需要根据“结构化审核证据”判断该规则是否通过。

# 判定依据
- 以“结构化审核证据”中的 found、results、value、rawText 作为判定依据。
- 当 value 已经落在当前关键词的 enumOptions 中时，优先按 value 判断，保持规则原意和选项口径一致。
- found=false 或 results 为空时，按证据不足处理。
- 结构化审核证据中的 rawText 是精解阶段提取的原始证据片段。
- 只有在输出不通过结论时，才把 rawText 摘录到 suspicionList.sources[].refContent。
- 不要要求结构化审核证据里自带 refContent。
- suspicionList.detail 使用面向审核人员的表述，避免出现“精解结果”“关键词”“value”等内部流程词。
- suspicionList.detail 中描述的具体事实，必须能在 sources.refContent 中直接找到对应表述；不要引用 keywordContent 示例词或未进入 sources 的材料事实。
- 如果 results 中 rawText 为空，但 value 表示不符合规则，可以判定不通过；此时 sources.refContent 用空字符串，detail 只描述 value 能支持的事实。

# 规则信息
- ruleCode: 【在这里用腾讯变量选择器插入：开始.iterator_selector.ruleCode】
- ruleContent: 【在这里用腾讯变量选择器插入：开始.iterator_selector.ruleContent】
- experience: 【在这里用腾讯变量选择器插入：开始.iterator_selector.experience】


# 异常类型选项

【在这里用腾讯变量选择器插入：开始.suspicion_type_options】


# 结构化审核证据

【在这里用腾讯变量选择器插入：精解结果结构化.extractionList】


# 输出要求
- 输出一个合法 JSON 对象。
- 直接输出 JSON 对象本身，不要输出 Markdown，不要输出解释文字。
- JSON 中保留 ruleCode、ruleResult、ruleContent。
- 不通过时补充 suspicionList。

# 输出格式

通过时：
{
  "ruleCode": "使用上方规则信息中的实际 ruleCode",
  "ruleResult": "通过",
  "ruleContent": "使用上方规则信息中的实际 ruleContent"
}

不通过时：
{
  "ruleCode": "使用上方规则信息中的实际 ruleCode",
  "ruleResult": "不通过",
  "ruleContent": "使用上方规则信息中的实际 ruleContent",
  "suspicionList": [
    {
      "suspicionType": "从异常类型选项中选择；无合适项则用“其他异常”",
      "detail": "仅描述一个不通过点，并说明其与规则不符之处",
      "sources": [
        {
          "materialName": "来自 results.materialName",
          "materialId": "来自 results.materialId",
          "refContent": "来自 results.rawText"
        }
      ]
    }
  ]
}

证据缺失时：
{
  "ruleCode": "使用上方规则信息中的实际 ruleCode",
  "ruleResult": "不通过",
  "ruleContent": "使用上方规则信息中的实际 ruleContent",
  "suspicionList": [
    {
      "suspicionType": "信息缺失",
      "detail": "现有审核材料中未见满足该规则要求的有效证据。",
      "sources": []
    }
  ]
}

现在直接输出 JSON 对象：

```

## 四、腾讯平台里变量插入的注意点

上面正文里的：

```text
{{ruleCode}}
{{ruleContent}}
{{experience}}
{{suspicion_type_options}}
{{text}}
```

在腾讯平台里最好用变量选择器插入成平台自己的变量 token。不要直接复制 DIFY 里的这种写法：

```text
{{#1767236686721.item#}}
{{items.ruleCode}}
{{#1767236864578.text#}}
```

因为这些是 DIFY 节点 ID 写法，腾讯平台不能直接识别。

如果测试结果里出现：

```json
{
  "ruleCode": "ruleCode",
  "ruleContent": "ruleContent"
}
```

或者推理过程里说“规则信息、结构化审核证据是占位符”，说明提示词里的变量没有真正绑定成功。处理方式：

1. 删除提示词中手写的 `{{ruleCode}}`、`{{ruleContent}}`、`{{text}}` 等字样。
2. 在这些位置用腾讯平台的变量选择器重新插入变量。
3. 插入后界面里应该显示成变量标签，而不是普通文本。

建议在输出格式示例里也不要手写变量名，直接告诉模型“使用上方规则信息中的实际 ruleCode 和 ruleContent”。如果平台变量替换不稳定，可以把输出格式改成下面这种：

```text
通过时：
{
  "ruleCode": "使用上方规则信息中的实际 ruleCode",
  "ruleResult": "通过",
  "ruleContent": "使用上方规则信息中的实际 ruleContent"
}
```

## 六、LLM 输出后接哪个节点

这个 LLM 节点输出的是一段 JSON 文本，后面接：

```text
单条标准审核结果结构化.py
```

它的入参建议这样配：

```text
ruleResult = 逐条认定 LLM 节点输出文本
items = 开始.iterator_selector
```

这样即使模型漏了 `ruleCode` 或 `ruleContent`，结构化代码节点也能用 `items` 兜底补上。

## 七、LLM 节点输出示例

### 示例 1：通过

```json
{
  "ruleCode": "1002001",
  "ruleResult": "通过",
  "ruleContent": "二型糖尿病确诊"
}
```

### 示例 2：不通过，有明确证据

```json
{
  "ruleCode": "1002001",
  "ruleResult": "不通过",
  "ruleContent": "二型糖尿病确诊",
  "suspicionList": [
    {
      "suspicionType": "指标异常",
      "detail": "材料记载患者无糖尿病史，不符合二型糖尿病确诊要求。",
      "sources": [
        {
          "materialName": "住院病案首页",
          "materialId": "2018496043368521728",
          "refContent": "无糖尿病史。"
        }
      ]
    }
  ]
}
```

### 示例 3：不通过，证据缺失

```json
{
  "ruleCode": "1002001",
  "ruleResult": "不通过",
  "ruleContent": "二型糖尿病确诊",
  "suspicionList": [
    {
      "suspicionType": "信息缺失",
      "detail": "现有审核材料中未见满足该规则要求的有效证据。",
      "sources": []
    }
  ]
}
```

注意：这个 LLM 节点只输出 JSON 对象本身，不要输出 Markdown 代码块，不要在 JSON 前后加解释文字。

## 八、联调踩坑记录

1. `text` 必须绑定 `精解结果结构化.extractionList`。
   如果 reasoningContent 里出现“没有提供结构化审核证据”或把 `text` 当普通文字，说明变量没有插入成功。

2. 规则字段必须用变量选择器插入。
   不要在提示词正文里直接写 `ruleCode`、`ruleContent`、`experience`，否则模型可能输出 `"ruleCode": "ruleCode"`。

3. 逐条认定阶段负责 `rawText -> refContent`。
   输入证据看 `extractionList.results[].rawText`；输出不通过时写到 `suspicionList.sources[].refContent`。

4. 不通过时必须输出 `suspicionList`。
   如果后续合并节点里没有不通过原因，先检查逐条认定 LLM 输出 schema 是否包含 `suspicionList`，且类型为 `[obj]`。
