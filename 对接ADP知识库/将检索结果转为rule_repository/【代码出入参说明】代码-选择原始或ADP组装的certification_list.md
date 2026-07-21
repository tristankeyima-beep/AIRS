# 代码节点出入参说明：返回原始 certification_list（知识库未命中分支）

对应代码：`代码-选择原始或ADP组装的certification_list.py`

## 节点职责

该节点只放在“提取相关性最高的知识库结果”之后的**未命中分支**：即条件判断发现 `knowledgeContent` 为空时，流程进入本节点。

节点将最初传入工作流的完整 `certification_list` 原样输出，使未检索到当前病种认定标准时，既有审核流程仍继续使用原规则。

`knowledgeContent` 的是否为空由上游条件节点判断，本代码节点**不再接收** `knowledgeContent`，也不接收 ADP 组装结果。

## 入参

| 字段 | 类型 | 必填 | 绑定来源 | 说明 |
| --- | --- | --- | --- | --- |
| `originalCertificationList` | `obj` | 是 | 工作流初始入参 `certification_list` | 最初接收到的完整对象。 |

腾讯平台配置：

```text
originalCertificationList = 工作流初始入参 certification_list
类型 = obj
```

不能只传 `ruleRepository`，也不能传 JSON 字符串。

## 可直接粘贴测试的入参示例

```json
{
  "originalCertificationList": {
    "meta": {
      "version": "v20260517",
      "chronicDiseaseName": "尿毒症透析",
      "chronicDiseaseCode": "M07801"
    },
    "ruleRepository": [
      {"ruleCode": "01001"}
    ],
    "logicTopology": {
      "type": "RULE_REF",
      "ruleCode": "01001"
    }
  }
}
```

## 出参

```text
certification_list: obj
```

出参内容与 `originalCertificationList` 完全一致。将它直接绑定到既有“认定标准提取”流程的 `certification_list` 入参。

## 分支衔接

```text
提取相关性最高的知识库结果
  └─ 条件：knowledgeContent 是否为空
       ├─ 否：继续 LLM → 结构化 → 组装 certification_list → 使用组装结果
       └─ 是：本节点 → 使用原始 certification_list
```

## 联调定位

| 现象 | 原因与处理 |
| --- | --- |
| `originalCertificationList 必须是完整 certification_list 对象` | 初始 `certification_list` 未绑定，或传入了字符串 / 规则数组。 |
| 未命中时仍进入 LLM | 检查条件节点是否以 `knowledgeContent` 为空作为未命中条件。 |
