# 门诊慢特病 Flash Skill 拆分设计

## 目标

把现有二合一 Skill `chronic-disease-certification-qc-flash` 拆成两个可独立上传、安装、调用和升级的 Skill：

- `chronic-disease-certification-standard-flash`：只负责模式 1，即生成门诊慢特病结构化认定标准及离线可视化 HTML。
- `chronic-disease-certification-qc-flash`：只负责模式 2，即根据患者材料、认定标准和原审核结果生成审核质控 JSON 及离线 HTML。

拆分后不保留模式路由、组合模式或旧二合一兼容入口。

## 目录结构

```text
chronic-disease-certification-standard-flash/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── mode1-contract.md
│   └── output-checklist.md
└── assets/
    └── certification-template.html

chronic-disease-certification-qc-flash/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── mode2-contract.md
│   └── output-checklist.md
└── assets/
    └── qc-report-template.html
```

每个目录都是完整、独立的 Skill，不引用另一个 Skill 的文件，也不依赖仓库外的共享运行时资源。

## Skill 入口

### 认定标准 Skill

`chronic-disease-certification-standard-flash/SKILL.md` 只保留模式 1 的工作流、通用约束、安全处理和错误处理。删除模式选择、模式 2、组合请求及相关交叉说明。

界面名称和默认提示词明确表达“认定标准生成”，调用名固定为：

```text
$chronic-disease-certification-standard-flash
```

### 审核质控 Skill

`chronic-disease-certification-qc-flash/SKILL.md` 只保留模式 2 的工作流、通用约束、安全处理和错误处理。删除模式选择、模式 1、组合请求及相关交叉说明。

界面名称和默认提示词明确表达“审核质控”，调用名继续使用：

```text
$chronic-disease-certification-qc-flash
```

模式 2 沿用当前目录名称，但其含义由“二合一入口”收窄为“审核质控专用入口”。

## 契约、清单与模板

- 模式 1 Skill 只包含 `mode1-contract.md`、模式 1 专用 `output-checklist.md` 和 `certification-template.html`。
- 模式 2 Skill 只包含 `mode2-contract.md`、模式 2 专用 `output-checklist.md` 和 `qc-report-template.html`。
- 两份自检清单分别保留适用的通用检查项和本模式检查项，不出现另一个模式的字段或流程。
- 原有 JSON 字段结构、`flash-1.0` 契约、模板交互、中文状态展示、原文和分析草稿展示能力保持不变。
- 模板仍通过 `flash-data` 数据槽接收结构化 JSON；不增加 Python 或其他外部运行时脚本。

## 删除范围

删除整个开发验收工程：

```text
chronic-disease-certification-qc-flash-acceptance/
```

其中的测试、fixture、基线结果和前向结果均不迁入两个运行时 Skill。历史设计与实施文档作为迭代记录保留，不重写其历史路径。

## 验证

拆分完成后只进行轻量、非验收工程式验证：

1. 两个 Skill 分别通过 Skill 格式校验。
2. 每个 Skill 只包含五个运行时文件。
3. `SKILL.md`、`agents/openai.yaml`、契约和清单中的调用名及引用路径正确。
4. 模式 1 文件中不存在模式 2 契约或模板引用；模式 2 文件中不存在模式 1 契约或模板引用。
5. 两个 HTML 模板各自只包含一个有效的 `__FLASH_DATA_JSON__` 数据槽占位符。
6. 原有 JSON 契约和 HTML 模板内容除拆分所需路径与说明外不作业务性修改。
7. `chronic-disease-certification-qc-flash-acceptance` 不再存在。
8. Git 工作区无意外改动，`git diff --check` 通过。

## 非目标

- 不调整认定标准或审核质控的业务规则。
- 不修改模板视觉设计或交互。
- 不新增路由 Skill、共享依赖目录、脚本或验收工程。
- 不为旧的二合一调用方式提供兼容层。
