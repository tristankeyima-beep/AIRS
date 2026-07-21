# ADP 检索结果转规则库与逻辑树 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ADP DOC 检索结果通过通用 LLM 提示词和后置代码节点转换为 `ruleRepository` 与 `logicTopology`。

**Architecture:** LLM 从 `KnowledgeList` 的 DOC 正文中识别准入规则、证据细则和逻辑关系，并以 `R001` 等临时标识连接规则与逻辑树。Python 节点严格解析、校验和标准化输出，按病种编码末两位分配五位规则编码，并回写逻辑树引用。

**Tech Stack:** 腾讯智能体平台、Python 3 标准库（`json`、`re`）。

---

## File structure

- Create: `对接ADP知识库/将检索结果转为rule_repository/【LLM节点配置说明】将检索结果转为rule_repository.md` — 通用提示词、变量绑定与腾讯结构化 Schema。
- Create: `对接ADP知识库/将检索结果转为rule_repository/代码-将ADP提取出的rule_repository结构化.py` — LLM 输出解析、校验、编码及逻辑树回写。
- Create: `对接ADP知识库/将检索结果转为rule_repository/【代码出入参说明】代码-将ADP提取出的rule_repository结构化.md` — 代码节点契约、示例与故障定位。

### Task 1: 实现后置结构化代码节点

**Files:**

- Create: `对接ADP知识库/将检索结果转为rule_repository/代码-将ADP提取出的rule_repository结构化.py`

- [ ] **Step 1: 写出失败的导入验证**

运行：

```bash
python3 - <<'PY'
import importlib.util
from pathlib import Path

path = Path('对接ADP知识库/将检索结果转为rule_repository/代码-将ADP提取出的rule_repository结构化.py')
spec = importlib.util.spec_from_file_location('node', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PY
```

预期：目标文件尚不存在，命令失败。

- [ ] **Step 2: 写入节点实现**

实现 `main(llm_output=None, chronicDiseaseCode=None, **kwargs) -> dict`，并包含以下行为：

```text
接受 dict、list、JSON 字符串和 Markdown JSON 代码块。
拆开 Output.ruleRepository / Output.logicTopology、ruleRepository / logicTopology、result、output 外层。
要求至少一条规则；每条规则有非空 ruleContent 与非空 ruleKeywordGuide。
要求 dataType 只能为 enum 或 string；enum 有非空 enumOptions；string 的 enumOptions 输出为空数组。
从 chronicDiseaseCode 取末两位数字，规则编码为 DD001、DD002……；提取项编码为 ruleCode + 001、002……。
要求逻辑树只包含 GROUP 或 RULE_REF；GROUP 的 operator 只能为 AND 或 OR 且有 children；RULE_REF 必须引用 R001…或已生成规则编码。
用临时标识到正式规则编码的映射递归重写 logicTopology；所有引用均须存在。
输出 ruleRepository 和 logicTopology；任何解析或校验失败抛出 ValueError。
```

- [ ] **Step 3: 验证对象输出、文本输出与逻辑树回写**

运行：

```bash
python3 - <<'PY'
import importlib.util
import json
from pathlib import Path

path = Path('对接ADP知识库/将检索结果转为rule_repository/代码-将ADP提取出的rule_repository结构化.py')
spec = importlib.util.spec_from_file_location('node', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

payload = {
    'Output': {
        'ruleRepository': [
            {'tempRuleId': 'R001', 'ruleContent': '需长期透析治疗', 'ruleKeywordGuide': [
                {'dataType': 'enum', 'required': True, 'keywordContent': '判断是否需要或已接受长期透析治疗。', 'enumOptions': ['是', '否', '无法判断']}
            ]},
            {'tempRuleId': 'R002', 'ruleContent': '有二级及以上医疗机构出具的病历资料', 'ruleKeywordGuide': [
                {'dataType': 'enum', 'required': True, 'keywordContent': '判断出具机构是否为二级及以上。', 'enumOptions': ['二级及以上', '二级以下', '无法判断']}
            ]},
        ],
        'logicTopology': {'type': 'GROUP', 'operator': 'AND', 'children': [
            {'type': 'RULE_REF', 'ruleCode': 'R001'}, {'type': 'RULE_REF', 'ruleCode': 'R002'}
        ]},
    }
}
result = module.main(llm_output=payload, chronicDiseaseCode='M07801')
assert [r['ruleCode'] for r in result['ruleRepository']] == ['01001', '01002']
assert result['ruleRepository'][0]['ruleKeywordGuide'][0]['keywordCode'] == '01001001'
assert [c['ruleCode'] for c in result['logicTopology']['children']] == ['01001', '01002']
assert module.main(json.dumps(payload, ensure_ascii=False), 'M07801') == result
for bad_output, bad_code, message in [
    ({'ruleRepository': []}, 'M07801', '至少包含一条规则'),
    (payload, 'M078', '末两位数字'),
    ({'ruleRepository': payload['Output']['ruleRepository'], 'logicTopology': {'type': 'RULE_REF', 'ruleCode': 'R999'}}, 'M07801', '不存在'),
]:
    try:
        module.main(bad_output, bad_code)
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError('期望 ValueError')
PY
```

