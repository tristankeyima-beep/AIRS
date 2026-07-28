# 慢病知识库检索 Skill 设计

## 1. 目标

新增独立 Skill `chronic-disease-knowledge-retrieval`。当用户用自然语言询问门诊慢特病认定标准、专家共识、临床指南、疾病诊疗依据等知识时，Skill 调用腾讯 ADP 已发布的 `knowledge_qa` 应用，通过应用内部配置的工作流完成检索，并把结果整理为便于调用模型继续分析的结构化 JSON。

Skill 只负责判断是否需要知识库、发起检索和整理返回结果。最终业务解读、方案讨论、标准比对或审核推理仍由调用 Skill 的模型完成。

## 2. 触发边界

以下请求应触发 Skill：

- 查询某个门诊慢特病病种的认定条件、准入标准、排除条件、材料依据或政策原文；
- 查询与慢病相关的专家共识、临床指南、诊疗规范、用药或治疗依据；
- 要求查找知识库证据、来源、版本或原文片段，为业务讨论提供依据；
- 对知识库中的多份标准、指南或共识做后续解释、比较或归纳。

以下请求不应直接触发：

- 与慢病知识无关的普通问答；
- 用户已提供完整依据、且明确只要求改写、排版或计算；
- 要求模型直接诊断患者、替代医生决策或给出最终医保资格结论。

遇到最后一类请求时，可以先检索知识依据，但必须把结果标为业务讨论参考，交由调用模型审慎处理。

## 3. 调用方案

采用已确认的 HTTP SSE 方案：

1. 调用模型识别用户问题需要查询知识库后加载本 Skill。
2. Skill 把原始自然语言问题传给 `scripts/query_adp.py`。
3. 脚本从配置文件读取 SSE 地址和非敏感参数，从环境变量读取 AppKey。
4. 脚本调用已发布的 ADP `knowledge_qa` 应用。应用内部工作流负责检索。
5. 脚本持续读取 SSE 事件，收集最终回答、知识片段、参考来源和工作流输出。
6. 脚本只向调用模型输出统一 JSON；调用模型再根据用户任务做解释、比较或引用。

不在 Skill 中实现腾讯云管理类 API、不手写 TC3 签名、不调用 `CreateWorkflowRun` 异步接口。用户提供的 SecretId 和 SecretKey 不属于本方案运行必需项，不写入任何 Skill 文件。

## 4. 目录结构

```text
SKILLS/
└── 慢病知识库检索/
    └── chronic-disease-knowledge-retrieval/
        ├── SKILL.md
        ├── agents/
        │   └── openai.yaml
        ├── config/
        │   └── adp-config.template.json
        ├── references/
        │   └── internal-deployment.md
        ├── scripts/
        │   └── query_adp.py
        └── tests/
            └── test_query_adp.py
```

不增加 README、安装器、服务端框架或多层 Python 包。

## 5. 配置模板

配置模板使用直白字段，云端切换到省局内网时只复制模板并替换值：

```json
{
  "chat_url": "https://替换为实际地址",
  "app_key_env": "ADP_APP_KEY",
  "timeout_seconds": 120,
  "streaming_throttle": 10,
  "workflow_status": "enable",
  "search_network": "disable"
}
```

约束：

- `chat_url` 是唯一与云端或内网部署地址绑定的字段；
- `app_key_env` 保存环境变量名称，不保存 AppKey；
- AppKey 只从运行进程的环境变量读取；
- 不在日志、异常、测试快照或 JSON 输出中打印 AppKey；
- `internal-deployment.md` 用短句说明“复制模板、改地址、设置环境变量、运行自检”四步，适配 Qwen 3.6-27B；
- 若内网 SSE 路径或请求字段与云端不同，以用户提供的 V3.4.1.0 内网接口文档为准，只调整配置和一个集中构造请求的函数。

## 6. Python 脚本

脚本使用 Python 标准库，避免 Web 框架、异步语法、类继承和复杂依赖。主要函数保持少量且单一：

