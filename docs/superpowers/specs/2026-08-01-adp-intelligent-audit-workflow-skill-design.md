# ADP 慢病智能审核异步工作流 Skill 改造设计

## 1. 背景

现有 `chronic-disease-knowledge-workflow` 把用户问题作为 `Query` 调用异步工作流，目标是查询慢病知识。原目标应用不能完成当前需要的异步智能审核，因此保留现有 Skill 路径和 Skill ID 以兼容已有引用，但将其业务能力原地替换为“收集审核关键信息、结构化为新 ADP 应用入参、等待工作流完成、交付结构化结果与可视化报告”。

新 ADP 应用采用单工作流模式。应用导出包确认以下 API 变量：

- `certification_list`：认定标准对象；
- `material_list`：申请材料对象数组；
- `auditId`：审核流水号；
- `suspicion_type_options`：疑点类型选项。

主工作流结束节点确认以下业务输出：

- `advice`；
- `auditId`；
- `ruleResults`；
- `finalResult`。

接口实现只依据用户提供的《腾讯云智能体开发平台 V3.4.1.0 API 接口说明-加更》，仅使用 `CreateWorkflowRun` 与 `DescribeWorkflowRun`。不通过其他云端接口替代或补充这条调用链。

## 2. 目标与非目标

### 2.1 目标

1. 支持普通业务人员用自然语言、标准 JSON、JSON 文件或疑似 JSON 文本提供认定标准与申请材料。
2. 在本地把输入整理为新 ADP 应用所需的结构化变量，并在发送前完成确定性校验。
3. 通过文档规定的异步接口创建工作流实例并轮询结果。
4. 缺少 `auditId` 时自动生成 UUID，并在结果中原样返回。
5. 配置同时支持云端联调和省局内网部署，切换环境不修改代码。
6. 面向非技术业务用户提供清晰的过程反馈、决策卡交互和业务化错误说明。
7. 正式交付稳定 JSON 与固定版本离线 HTML，可追溯且内容一致。

### 2.2 非目标

- 不保留原“慢病知识查询”触发语义。
- 不调用文档之外的工作流、对话、知识检索或管理接口。
- 不让 Python 脚本用关键词规则猜测复杂自然语言认定标准。
- 不允许模型为每次结果自由生成 HTML、CSS 或 JavaScript。
- 不在模板、设计文档、测试夹具或提交记录中保存真实 AppKey、SecretId、SecretKey 或内网地址。
- 不把工作流结果描述为最终医保资格决定；它是供业务审核使用的智能审核结果。

## 3. 设计决策

采用“模型理解与结构化 + 确定性脚本校验与调用 + 固定模板渲染”的三段式设计。

备选方案及取舍：

1. **推荐方案：模型结构化，脚本校验、调用和渲染。** 能理解自然语言，又能确保 API 请求、轮询、结果契约和 HTML 生成稳定可测。
2. **脚本同时承担自然语言理解。** 实现集中，但规则启发式无法可靠处理认定标准中的 AND/OR、阈值、排除项和材料证据语义。
3. **模型直接调用 API 并自由生成展示。** 文件少，但缺少可重复校验，容易发生请求结构漂移、结果字段遗漏和 HTML 不一致。

## 4. 总体架构

```mermaid
flowchart LR
    U["普通业务用户"] --> S["Skill 交互与输入盘点"]
    S --> D{"存在会改变结果的明确歧义？"}
    D -->|"是"| C["优先弹出决策卡"]
    C --> S
    D -->|"否"| N["本地结构化与规范化"]
    N --> V["确定性输入校验"]
    V --> A["CreateWorkflowRun"]
    A --> P["DescribeWorkflowRun 轮询"]
    P --> R["结果解析与契约化"]
    R --> J["审核结果 JSON"]
    J --> H["固定版本离线 HTML"]
    J --> O["成果物交付"]
    H --> O
```

职责边界：

