# 代码节点出入参说明：组装 certification_list

对应代码：`代码-组装certification_list.py`

## 节点职责

将 ADP 分支已经生成的病种信息、规则库、逻辑树和确定性文档名组装为完整 `certification_list`，直接接入既有审核流程。

## 入参

| 字段 | 类型 | 必填 | 绑定来源 |
| --- | --- | --- | --- |
| `chronicDiseaseName` | `str` | 是 | 根据 certification_list 获取备案病种节点输出。 |
| `chronicDiseaseCode` | `str` | 是 | 根据 certification_list 获取备案病种节点输出。 |
| `documentName` | `str` | 是 | 提取相关性最高的知识库结果节点输出。 |
| `ruleRepository` | `[obj]` 或 `obj` 或 `str` | 是 | 将 ADP 提取出的 ruleRepository 结构化节点输出。 |
| `logicTopology` | `obj` 或 `str` | 是 | 将 ADP 提取出的 ruleRepository 结构化节点输出。 |

推荐腾讯绑定：

```text
chronicDiseaseName = 根据 certification_list 获取备案病种.chronicDiseaseName
chronicDiseaseCode = 根据 certification_list 获取备案病种.chronicDiseaseCode
documentName = 提取相关性最高的知识库结果.documentName
ruleRepository = 将 ADP 提取出的 ruleRepository 结构化.ruleRepository
logicTopology = 将 ADP 提取出的 ruleRepository 结构化.logicTopology
```

## 出参

```text
certification_list: obj
  meta: obj
    version: str
    chronicDiseaseName: str
    chronicDiseaseCode: str
    createdAt: str
    description: str
    sourceFile: str
  ruleRepository: [obj]
  logicTopology: obj
```

## 元信息生成规则

```text
documentName = 尿毒症透析-认定标准-v20260517.md
version = ADP-尿毒症透析-认定标准-v20260517
createdAt = 节点执行日期，例如 2026-07-21
description = 由 ADP 知识库检索结果生成
sourceFile = ruleRepository 第一条规则的 ruleSource；缺失时为 ADP知识库检索结果
```

## 校验

病种名称、病种编码、文档名、规则库和逻辑树均不能为空。每条规则必须有唯一 `ruleCode`；逻辑树只能使用 GROUP / RULE_REF，且每个 `RULE_REF.ruleCode` 必须在 `ruleRepository` 中存在。

## 下游绑定

把本节点的 `certification_list` 直接绑定到既有审核流程“规则库转可迭代数组”节点的 `certification_list` 入参，类型选 `obj`。
