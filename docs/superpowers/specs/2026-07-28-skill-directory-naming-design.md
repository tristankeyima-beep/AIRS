# Skill 目录命名设计

## 目标

让 `SKILLS` 中每一个可交付 Skill 都成为独立的一级目录；目录名称直接表达业务能力和版本，避免以“材料管理”“完整版”等泛化分类名称遮蔽实际内容。

## 最终结构

```text
SKILLS/
├── 门诊慢特病认定标准与审核质控助手（完整版）/
│   └── chronic-disease-certification-qc/
├── 认定标准生成（Flash）/
│   └── chronic-disease-certification-standard-flash/
├── 审核质控（Flash）/
│   └── chronic-disease-certification-qc-flash/
├── 申请材料预检与补件清单（Flash）/
│   └── chronic-disease-material-precheck-flash/
├── 材料证据编目与归位（Flash）/
│   └── chronic-disease-material-catalog-flash/
├── 认定标准版本比对与影响分析（Flash）/
│   └── chronic-disease-standard-version-impact-flash/
└── 开发验证（非 Skill）/
```

内部英文目录保持不变，保证既有脚本、资源与技术标识不因展示层命名而改变。`开发验证（非 Skill）` 保留测试用途，但在名称上明确其不属于六个可交付 Skill。

## 验收

- 五个 Flash Skill 与一个完整版 Skill 均有独立一级业务目录。
- 每个 Skill 的 `SKILL.md` 和 `agents/openai.yaml` 可从其新路径读取。
- 仓库根目录不保留任何这六个 Skill 的英文目录。
- 完整版审核质控 Skill 的既有自动化测试全部通过。