- `SKILL.md`：识别触发场景、盘点输入、决定何时使用决策卡、生成统一输入对象、调用脚本并交付成果。
- 输入契约参考文件：定义 `certification_list`、`material_list` 及自然语言适配规则。
- 工作流客户端脚本：加载配置、校验输入、序列化 `CustomVariables`、TC3 签名、创建实例、轮询和解析结果。
- 结果契约参考文件：定义稳定结果 JSON，不让 HTML 直接依赖 ADP 原始响应形态。
- HTML 渲染脚本：校验结果契约，复制固定模板并安全注入 JSON。
- 固定 HTML 资产：只负责展示，不生成新业务事实或结论。

## 5. 交互体验

### 5.1 面向业务人员的语言

用户可见交流使用“认定标准、申请材料、审核流水号、审核结论、疑点”等业务词汇。除非用户主动询问技术细节，不展示 `CustomVariables`、`ARRAY_OBJECT`、TC3、节点状态等内部术语。

信息完整且没有业务歧义时直接执行，不设置固定的二次确认门。开始调用前告知用户“关键信息已整理完成，正在执行智能审核”。工作流运行时间较长时持续给出简短状态，不让用户无反馈等待。

### 5.2 决策卡优先规则

当需要用户从两个或以上清晰、可执行、互斥的选项中选择时，运行环境支持决策卡就必须主动优先使用平台决策卡，不得只在正文中罗列选项。推荐选项排在第一位，并用一句中文说明影响，但不得替用户默认选择。

优先使用决策卡的场景包括：

- 同时识别出多份认定标准，需要选择本次采用哪一份；
- 同时识别出多个病种或病种编码，需要确定审核对象；
- 一份材料可能属于多个申请或材料分组；
- 疑似 JSON 有两种以上会改变业务含义的修复结果；
- 调用失败后存在重试、调整输入或停止等明确选项。

每张卡只解决一个决策；一轮最多三张。需要用户粘贴长文本、上传文件或自由填写病种编码时使用普通对话。运行环境没有决策卡能力时，才降级为一句简短的正文提问。敏感凭据告警不使用业务决策卡。

### 5.3 结果呈现顺序

对话摘要和 HTML 均优先展示：

1. 总审核结论；
2. 审核建议；
3. 逐条认定情况；
4. 疑点及关联证据；
5. 审核流水号和必要的执行标识。

不向普通用户默认倾倒原始 API 响应、工作流图、节点日志或签名信息。

## 6. 输入契约与规范化

### 6.1 统一调用对象

发送前统一为：

```json
{
  "certification_list": {
    "meta": {
      "chronicDiseaseName": "病种名称",
      "chronicDiseaseCode": "病种编码"
    },
    "ruleRepository": [],
    "logicTopology": {}
  },
  "material_list": [],
  "auditId": "自动生成或用户提供的流水号",
  "suspicion_type_options": "指标异常;信息缺失;资质不符;临床表现不足;材料不全"
}
```

完整字段以目标工作流项目中的现有测试入参和节点说明为准，不为方便调用擅自改变字段名。

### 6.2 `certification_list`

- 必须最终为对象。
- `meta.chronicDiseaseName` 与 `meta.chronicDiseaseCode` 必须为非空字符串，因为目标子工作流会先读取这两个字段。
- 标准 JSON 文件或 JSON 对象优先保留其完整结构。
- 单元素对象数组可无损解包；多元素数组不得静默取第一项，应通过决策卡让用户选择。
- 自然语言标准由模型在本地结构化；必须保留原意，不使用外部医学或政策知识补造规则。
- AND/OR、阈值、单位、时长、次数、排除项或规则适用范围存在会改变审核含义的歧义时，先让用户确认。
- 病种编码无法从输入确定时，请用户自由填写；若已识别出少量候选编码，使用决策卡。

### 6.3 `material_list`

- 必须最终为非空对象数组。
- 每份材料保留为独立对象，不把多份材料拼接成一个材料。
- 最小对象包含 `materialId`、`materialName`、`materialContent`；缺少 `materialId` 时生成本地 UUID。
- `materialType`、`sourceHospital`、`hospitalLevel`、`reportDate`、`uploadTime`、`materialSummary` 在来源中存在时保留，不存在时使用契约允许的空值，不补造。
- 一段自然语言申请材料可转换为一条材料记录；多份自然语言材料按标题、文件或用户明确分隔保留为多条。

