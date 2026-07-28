# 内网部署

## 1. 复制配置模板

先将包含本 `SKILL.md` 的目录解析为绝对路径 `<SKILL_ROOT>`。不要执行 `cd`，不要依赖当前工作目录或仓库根目录。

将 `<SKILL_ROOT>/config/adp-config.template.json` 复制为 `<SKILL_ROOT>/config/adp-config.json`，保持 UTF-8 编码。不要在 JSON、Python、SKILL、日志、聊天内容或命令历史中写入 AppKey。

## 2. 修改服务地址

普通部署只修改 `<SKILL_ROOT>/config/adp-config.json`：把 `chat_url` 改为实际的 ADP SSE 地址。此 SSE 方案不使用 SecretId 或 SecretKey。

仅当内网接口契约与模板不兼容时，才由维护人员按用户提供的 V3.4.1.0 文档处理例外，并将字段适配集中在 `<SKILL_ROOT>/scripts/query_adp.py` 的 `build_request` 中；不要分散修改，也不要引入 SDK 内部实现。

## 3. 安全设置 AppKey

使用系统的服务配置、密钥管理或受保护的环境注入机制，设置模板中 `app_key_env` 指定的 `ADP_APP_KEY`。不要把密钥直接输入会记录命令历史的命令行。

## 4. 运行自检

确认配置与环境变量已在目标内网环境生效后运行：

```bash
python3 "<SKILL_ROOT>/scripts/query_adp.py" --config "<SKILL_ROOT>/config/adp-config.json" --query "请检索一个已知慢病条目，并返回依据来源"
```

检查标准输出为 UTF-8 JSON，且顶层 `ok` 为 `true`。若不是，按 `error_type` 区分：配置文件或环境变量缺失为“未配置”，认证错误或 HTTP 401/403 为“鉴权失败”，网络、超时或 SSE 错误为“不可访问”，空结果为“检索无结果”。不要在日志中输出 AppKey。
