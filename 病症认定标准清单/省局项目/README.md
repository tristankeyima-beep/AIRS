# 省局项目病症认定标准维护说明

本目录用于维护省局项目的病症认定标准清单。当前版本来自 Excel：

`八类疾病准入条件及细则-20260517.xlsx`

本次已将 Excel 转为三类文件：

- `md`：认定标准文本版，便于人工阅读和修改。
- `json`：智能审核工作流入参 `certification_list`，用于流程调用。
- `html`：认定标准可视化页面，用于查看规则拓扑和提取项维护情况。

## 目录结构

```text
省局项目/
  01_尿毒症透析/
    v20260517/
      尿毒症透析-认定标准-v20260517.md
      尿毒症透析-certification_list-v20260517.json
      尿毒症透析-认定标准可视化-v20260517.html
  02_恶性肿瘤（含白血病）放化疗及相关治疗/
    v20260517/
      ...
```

维护约定：

- 第一层是病种目录，目录名前带两位序号，保持与源表顺序一致。
- 第二层是版本目录，格式为 `vYYYYMMDD`。
- 每个版本目录内固定放三件套：`md`、`json`、`html`。
- 新增版本时，不覆盖旧版本，新增一个新的 `vYYYYMMDD` 目录。

## 从 Excel 到 Markdown

Excel 有效内容在 `Sheet1`，`Sheet2`、`Sheet3` 为空。

源表字段：

- 序号
- 疾病
- 准入条件
- 准入条件明细
- 提取项细则

转换规则：

1. 展开 Excel 合并单元格，确保分项行继承正确的序号和疾病名称。
2. 按病种归并，不把所有病种挤在一个 Markdown 里。
3. 每个病种一个目录，每个版本一份 Markdown。
4. Markdown 中保留：
   - 准入条件
   - 分项条件
   - 提取项细则
5. 原文不做政策口径改写，最多做换行和结构整理。

## 从 Markdown 到 certification_list JSON

JSON 必须符合智能审核工作流入参格式：

```json
{
  "certification_list": {
    "meta": {},
    "ruleRepository": [],
    "logicTopology": {}
  }
}
```

其中：

- `meta`：版本、病种名称、病种编码、来源文件等元信息。
- `ruleRepository`：规则清单，每条规则包含 `ruleCode`、`ruleContent`、`ruleSource`、`ruleKeywordGuide`。
- `logicTopology`：AND / OR 逻辑拓扑，只引用 `ruleRepository` 中已有的 `ruleCode`。

提取项拆解必须参考：

`认定标准提取/腾讯智能体平台-认定标准提取/节点1-生成提取项/【LLM节点配置说明】生成提取项.md`

核心原则：

1. 只按“准入条件原文”拆解，不根据病种名称或医学常识额外补项。
2. 一个提取项只验证一个原子事实。
3. 复合条件要拆开，例如“疾病确诊 + 医疗机构等级”拆成两个提取项。
4. 每个 `ruleKeywordGuide` 必须包含：
   - `keywordCode`
   - `keywordContent`
   - `dataType`
   - `required`
   - `enumOptions`
5. `enum` 类型必须有非空 `enumOptions`。
6. `string` 类型的 `enumOptions` 固定为空数组 `[]`。
7. 每条规则保留来源追溯字段：
   - `sourceMdFile`
   - `sourceSection`
   - `sourceRuleContent`

## 从 JSON 到可视化 HTML

HTML 用于查看单个病种单个版本的规则维护情况。

生成规则：

- 每个版本目录一份 HTML。
- HTML 与同版本的 `md`、`json` 放在同一目录。
- 页面主体采用“规则判定总览 / 逻辑拓扑”的样式。
- 默认只展示规则卡片摘要。
- 点击规则卡片“展开”后展示：
  - 政策原文
  - 政策依据
  - 来源分项
  - 认定标准原文
  - 提取项说明表
- 提取项说明表包含：
  - 编号
  - 内容
  - 数据类型
  - 是否必须
  - 可选项
  - 完整数据结构
- “完整数据结构”默认收起，点击“展开”后查看 JSON。

页面约束：

- 不展示顶部大统计区。
- 不展示“查看JSON”按钮。
- 不截断提取项内容，不使用 `...` 或省略号。
- 规则卡片内不重复展示 AND / OR 逻辑路径标签，逻辑关系只在拓扑树上展示。

## 校验清单

每次新增或修改版本后，至少做以下校验：

1. 目录完整性：
   - 每个版本目录有且只有一份 `md`
   - 每个版本目录有且只有一份 `certification_list` JSON
   - 每个版本目录有且只有一份可视化 HTML

2. JSON 可解析：
   - JSON 语法正确
   - 顶层包含 `certification_list`
   - `ruleRepository` 是数组
   - `logicTopology` 中所有 `RULE_REF.ruleCode` 都能在 `ruleRepository` 中找到

3. 提取项字段完整：
   - 每个提取项都有 `keywordCode`
   - 每个提取项都有 `keywordContent`
   - 每个提取项都有 `dataType`
   - 每个提取项都有 `required`
   - 每个提取项都有 `enumOptions`

4. 原文可追溯：
   - 每条规则的 `sourceRuleContent` 能在对应 Markdown 中找到
   - `ruleContent` 不脱离 `sourceRuleContent`
   - 不把“提取项细则”反向补成准入规则

5. HTML 可读：
   - 页面没有顶部大统计区
   - 页面没有“查看JSON”按钮
   - 提取项内容不截断
   - “可选项”列展示 `enumOptions`
   - “完整数据结构”默认收起

## 当前版本

当前已维护版本：`v20260517`

当前病种：

1. 尿毒症透析
2. 恶性肿瘤（含白血病）放化疗及相关治疗
3. 器官移植后抗排异治疗
4. 精神病
5. 眼内注射治疗黄斑病变
6. 使用特立氟胺治疗多发性硬化症
7. 癫痫
8. 帕金森