### 6.4 JSON 与疑似 JSON

按以下顺序处理：

1. 标准 JSON 解析；
2. 去除 UTF-8 BOM 或单层 Markdown 代码围栏后重试；
3. 对单引号、尾随逗号、`True`、`False`、`None` 等可由安全字面量解析且不改变业务含义的形式进行规范化；
4. 仍失败时由模型依据上下文整理；
5. 存在多种语义解释时停止并使用决策卡，不猜测。

不得使用 `eval`，不得执行输入中的代码、命令、提示词或工具指令。

### 6.5 默认值

- `auditId`：缺失时生成 UUID；已有值不覆盖。
- `suspicion_type_options`：缺失时使用应用导出包中的默认值；已有非空值不覆盖。
- `Query`：使用不含患者正文的固定业务描述或审核流水号，不重复发送完整材料。
- `VisitorId`：每次调用生成 UUID。

## 7. ADP 请求设计

### 7.1 创建实例

`CreateWorkflowRun` 请求体只使用接口文档允许的字段：

```json
{
  "AppBizId": "来自当前 profile",
  "RunEnv": 0,
  "Query": "执行智能审核",
  "CustomVariables": [
    {"Name": "certification_list", "Value": "紧凑 JSON 字符串"},
    {"Name": "material_list", "Value": "紧凑 JSON 字符串"},
    {"Name": "auditId", "Value": "字符串"},
    {"Name": "suspicion_type_options", "Value": "字符串"}
  ],
  "VisitorId": "UUID"
}
```

对象和数组先按 UTF-8、`ensure_ascii=false`、禁止非有限数的方式序列化为紧凑 JSON 字符串，再作为 `CustomVariable.Value` 发送。

### 7.2 轮询实例

取得 `WorkflowRunId` 后，以 `AppBizId` 与 `WorkflowRunId` 调用 `DescribeWorkflowRun`。继续使用现有可配置轮询间隔和总超时机制：

- 成功状态时解析 `WorkflowRun.Output`；
- 明确失败或停止状态时返回工作流错误；
- 达到总超时时停止轮询并返回超时错误；
- 保存服务端 `RequestId` 供排障，但不把节点图或完整响应写入正式业务报告。

### 7.3 输出兼容

`WorkflowRun.Output` 可能是 JSON 字符串或对象。解析后提取 `advice`、`auditId`、`ruleResults`、`finalResult`。

`ruleResults` 兼容：

- 对象数组；
- JSON 字符串形式的数组；
- 数组中的单项 JSON 字符串。

只做结构解包和类型规范化，不改变工作流给出的规则结论、证据或建议。必需字段缺失时返回响应错误，不生成看似完整的正式 HTML。

## 8. 配置设计

真实配置保存在被 Git 忽略的 `config/adp-config.json`。模板只保存空值和说明性 profile：

```json
{
  "active_profile": "cloud",
  "profiles": {
    "cloud": {
      "api_host": "",
      "app_id": "",
      "app_key": "",
      "secret_id": "",
      "secret_key": "",
      "run_env": 0,
      "region": "1",
      "service": "lke",
      "version": "2023-11-30"
    },
    "provincial_intranet": {
      "api_host": "",
      "app_id": "",
      "app_key": "",
      "secret_id": "",
      "secret_key": "",
      "run_env": 1,
      "region": "1",
      "service": "lke",
      "version": "2023-11-30"
    }
  },
  "poll_interval_seconds": 1,
  "timeout_seconds": 300
}
```

- `active_profile` 控制当前使用的环境。
- 云端和省局内网可以使用不同的网关、应用、密钥和运行环境。
- `app_key` 按用户要求保存在 profile 中，但 `CreateWorkflowRun` 与 `DescribeWorkflowRun` 的文档请求结构没有该字段，因此客户端不发送它。
- 错误信息、标准输出、测试和 HTML 都不得回显 `app_key`、`secret_id`、`secret_key` 或签名头。
- 云端真实参数只进入本机被忽略配置；提交的模板保持空值。

## 9. 稳定结果 JSON

正式结果使用 `adp-audit-result-1.0` 契约：

