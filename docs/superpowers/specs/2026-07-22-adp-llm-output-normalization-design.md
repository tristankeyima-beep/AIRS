# 腾讯 ADP 智能审核流程：LLM 出参结构化设计

## 目标

省局内网本地模型不能稳定按腾讯 ADP 的结构化 Output Schema 返回结果。为保持原有代码节点、聚合逻辑和下游变量契约不变，在两个业务 LLM 节点之后各增加一个使用 Qwen2.5 的“借助 LLM 将出参结构化处理”节点。

Qwen2.5 节点只负责把上游 LLM 的自然语言或非规范 JSON 输出清洗为约定 JSON；现有代码节点继续负责字段兜底、解析兼容、排序和数组封装。

## 范围与边界

修改范围限于：

- `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/1精解`
- `智能审核流程ai_recognize_workflow/腾讯智能体平台-智能审核流程-0604-入参改为obj/节点2-迭代/2逐条认定`

不修改既有 Python 代码、不改变节点 3 聚合、节点 4 输出 advice，也不修改原业务 LLM 的提示词和模型选择。

## 流程变更

### 精解分支

```text
01 使用 LLM 精解（本地模型原始输出）
  -> 02 借助 LLM 将出参结构化处理（Qwen2.5）
  -> 03 精解结果结构化（既有代码节点）
  -> 逐条认定
```

新节点的入参是上一节点的完整 Output 文本；其 ADP 结构化 Output 定义一个 `extraction_data` 数组。既有“精解结果结构化”代码节点绑定 `02...Output.extraction_data`，并仍输出 `extractionList`。

### 逐条认定分支

```text
01 通过 LLM 逐条认定（本地模型原始输出）
  -> 02 借助 LLM 将出参结构化处理（Qwen2.5）
  -> 03 单条标准审核结果结构化（既有代码节点）
  -> 提取推理过程
```

新节点的入参是上一节点的完整 Output 文本；其 ADP 结构化 Output 定义 `ruleCode`、`ruleResult`、`ruleContent` 与可选 `suspicionList`。既有“单条标准审核结果结构化”代码节点绑定该新节点的完整 `Output`，继续输出数组化的 `ruleResult`。

## 数据契约

### 精解结构化输出

`extraction_data` 类型为 `[obj]`。每项包含 `keywordCode`、`keywordContent`、`found` 和 `results`；`results` 类型为 `[obj]`，字段为 `materialId`、`materialName`、`materialSource`、`rawText`、`value`。无证据时仍保留提取项，令 `found=false` 且 `results=[]`。

完整示例：

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

### 逐条认定结构化输出

`ruleCode`、`ruleResult`、`ruleContent` 类型均为 `str`；`suspicionList` 类型为 `[obj]`，不通过时输出，包含 `suspicionType`、`detail` 和 `sources`。`sources` 为 `[obj]`，字段为 `materialName`、`materialId`、`refContent`。通过时不输出 `suspicionList` 或输出空数组。

完整示例：

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

## 节点配置要求

两个新增节点均选择省局内已部署、支持 ADP 结构化出参的 Qwen2.5。输入变量均为 `raw_llm_output`（类型 `str`），绑定各自上游业务 LLM 的完整 Output。提示词要求：仅依据 `raw_llm_output` 提取已有信息；只返回 JSON；不补造材料、规则或结论；无法恢复时按对应空结构输出。

每个新增目录都提供 `【LLM节点配置说明】借助LLM将出参结构化处理.md`，写明模型、输入绑定、Output Schema、可复制提示词、完整 JSON 案例，以及下游既有代码节点的绑定改动。

## 异常处理与验证

- 上游出参含 Markdown 代码块、说明文字或转义 JSON 时，Qwen2.5 只提取可支持字段并输出 Schema JSON。
- 精解无法识别内容时输出 `{\"extraction_data\": []}`；逐条认定无法识别有效结论时输出 `ruleResult=\"不通过\"` 和“信息缺失”的空来源疑点，避免下游缺少结论。
- 配置后，用现有测试数据分别验证：Qwen 节点可被 ADP 解析；精解代码节点取得非空 `extractionList`；逐条代码节点取得数组化 `ruleResult`；聚合节点无需调整即可运行。

## 备选方案与选择

1. **推荐：新增 Qwen2.5 格式化节点并保留代码节点。** 兼顾 ADP Schema 稳定性与既有代码兼容能力，改动最小。
2. 仅改原业务 LLM 提示词。无法解决本地模型不支持结构化 Output 的平台能力限制。
3. 用代码节点取代新增 Qwen2.5。对非规范自然语言 JSON 的恢复能力较弱，且不满足使用 ADP 结构化出参能力的目标。
