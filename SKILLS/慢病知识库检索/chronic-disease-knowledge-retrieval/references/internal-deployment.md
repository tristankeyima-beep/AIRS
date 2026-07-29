# 内网部署

## 1. 创建本机配置

先将包含本 `SKILL.md` 的目录解析为绝对路径 `<SKILL_ROOT>`。不要执行 `cd`，不要依赖当前工作目录或仓库根目录。

将 `<SKILL_ROOT>/config/adp-config.template.json` 复制为 `<SKILL_ROOT>/config/adp-config.json`，保持 UTF-8 编码。

同一个 `adp-config.json` 包含 `chat_url`、`app_key`、`secret_id` 和 `secret_key` 四个字段。

当前 SSE 对接只需填写：

- `chat_url`：实际的 ADP SSE 地址。
- `app_key`：当前 SSE 调用使用的 AppKey。

`secret_id` 和 `secret_key` 可以保持为空：当前客户端不会校验或发送它们。以后内网若切换到 V3 签名接口，再直接在这个配置文件的现有字段中填写 SecretId 和 SecretKey，并按已文档化的方式增加签名适配器。

真实配置文件只能保留在内网主机；不要提交到 Git，也不要发送到聊天、日志或其他外部位置。

## 2. 运行自检

确认内网配置已填写后运行：

```bash
python3 "<SKILL_ROOT>/scripts/query_adp.py" --config "<SKILL_ROOT>/config/adp-config.json" --query-stdin
```

命令启动后，通过执行工具独立的 stdin 通道发送一行 UTF-8 自检问题，并以换行结束，例如“请检索一个已知慢病条目，并返回依据来源”。脚本收到该换行后立即执行，不等待 EOF。不得把问题插值进 shell 命令，不得使用管道或 here-document。若执行工具没有独立 stdin 通道，停止自检并提示维护人员。

检查标准输出为 UTF-8 JSON，且顶层 `ok` 为 `true`。若不是，按 `error_type` 区分：配置文件缺失，或 `chat_url` / `app_key` 缺失为“未配置”（`config`）；HTTP 401/403 为“鉴权失败”（`auth`）；网络或 SSE 等错误为“不可访问”；空结果为“检索无结果”。不要在日志中输出 AppKey 或 secret 字段。
