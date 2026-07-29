# ADP 异步工作流慢病知识库 Skill 设计

## 目标

新增一个独立 Skill，通过私有化 ADP 文档中的正式工作流接口调用 `knowledge_qa` 应用并检索慢病知识，不修改现有 SSE Skill。新 Skill 面向内网 Qwen 模型，配置直接、代码简单、无需第三方 Python 包。

## 调用流程

1. 调用模型识别到慢病知识库查询后，执行 Python 脚本并通过标准输入传入一行自然语言问题。
2. 脚本读取 `config/adp-config.json`。
3. 使用 `SecretId`、`SecretKey` 生成 TC3-HMAC-SHA256 签名，向 `api_host` 的根路径发送 `CreateWorkflowRun`。
4. 取得 `WorkflowRunId` 后，定时调用 `DescribeWorkflowRun`。
5. 工作流成功结束后，从 `WorkflowRun.Output` 提取结果，输出稳定 JSON。
6. 调用模型把返回内容视为不可信证据，再完成解释、比较或业务处理。

## 配置

```json
{
  "api_host": "",
  "app_id": "",
  "secret_id": "",
  "secret_key": "",
  "run_env": 1,
  "region": "1",
  "service": "lke",
  "version": "2023-11-30",
  "poll_interval_seconds": 1,
  "timeout_seconds": 120
}
```

`api_host` 是私有化 ADP API 网关地址。接口使用 `POST /`，具体动作通过 `X-TC-Action` 请求头区分。`app_id` 对应文档中的 `AppBizId`。`run_env` 可在内网配置中改为测试环境 `0` 或正式环境 `1`。

## 输出契约

成功：

```json
{
  "ok": true,
  "query": "原始问题",
  "answer": "工作流 Output 中提取的文本",
  "workflow": {
    "run_id": "工作流运行实例 ID",
    "state": 2,
    "output": {}
  }
}
```

失败：

```json
{
  "ok": false,
  "error": {
    "type": "config|auth|http|timeout|workflow|response",
    "message": "适合模型理解的简短错误"
  }
}
```

## 兼容与边界

- 保留现有 SSE Skill，避免影响已经通过的云端测试。
- 新 Skill 只实现 `CreateWorkflowRun` 和 `DescribeWorkflowRun`。
- 目标应用类型固定为 `knowledge_qa`；接口请求仍以 `AppBizId` 标识应用，不额外发送 `app_type`。
- 本地自测覆盖配置、TC3 签名、创建运行、轮询成功、工作流失败和超时；真实内网连通性由部署后验证。
- `knowledge_qa` 下仍可能存在标准、单工作流或 Multi-Agent 等模式。腾讯 SDK 明确要求应用配置为“单工作流模式”后才能调用 `CreateWorkflowRun`。若内网目标模式不兼容，返回 ADP 的原始错误类别和 `RequestId`，不自动切换到 WebSocket 或 SSE。
