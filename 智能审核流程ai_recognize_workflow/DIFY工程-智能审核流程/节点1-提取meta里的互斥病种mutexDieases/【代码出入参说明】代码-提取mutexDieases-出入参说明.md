# 代码节点出入参说明：提取互斥病种

对应代码：`代码-提取mutexDieases.py`

## 这个节点做什么

从认定标准 `meta.mutexDiseases` 里取出互斥病种名称，只保留名称数组，供后面的“互斥病种审核”节点使用。

## 入参

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `mutexDiseases` | Array 或 JSON字符串 | 是 | 互斥病种列表。代码里要求最终必须是数组。 |
| `currentDiseaseName` | String | 否 | 当前正在审核的病种名称，原样透传到出参。 |

### `mutexDiseases` 层级

```text
mutexDiseases: Array
  - item: Object
      mutexDiseasesCode: String，可选，互斥病种编码
      mutexDiseasesName: String，互斥病种名称，本节点会提取这个字段
```

## 出参

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `currentDiseaseName` | String | 当前病种名称。 |
| `mutexDiseasesName` | Array<String> | 互斥病种名称列表。只包含名称，不包含编码。 |

### 出参层级

```text
Object
  currentDiseaseName: String
  mutexDiseasesName: Array<String>
```

## 可直接粘贴测试的入参示例

```json
{
  "mutexDiseases": [
    {
      "mutexDiseasesCode": "M00001",
      "mutexDiseasesName": "恶性肿瘤"
    },
    {
      "mutexDiseasesCode": "M00002",
      "mutexDiseasesName": "糖尿病"
    }
  ],
  "currentDiseaseName": "冠心病"
}
```

## 对应出参示例

```json
{
  "currentDiseaseName": "冠心病",
  "mutexDiseasesName": ["恶性肿瘤", "糖尿病"]
}
```