预期：退出码为 0，无输出。

### Task 2: 编写通用 LLM 节点配置说明

**Files:**

- Create: `对接ADP知识库/将检索结果转为rule_repository/【LLM节点配置说明】将检索结果转为rule_repository.md`

- [ ] **Step 1: 写入变量与结构化输出 Schema**

```text
knowledge_result: obj，绑定 ADP 知识库检索节点 Output
chronicDiseaseName: str，绑定备案病种提取节点输出
chronicDiseaseCode: str，绑定备案病种提取节点输出
Output.ruleRepository: [obj]，含 tempRuleId、规则字段和 ruleKeywordGuide
Output.logicTopology: obj，含 type、operator、children、ruleCode
```

- [ ] **Step 2: 写入全病种通用提示词**

提示词要求 LLM：

```text
只使用 KnowledgeType=DOC 的 Content，忽略 QA；同内容 DOC 去重。
从准入条件生成规则；细则只补强语义对应的规则，不能新建规则。
识别“之一”“同时”“或”“且”“未经……的”等逻辑，输出嵌套 AND/OR 树。
每条规则设置 tempRuleId=R001、R002……；logicTopology 只能引用这些临时标识。
每个规则至少一个提取项；枚举和字符串的字段约束与代码节点一致。
不生成 ruleCode、keywordCode、患者审核结论、医学常识补充或 Markdown。
```

- [ ] **Step 3: 写入跨病种边界案例**

用尿毒症说明“一个复合准入条件可拆多个提取项”；用恶性肿瘤说明“符合以下条件之一”是 OR；用眼内注射说明“适应症之一 + 共同条件”是嵌套 OR/AND。所有例子仅说明结构，不含任何病种专属硬编码。

### Task 3: 编写代码节点出入参说明

**Files:**

- Create: `对接ADP知识库/将检索结果转为rule_repository/【代码出入参说明】代码-将ADP提取出的rule_repository结构化.md`

- [ ] **Step 1: 写入输入、输出和平台绑定**

```text
llm_output: obj，绑定 LLM 节点 Output；兼容 str。
chronicDiseaseCode: str，绑定备案病种提取节点 chronicDiseaseCode。
输出 ruleRepository: [obj] 与 logicTopology: obj。
```

- [ ] **Step 2: 写入编码、回写与错误示例**

展示 `M07801 → R001 / R002 → 01001 / 01002` 及逻辑树引用同步替换；列出不合法 JSON、病种编码末尾不是两位数字、空规则、空提取项、不合法 `dataType`、空枚举、无效逻辑节点和悬空引用的失败说明。

### Task 4: 交付验证与提交

**Files:**

- Create: `对接ADP知识库/将检索结果转为rule_repository/代码-将ADP提取出的rule_repository结构化.py`
- Create: `对接ADP知识库/将检索结果转为rule_repository/【代码出入参说明】代码-将ADP提取出的rule_repository结构化.md`
- Create: `对接ADP知识库/将检索结果转为rule_repository/【LLM节点配置说明】将检索结果转为rule_repository.md`

- [ ] **Step 1: 运行 Task 1 的验证命令**

预期：退出码为 0。

- [ ] **Step 2: 进行格式检查**

运行：

```bash
git diff --check
rg -n 'ruleRepository|logicTopology|tempRuleId|chronicDiseaseCode' '对接ADP知识库/将检索结果转为rule_repository'
```

预期：`git diff --check` 无输出；三个文件均使用驼峰 `ruleRepository`。

- [ ] **Step 3: 提交三个交付文件**

运行：

```bash
git add '对接ADP知识库/将检索结果转为rule_repository'
git commit -m 'feat: convert ADP search results to rule repository'
```

预期：提交只包含三个交付文件。

## Self-review

- Spec coverage：Task 1 覆盖格式化、编码和逻辑树回写；Task 2 覆盖全病种提示词；Task 3 覆盖平台契约；Task 4 覆盖验证和提交。
- Placeholder scan：没有 TODO、TBD 或未定义字段。
- Type consistency：LLM 使用 `tempRuleId`，代码把它转换为 `ruleCode`，最终输出字段固定为 `ruleRepository` 与 `logicTopology`。
