# LLM 节点配置说明：借助 LLM 将出参结构化处理（精解）

## 这个节点放在哪里

```text
01 使用LLM精解（按提取指令拆解病历材料，本地模型原始出参）
  -> 02 借助LLM将出参结构化处理（本节点，Qwen2.5）
  -> 03 精解结果结构化（既有代码节点）
```

省局内网本地模型不具备腾讯 ADP 的结构化出参能力时，01 节点只需正常输出文本或 JSON 文本。本节点使用支持结构化出参的 Qwen2.5，将其清洗成固定的 `extraction_data`，再交给既有代码节点排序和兼容处理。

本节点不重新精解病历、不补充材料事实，也不替代 03 代码节点。

## 一、模型与基础配置

| 配置项 | 值 |
| --- | --- |
| 节点名称 | `02借助LLM将出参结构化处理` |
| 模型 | 省局内已部署、支持结构化出参的 `qwen2.5` |
| 温度 | `0`；如平台不支持 `0`，设为可选最小值 |
| 结构化输出 | 开启 |
| 输出根对象 | `Output` |

## 二、输入变量

| 变量名称 | 数据来源 | 类型 | 腾讯 ADP 绑定 |
| --- | --- | --- | --- |
| `raw_llm_output` | 引用 | `str` | `01使用LLM精解（按提取指令拆解病历材料）.Output` |

必须通过腾讯平台的变量选择器插入上游完整 `Output`。不要手写变量名，也不要只绑定 `results`、`value` 等子字段，否则 Qwen 无法恢复完整层级。

## 三、结构化输出变量格式

在本节点的“输出格式/结构化输出”中配置以下层级。`extraction_data` 必须是根对象 `Output` 下的数组，不能直接把数组作为根出参。

```text
Output: Object
  extraction_data: [obj]
    - keywordCode: str
    - keywordContent: str
    - found: bool
    - results: [obj]
      - materialId: str
      - materialName: str
      - materialSource: str
      - rawText: str
      - value: str
```

字段规则：

- `keywordCode`：保留上游出参中的关键词编码；未提供时输出空字符串，不临时生成编码。
- `keywordContent`：保留上游提取项说明；未提供时输出空字符串。
- `found`：只能是 JSON 布尔值 `true` 或 `false`，不是字符串。
- `results`：始终为数组；`found=false` 时必须为 `[]`。
- `materialId`、`materialName`、`materialSource`、`rawText`、`value`：按上游内容原样清洗；字段缺失时输出空字符串，禁止根据常识补造。
- 一条结果的 `rawText` 为空时，保留空字符串；不要虚构原文证据。

## 四、可直接使用的提示词

把下列 `raw_llm_output` 位置替换为腾讯 ADP 变量选择器插入的变量标签。

```text
# 任务
将“精解 LLM 原始出参”清洗为规定的 JSON 结构。你只做格式化与字段映射，不重新分析病历，不补充任何原始出参中不存在的事实。

# 精解 LLM 原始出参
{{raw_llm_output}}

# 清洗规则
1. 原始出参可能是 JSON 对象、JSON 数组、带 Markdown 代码块的 JSON，或夹带说明文字的 JSON；只提取其中可被原始出参支持的数据。
2. 最外层必须输出 JSON 对象，且对象中必须有 extraction_data 数组。
3. extraction_data 的每项必须有 keywordCode、keywordContent、found、results。
4. found 只能输出 true 或 false；found=false 时 results 必须输出 []。
5. results 的每项必须有 materialId、materialName、materialSource、rawText、value；原始出参缺失的字段输出空字符串。
6. 保留原始出参表达的否定证据、数值、枚举值和材料信息；禁止根据医疗常识、规则要求或上下文推断补写。
7. 原始出参无法识别为有效精解结果时，输出 {"extraction_data": []}。
8. 只输出 JSON 对象本身；不要输出 Markdown、解释、前后缀或思考过程。

# 输出示例
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

## 五、完整 JSON 案例

### 案例 1：找到反向证据

这是腾讯 ADP 应解析出的完整 `Output` 对象：

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

### 案例 2：未找到证据

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

## 六、下游 03 代码节点怎么绑定

本节点成功后，`03精解结果结构化` 的入参按下列方式配置：

```text
变量名：extraction_data
数据来源：引用
绑定：02借助LLM将出参结构化处理.Output.extraction_data
类型：str
```

不要把 03 的 `extraction_data` 绑定到本节点完整 `Output`，也不要继续绑定 01 的 Output。03 代码节点会把 `extraction_data` 转为排序后的 `extractionList`，供“逐条认定”继续使用。
