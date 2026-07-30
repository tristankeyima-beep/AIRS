# 内网配置说明

## 使用前提

目标应用类型可以是 `knowledge_qa`，但还必须在 ADP 中配置为“单工作流模式”。腾讯 SDK 对 `CreateWorkflowRun` 明确要求这一点。若只是标准知识问答模式，本 Skill 会返回接口错误，不能用修改密钥的方式解决。

## 配置文件

保留模板文件，再复制一份：

```text
config/adp-config.template.json  →  config/adp-config.json
```

只修改 `adp-config.json`：

```json
{
  "api_host": "http://10.80.38.161",
  "app_id": "内网应用ID",
  "secret_id": "内网SecretId",
  "secret_key": "内网SecretKey",
  "run_env": 1,
  "region": "1",
  "service": "lke",
  "version": "2023-11-30",
  "poll_interval_seconds": 1,
  "timeout_seconds": 120
}
```

- `api_host`：私有化 ADP API 网关的协议、IP 和端口，不填写 `/adp/` 等页面路径。
- `app_id`：应用页面 URL 中的 `appid`，请求时作为 `AppBizId`。
- `secret_id`、`secret_key`：内网密钥管理页面中的 AK、SK。
- `run_env`：`0` 为测试环境，`1` 为正式环境。
- `service` 固定为 `lke`，`version` 固定为 `2023-11-30`。
- 这条调用链不使用 AppKey。

## 可选自测

配置完成后可以运行：

```bash
python3 "<SKILL_ROOT>/scripts/query_adp_workflow.py" \
  --config "<SKILL_ROOT>/config/adp-config.json" \
  --query-stdin
```

命令启动后输入一行问题并回车。该命令只用于手工检查；模型正常使用 Skill 时会自动执行。

成功结果包含 `"ok":true`、`answer` 和 `workflow`。若返回 `AuthFailure`，检查内网时间、SecretId、SecretKey、`service` 和 `version`。若返回应用模式相关错误，先确认应用是“单工作流模式”。

部署时 `tests` 文件夹可以删除；若保留测试，则同时保留 `adp-config.template.json`。实际运行只读取 `adp-config.json`。
