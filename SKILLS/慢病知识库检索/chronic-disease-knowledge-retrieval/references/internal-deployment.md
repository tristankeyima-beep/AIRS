# 内网部署

## 1. 复制配置模板

将 `config/adp-config.template.json` 复制为 `config/adp-config.json`，保持 UTF-8 编码。不要在 JSON、Python、SKILL、日志、聊天内容或命令历史中写入 AppKey。

## 2. 修改服务地址

只把 `chat_url` 改为实际的 ADP SSE 地址。此 SSE 方案不使用 SecretId 或 SecretKey。

如果内网请求字段与当前实现不同，以用户提供的 V3.4.1.0 文档为准，并将字段适配集中在 `scripts/query_adp.py` 的 `build_request` 中；不要分散修改，也不要引入 SDK 内部实现。

## 3. 安全设置 AppKey

使用系统的服务配置、密钥管理或受保护的环境注入机制，设置模板中 `app_key_env` 指定的 `ADP_APP_KEY`。不要把密钥直接输入会记录命令历史的命令行。

## 4. 运行自检

确认配置与环境变量已在目标内网环境生效后运行：

```bash
python3 scripts/query_adp.py --config config/adp-config.json --query "请检索一个已知慢病条目，并返回依据来源"
```

检查标准输出为 UTF-8 JSON，且顶层 `ok` 为 `true`。若不是，先按 `error_type` 区分配置、鉴权、网络、超时、SSE 或空结果问题，不在日志中输出 AppKey。
