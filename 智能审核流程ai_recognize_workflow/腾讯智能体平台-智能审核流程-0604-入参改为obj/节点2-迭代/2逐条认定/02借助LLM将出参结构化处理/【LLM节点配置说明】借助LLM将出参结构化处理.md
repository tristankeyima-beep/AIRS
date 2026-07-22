# LLM 节点配置说明：借助 LLM 将出参结构化处理（逐条认定）

## 这个节点放在哪里

```text
01 通过LLM逐条认定（本地模型原始出参）
  -> 02 借助LLM将出参结构化处理（本节点，Qwen2.5）
  -> 03 单条标准审核结果结构化（既有代码节点）
  -> 04 提取推理过程（既有代码节点）
```

01 节点负责业务判断；本节点只将其文本或非规范 JSON 出参清洗为腾讯 ADP 可解析的审核结论对象。03 代码节点继续保留，用于容错解析、规则字段兜底和把单条结论封装为 `ruleResult` 数组。

本节点不得根据自身判断改变上游已经表达的“通过/不通过”结论，也不得新增材料或证据。

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
| `raw_llm_output` | 引用 | `str` | `01通过LLM逐条认定.Output` |

通过变量选择器绑定 01 节点的完整 `Output`。不要只绑定 `ruleResult`、`suspicionList` 等子字段，否则会丢失需要清洗的规则编码、规则内容或证据层级。

## 三、结构化输出变量格式

在本节点的“输出格式/结构化输出”中配置以下层级。为保证后续代码节点的输入稳定，`suspicionList` 始终配置为数组；通过时输出空数组。

```text
Output: Object
  ruleCode: str
  ruleResult: str
  ruleContent: str
  suspicionList: [obj]
    - suspicionType: str
    - detail: str
    - sources: [obj]
      - materialName: str
      - materialId: str
      - refContent: str
```

字段规则：

- `ruleResult` 只能为 `通过` 或 `不通过`。
- `ruleCode`、`ruleContent` 必须优先保留上游结果；上游未提供时输出空字符串，由 03 代码节点通过 `开始.iterator_selector` 兜底。
- 不通过且有疑点时，`suspicionList` 输出一个或多个疑点对象。
- 通过时 `suspicionList` 输出 `[]`。
- `sources` 始终为数组；没有可引用的材料时输出 `[]`，禁止补造材料名称、材料 ID 或原文。
- `refContent` 仅来自上游结果中的原始证据、`rawText` 或 `refContent`；缺失时为空字符串。

## 四、可直接使用的提示词

把下列 `raw_llm_output` 位置替换为腾讯 ADP 变量选择器插入的变量标签。

```text
# 任务
将“逐条认定 LLM 原始出参”清洗为规定的 JSON 结构。你只做格式化与字段映射，不重新审核，不改变原始出参已经表达的通过/不通过结论，不增加任何材料、事实或证据。

# 逐条认定 LLM 原始出参
{{raw_llm_output}}

# 清洗规则
1. 原始出参可能是 JSON 对象、带 Markdown 代码块的 JSON，或夹带说明文字的 JSON；只提取其中可被原始出参支持的数据。
2. 最外层必须输出 JSON 对象，且必须包含 ruleCode、ruleResult、ruleContent、suspicionList。
3. ruleResult 只能输出“通过”或“不通过”。原始出参明确表达结论时，必须原样保留。
4. 通过时 suspicionList 必须输出 []。
5. 不通过时，逐条映射原始出参中的 suspicionType、detail 和 sources。sources 必须为数组；证据缺失时输出 []，不能编造证据。
6. sources 中每项必须有 materialName、materialId、refContent；原始出参未提供的字段输出空字符串。
7. 原始出参无法识别有效结论时，输出“不通过”及一个“信息缺失”疑点：detail 为“上游逐条认定结果无法解析，无法形成有效审核结论。”，sources 为 []；ruleCode 和 ruleContent 输出空字符串，由下游代码节点兜底。
8. 只输出 JSON 对象本身；不要输出 Markdown、解释、前后缀或思考过程。

# 输出示例
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

## 五、完整 JSON 案例

### 案例 1：不通过，有明确证据

这是腾讯 ADP 应解析出的完整 `Output` 对象：

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

### 案例 2：通过

```json
{
  "ruleCode": "1002001",
  "ruleResult": "通过",
  "ruleContent": "二型糖尿病确诊",
  "suspicionList": []
}
```

### 案例 3：上游结论无法解析

```json
{
  "ruleCode": "",
  "ruleResult": "不通过",
  "ruleContent": "",
  "suspicionList": [
    {
      "suspicionType": "信息缺失",
      "detail": "上游逐条认定结果无法解析，无法形成有效审核结论。",
      "sources": []
    }
  ]
}
```

## 六、下游 03 代码节点怎么绑定

本节点成功后，`03单条标准审核结果结构化` 的入参按下列方式配置：

```text
变量名：ruleResult
数据来源：引用
绑定：02借助LLM将出参结构化处理.Output
类型：obj

变量名：items
数据来源：引用
绑定：开始.iterator_selector
类型：obj
```

`ruleResult` 必须绑定完整 `Output`，不要只选择其中的 `ruleResult` 字段，否则会丢失 `ruleCode`、`ruleContent` 或 `suspicionList`。`items` 必须保留，用于上游漏字段时的兜底。
