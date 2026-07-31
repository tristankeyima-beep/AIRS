# ADP 环境与部署

客户端严格使用接口文档规定的异步链路：`CreateWorkflowRun` 创建实例，`DescribeWorkflowRun` 使用应用 ID 与运行实例 ID 轮询。不得增加知识检索、会话、对话或管理接口。

## Profile 切换

复制 `config/adp-config.template.json` 为已被 Git 忽略的真实配置 `config/adp-config.json`。分别填写 `cloud` 与 `provincial_intranet` profile，只修改 `active_profile` 即可切换云端或省局内网；不得修改脚本、变量映射或模板来切换环境。

每个 profile 保存 `api_host`、`app_id`、`app_key`、`secret_id`、`secret_key`、`run_env`、`region`、`service`、`version`。`app_key` 按部署要求保存，但接口请求结构没有该字段，因此客户端不发送。

## 凭据与成果安全

- 真实配置只保存在被忽略的文件中，并将文件权限设置为 `0600`；提交的模板只保留空值。
- 不得把配置内容、密钥、签名头或请求体写入 stdout、stderr、应用日志、测试快照、JSON、HTML 或 Git。
- 不得在错误信息和成果物中回显密钥值、签名信息或完整患者材料。
- 云端和省局内网联调、验收均使用最小化合成数据，不使用真实患者身份信息。
