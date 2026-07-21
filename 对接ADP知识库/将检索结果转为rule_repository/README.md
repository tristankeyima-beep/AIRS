# 将检索结果转为 rule_repository

本目录按 ADP 知识库检索分支的执行顺序整理：

1. `01-提取相关性最高的知识库结果`：从知识库候选中筛选当前病种的最高相关 DOC。
2. `02-LLM-将检索结果转为rule_repository`：将检索正文转换为临时规则与逻辑树的 LLM 配置。
3. `03-将ADP提取出的rule_repository结构化`：规范化 LLM 输出并生成规则编码。
4. `04-组装certification_list`：将病种信息、规则库和逻辑树组装为完整对象。
5. `05-根据检索结果返回certification_list`：根据条件节点 `ConditionIndex` 返回原始或 ADP 组装后的对象。

每个代码节点文件夹内均包含代码和对应的代码出入参说明；LLM 节点文件夹内包含其配置说明。