```json
{
  "schemaVersion": "adp-audit-result-1.0",
  "templateVersion": "audit-result-template-1.0",
  "generatedAt": "ISO-8601 时间",
  "audit": {
    "auditId": "审核流水号",
    "diseaseName": "病种名称",
    "diseaseCode": "病种编码",
    "finalResult": "通过或不通过",
    "advice": "审核建议",
    "materialCount": 1
  },
  "ruleResults": [],
  "execution": {
    "profile": "cloud 或 provincial_intranet",
    "runEnv": 0,
    "workflowRunId": "工作流运行实例 ID",
    "requestId": "服务端请求 ID"
  }
}
```

规则明细完整保留目标工作流返回的 `ruleCode`、`ruleContent`、`ruleResult`、`reasoningContent`、`ruleKeywordGuide` 与 `suspicionList`。正式结果不复制完整患者材料，只保留工作流已经纳入规则明细的证据片段，减少不必要的敏感信息扩散。

## 10. 固定版本 HTML

### 10.1 固定模板

新增 `assets/audit-result-template.html`，模板版本固定为 `audit-result-template-1.0`。每次生成都从该资产复制，不允许模型或运行脚本修改模板 CSS 和 JavaScript。

模板使用唯一数据槽：

```html
<script id="audit-data" type="application/json">__AUDIT_DATA_JSON__</script>
```

渲染步骤：

1. 校验结果 JSON 的 Schema 与模板版本；
2. 确认占位符在指定数据槽中恰好出现一次；
3. 仅对序列化 JSON 中的字面 `<`、`>`、`&` 转义为 `\u003c`、`\u003e`、`\u0026`；
4. 只替换数据槽占位符一次；
5. 重新解析槽内 JSON，确认与交付 JSON 逐字段等值；
6. 失败时不交付部分 HTML，也不手工修补展示内容。

页面脚本只使用 `textContent` 创建业务内容，不使用 `innerHTML`，不依赖 CDN、网络字体或外部 JavaScript，可离线打开、搜索和打印。

### 10.2 页面结构

固定展示：

1. 报告概览：病种、流水号、生成时间、总审核结论；
2. 审核建议；
3. 规则统计：通过、不通过和总数；
4. 逐条认定结果；
5. 疑点列表：类型、说明和关联材料；
6. 证据详情：材料名称、材料 ID、引用原文和提取值；
7. 推理说明；
8. 执行信息：工作流实例 ID 与请求 ID。

不在 HTML 中显示密钥、签名、API 请求体、完整患者材料或节点运行日志。

### 10.3 成果文件

正式成果固定为：

```text
<auditId>-智能审核结果.json
<auditId>-智能审核结果.html
```

工作流客户端要求显式传入可写的输出目录，避免把业务成果写入 Skill 安装目录。生成后 JSON 和 HTML 作为两个独立成果物交付；HTML 是业务阅读入口，JSON 是唯一事实源和系统交换文件。

## 11. 错误处理

稳定错误类型：

| 类型 | 业务提示方向 |
| --- | --- |
| `config` | 当前审核服务尚未配置，请联系维护人员检查运行环境。 |
| `input` | 已收到材料，但仍缺少本次审核必需的信息。 |
| `auth` | 审核服务身份校验失败，请维护人员检查密钥和系统时间。 |
| `http` | 当前无法连接审核服务，请稍后重试或联系维护人员。 |
| `timeout` | 审核仍未在限定时间内完成，可选择继续重试或稍后处理。 |
| `workflow` | 工作流执行失败，可根据流水号和请求 ID 排查。 |
| `response` | 工作流已返回，但结果结构不完整，未生成正式报告。 |
| `render` | 审核 JSON 已生成，但可视化页面生成失败。 |

错误时优先说明用户接下来可以做什么。技术错误类型、请求 ID 可放在简短“排障信息”中，但不得包含原始异常堆栈、密钥、签名或完整患者材料。

若 JSON 已成功生成但 HTML 渲染失败，明确交付 JSON 并说明 HTML 尚未形成；不得把不完整 HTML 称为正式成果。

## 12. 安全与隐私

