# AIRS 智能审核 Dify 工作流运行测试

这个目录只用于 AIRS 智能审核流程工作流测试，不再维护 AIHcare 干预方案、认定标准提取或 Chatflow 分支。

## 本地工作流 Key

```bash
DIFY_API_KEY="app-nNTQp7OB3FmhWY0q6DTz6XR9"
```

脚本生成普通终端执行命令时不把 Key 写入结果文件；真正调用 Dify 时会从本 README 读取上面的 Key。HTML 和原始结果中的请求头只显示 `Bearer ***`。

## Codex 快速处理约定

测试者在 Codex 对话中直接贴大段 AIRS 入参时，默认走快速路径：

1. Codex 先把原始入参保存成临时 JSON。
2. Codex 立即执行 `prepare-input` 生成 `userinput/<患者名称>_<申请病种>_<记录时间>/入参.json`。
3. Codex 只返回生成的 `入参.json` 路径、识别出的患者名称/申请病种，以及普通终端执行命令。

除非测试者明确要求检查、调试、验证或分析结果，Codex 不额外展开入参内容、不做额外验证、不发起 Dify 调用。

## 使用流程

### 1. 结构化测试者入参

```bash
cd "/Users/Tristan/TristansDevelop/TristanProject/AIRS/智能审核流程ai_recognize_workflow/DIFY工程-智能审核流程/DIFY工作流运行测试"
python3 dify_airs_runner.py prepare-input --input "/path/to/raw-input.json"
```

生成结果：

- `userinput/<患者名称>_<申请病种>_<记录时间>/入参.json`
- 一段普通终端执行命令

`prepare-input` 会兼容两种入参形态：

- `certification_list` / `material_list` 已经是 JSON 对象或数组
- `certification_list` / `material_list` 是 JSON 字符串

患者名称提取顺序：

1. 顶层 `patientName` / `patient_name` / `姓名`
2. `material_list[*].materialContent` 中的 `姓名：xxx`
3. `未知患者`

申请病种提取顺序：

1. `certification_list.meta.chronicDiseaseName`
2. 顶层 `chronicDiseaseName`
3. `未知病种`

### 2. 用户执行命令发起 Dify 工作流

复制 `prepare-input` 输出的普通终端命令执行，例如：

```bash
cd "/Users/Tristan/TristansDevelop/TristanProject/AIRS/智能审核流程ai_recognize_workflow/DIFY工程-智能审核流程/DIFY工作流运行测试" && python3 dify_airs_runner.py run --case-dir "userinput/刘会芝_糖尿病_20260516-153031"
```

默认调用：

- `POST https://dify.hzmarvel.com/v1/workflows/run`
- `response_mode: "streaming"`
- `user: "dify-airs-workflow-test"`
- `transport: "curl"`

脚本默认走 `https`，并默认用系统 `curl` 发起调用，Python 负责结构化入参、解析 SSE 和归档结果。不要改用 `http`：`http://dify.hzmarvel.com/v1/workflows/run` 可能返回网关 `502 Bad Gateway`，不会进入正确的 Dify 服务。

如果需要回退到 Python `urllib` 调试，可以显式加 `--transport urllib`。

### 3. 查看和归档结果

每次调用会写入同一个 case 目录下的独立子目录：

```text
userinput/<患者名称>_<申请病种>_<记录时间>/<调用时间>_<workflowrunid>/
```

子目录内固定生成：

- `<调用时间>_<workflowrunid>_raw-result.json`
- `<调用时间>_<workflowrunid>_result.html`
- `<调用时间>_<workflowrunid>_events.ndjson`

如果 Dify 失败或未返回 `workflow_run_id`，目录名使用：

```text
<调用时间>_no-workflowrunid
```

### 4. 重新渲染 HTML

```bash
python3 dify_airs_runner.py render-html --record "userinput/刘会芝_糖尿病_20260516-153031/20260516-154056_abc-123/20260516-154056_abc-123_raw-result.json"
```

## 当前 AIRS 工作流资料

- 节点 1：`../节点1-提取meta里的互斥病种mutexDieases/【代码出入参说明】代码-提取mutexDieases-出入参说明.md`
- 节点 2：`../节点2-将rule_repository 转换为可迭代的数组/【代码出入参说明】节点1代码-出入参说明.md`
- 互斥病种审核：`../节点2并列-互斥病种审核/【代码出入参说明】代码-互斥病种审核结果结构化-出入参说明.md`
- 精解：`../节点3-迭代/1精解/【代码出入参说明】代码-将精解结果结构化-出入参说明.md`
- 逐条认定：`../节点3-迭代/2逐条认定/【代码出入参说明】代码-单条标准审核结果结构化-出入参说明.md`
- 出参聚合：`../节点3-迭代/3聚合推理过程&精解结果&认定结果/【代码出入参说明】代码-出参聚合-出入参说明.md`
- 逻辑合并：`../节点4-按逻辑合并审核+吐出推理过程/【代码出入参说明】逻辑合并0427-出入参说明.md`
