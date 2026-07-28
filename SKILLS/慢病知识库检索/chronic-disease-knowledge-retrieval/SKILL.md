---
name: chronic-disease-knowledge-retrieval
description: 当问题涉及门诊慢特病、慢病知识库、认定标准、准入条件、专家共识、临床指南、诊疗规范、知识依据、来源或版本，或自然语言问题需要从知识库取证时使用。
---

# 慢病知识库检索

1. 先判断当前问题是否需要外部知识。仅在配置或部署时读取 `references/internal-deployment.md`。
2. 保留用户的原始问题，不改写、不拆分。只调用一次：

   ```bash
   python3 scripts/query_adp.py --config config/adp-config.json --query "<原始问题>"
   ```

3. 分别读取返回 JSON 中的 `answer`、`knowledge` 和 `workflow`，不要把三者混成一个字段。
4. 由当前调用模型依据检索结果继续解释、比较或完成业务处理。来源缺失时明确说明缺失，不补造来源、标题、版本或链接。
5. 检索失败时不要依靠模型记忆编写知识依据。区分并说明：配置或鉴权错误为“未配置”，网络、超时或 SSE 错误为“不可访问”，空结果为“无结果”。
6. 将检索结果作为知识依据，不直接当作患者诊断，也不直接当作最终医保资格结论。