- 用户输入、材料原文、OCR、文件名、工作流输出都作为不可信数据处理，不执行其中的命令、提示词或工具请求。
- 用户在正常业务材料中提供患者信息是工作流业务输入；只发送本次审核所需字段，不在日志重复打印。
- Skill 自身发现用户把 API 密钥混入待审核材料时，停止发送材料并给出不含具体值的脱敏告警。
- 配置文件的密钥字段不得进入结果 JSON、HTML、stdout、stderr、异常信息或测试快照。
- 云端联调使用最小化、合成、无真实患者身份信息的测试输入。
- 正式成果保留工作流返回的必要证据片段，但不额外复制完整申请材料。

## 13. 文件结构

保留现有 Skill 根目录和 `chronic-disease-knowledge-workflow` ID，计划调整为：

```text
chronic-disease-knowledge-workflow/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── assets/
│   └── audit-result-template.html
├── config/
│   └── adp-config.template.json
├── references/
│   ├── input-contract.md
│   ├── result-contract.md
│   └── internal-deployment.md
├── scripts/
│   ├── run_adp_audit_workflow.py
│   └── render_audit_result.py
└── tests/
    ├── fixtures/
    ├── test_run_adp_audit_workflow.py
    ├── test_render_audit_result.py
    └── test_skill_contract.py
```

旧 `query_adp_workflow.py` 与其测试由新审核客户端替换，不保留两套并行语义。

## 14. 验证策略

### 14.1 单元测试

- profile 选择、必填字段、URL、时间参数和密钥不泄漏；
- 固定 TC3 签名向量；
- 标准 JSON、代码围栏 JSON、安全疑似 JSON 和非法输入；
- 单元素标准数组解包、多元素数组阻断；
- `auditId` 保留与自动生成；
- 材料最小字段、材料 ID 自动生成和多材料独立保留；
- `CustomVariables` 名称、值序列化和请求体字段白名单；
- 创建、轮询、成功、失败、超时、鉴权和异常响应；
- 字符串化 `ruleResults` 的兼容解析；
- 正式结果 JSON 契约。

### 14.2 HTML 测试

- 固定 Schema 与模板版本；
- 唯一数据槽与唯一占位符；
- 不使用 `innerHTML`，不引用外部资源；
- `<`、`>`、`&` 和 `</script>` 注入安全；
- 槽内 JSON 与交付 JSON 逐字段等值；
- 通过、不通过、空疑点、多疑点、长证据和缺失可选字段；
- 页面包含结论、建议、规则、疑点、证据和执行标识；
- 桌面、窄屏与打印布局视觉检查。

### 14.3 云端联调

1. 使用被忽略的云端 profile 和用户提供的真实配置；
2. 使用合成病种、合成标准和合成材料，不发送示例包中的真实患者信息；
3. 确认 `CreateWorkflowRun` 返回运行实例 ID；
4. 确认 `DescribeWorkflowRun` 完成并返回四个业务字段；
5. 确认 JSON 和 HTML 生成、等值校验与视觉检查通过；
6. 检查输出与日志中不存在任何密钥值。

### 14.4 省局内网验收

只切换 `active_profile` 并填写内网网关、应用和密钥。重复相同合成用例，确认不需要改代码、模板或字段映射。

## 15. 验收标准

1. Skill 仍可通过现有 ID 被引用，但展示名称和触发描述已变为慢病智能审核。
2. 自然语言、JSON 文件和疑似 JSON 均能进入统一输入流程。
3. 业务歧义出现且平台支持时，Skill 主动使用决策卡；不支持时才正文降级。
4. 无 `auditId` 的输入可以自动生成并完成审核。
5. 客户端只调用文档规定的两个异步工作流接口。
6. 云端与省局内网通过 profile 切换，不修改代码。
7. 成功调用固定交付契约化 JSON 和固定版本离线 HTML。
8. HTML 与 JSON 逐字段一致，页面不自由生成、不执行用户内容且不依赖外网。
9. 失败分类可理解、可排障且不泄漏凭据或完整患者材料。
10. 单元测试、Skill 结构验证、云端无敏感数据联调和 HTML 视觉验收全部通过。