- `load_config()`：读取并检查配置；
- `build_request()`：生成 session、visitor 和请求体；
- `read_sse()`：逐行读取 SSE；
- `collect_result()`：把事件归并为统一结果；
- `main()`：接收自然语言并输出 JSON。

命令行形式：

```bash
python scripts/query_adp.py \
  --config config/adp-config.json \
  --query "尿毒症透析的门诊慢特病认定标准是什么？"
```

成功时输出：

```json
{
  "ok": true,
  "query": "原始问题",
  "answer": "ADP 应用最终回答",
  "knowledge": [
    {
      "type": "document",
      "title": "来源标题或文件名",
      "content": "可供模型理解和引用的知识片段",
      "url": "",
      "confidence": null
    }
  ],
  "workflow": {
    "name": "",
    "run_id": "",
    "outputs": []
  },
  "meta": {
    "session_id": "",
    "request_id": "",
    "source": "tencent-adp"
  }
}
```

字段不存在时使用空字符串、空数组或 `null`，不猜测内容。若云端旧版 SSE 只返回回答和参考来源，`workflow` 可以为空；检索证据仍放入 `knowledge`。调试所需的原始事件只在显式 `--debug` 时写到标准错误，不进入默认模型上下文，并过滤敏感字段。

失败时输出 `ok=false`、简短错误类型和可执行提示，并使用非零退出码。认证失败、连接失败、超时、SSE 格式异常和无最终回答必须区分。

## 7. Skill 给模型的使用规则

`SKILL.md` 使用短句和编号，明确要求：

1. 保留用户原始问题，不擅自改成更宽泛的问题；
2. 需要知识依据时先运行脚本，再继续推理；
3. 优先使用 `knowledge` 中的原文片段和来源，`answer` 作为 ADP 的综合回答；
4. 不把空来源补造成政策、指南或共识；
5. 区分“知识库没有返回”与“事实不存在”；
6. 对认定标准、专家共识和临床指南标明检索到的来源或版本；
7. 不把检索结果直接写成患者诊断或最终医保经办结论；
8. 脚本失败时说明失败原因，不绕过知识库自行编造依据。

## 8. 测试策略

### 最小闭环

1. 配置模板和环境变量缺失时，脚本给出明确提示且不联网；
2. 使用模拟 SSE 数据验证回答、知识片段、参考来源和工作流字段的归并；
3. 使用云端 AppKey 通过环境变量发起一条窄问题，确认成功建立 SSE、收到最终回答并输出合法 JSON；
4. 全程检查标准输出和日志中没有 AppKey、SecretId 或 SecretKey。

首条云端问题使用仓库已有业务上下文中的稳定病种，例如：

```text
尿毒症透析的门诊慢特病认定标准是什么？请给出知识库依据。
```

### 完整闭环

至少覆盖三类自然语言：

- 门诊慢特病认定标准查询；
- 专家共识或临床指南查询；
- 要求模型基于多条检索依据做比较或业务解释。

完整测试验证：

- 触发说明能让模型在需要知识库时加载 Skill；
- 每次查询只调用一次 ADP，不重复消耗；
- `answer`、`knowledge` 和 `workflow` 信息不混淆；
- 来源缺失时不伪造；
- 中文内容无乱码；
- 超时、错误 AppKey、空回答和畸形 SSE 均有可理解错误；
- 云端配置替换为内网模板时不需要修改 Python 主流程。

真实云端测试只使用非患者、非敏感的通用知识问题。网络调用不创建、修改或删除 ADP 应用与知识库内容。

## 9. 验收标准

- Skill 可被自然语言中的慢病知识查询稳定触发；
- Python 程序保持单文件、标准库实现和直白流程；
- 云端最小闭环与三类完整闭环均成功；
- 默认输出是调用模型容易继续处理的 JSON；
- Skill 文件和 Git 历史中不存在真实 AppKey、SecretId、SecretKey；
- 内网部署者只需替换配置地址、设置 AppKey 环境变量并运行同一命令；
- Skill 格式校验、Python 单元测试、敏感信息扫描和仓库现有布局测试全部通过。
