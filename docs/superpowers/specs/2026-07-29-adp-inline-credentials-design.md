# ADP 内网凭据直接配置设计

## 目标

为了让内网的 Qwen 3.6-27B 和部署人员更容易理解、配置慢病知识库检索 Skill，将 AppKey、SecretId、SecretKey 统一放在运行配置文件中，不再要求通过环境变量注入 AppKey。

## 配置文件

部署人员将：

```text
<SKILL_ROOT>/config/adp-config.template.json
```

复制为：

```text
<SKILL_ROOT>/config/adp-config.json
```

然后直接填写：

```json
{
  "chat_url": "填写内网 ADP SSE 地址",
  "app_key": "填写 AppKey",
  "secret_id": "填写 SecretId",
  "secret_key": "填写 SecretKey",
  "timeout_seconds": 120,
  "streaming_throttle": 10,
  "workflow_status": "enable",
  "search_network": "disable"
}
```

模板只包含占位符，不包含真实凭据。真实 `adp-config.json` 不纳入 Git。

## 运行行为

- `query_adp.py` 直接从配置文件读取 `app_key`。
- 当前 HTTP SSE 对话请求只使用并发送 AppKey。
- `secret_id` 和 `secret_key` 不发送给 SSE 地址；它们作为内网 V3 签名接口的预留配置。
- 如果以后启用 V3 签名接口，应只在签名适配代码中读取 SecretId 和 SecretKey，不改变 Qwen 的配置方式。

## 错误与安全边界

- 缺少或未替换 `app_key` 时返回 `config` 错误。
- SecretId、SecretKey 当前不参与 SSE 检索，因此缺少它们不应阻断现有 SSE 请求。
- AppKey、SecretId、SecretKey 不得出现在标准输出、错误信息、调试输出或请求失败日志中。
- 配置文档明确提醒：真实配置仅用于内网部署，不提交 Git，不复制到聊天内容。

## 测试

- 先增加失败测试，证明客户端尚不能从配置文件读取 AppKey。
- 验证 AppKey 从配置文件进入 SSE 请求体。
- 验证不再依赖 `ADP_APP_KEY` 环境变量。
- 验证 SecretId、SecretKey 不进入 SSE 请求体、输出或错误信息。
- 验证模板字段、内网部署说明和 Skill 调用说明一致。
- 运行现有客户端测试、Skill 校验、布局测试和敏感信息扫描。
