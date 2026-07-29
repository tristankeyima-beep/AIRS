from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-07-29-chronic-disease-work-planner.md"
)
DESIGN_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-07-29-chronic-disease-work-planner-design.md"
)
SKILL_ROOT = (
    ROOT
    / "SKILLS"
    / "门诊慢特病工作规划与任务编排"
    / "chronic-disease-work-planner"
)
SAFEGUARD_INVARIANT_SENTENCES = (
    (
        "立即且不可跳过",
        "安全门是每轮处理的第 0 步，必须立即执行，不得延后或跳过。",
    ),
    (
        "早于所有处理",
        "安全门必须发生在输入盘点、内容复述、澄清提问、工作计划生成或更新、"
        "摘要或日志记录、下游调用、发送或上传之前。",
    ),
    (
        "仅输出脱敏告警",
        "命中疑似敏感凭据后，本轮只能输出不含具体值的通用脱敏告警，"
        "不得输出其他内容。",
    ),
)


def read(relative_path):
    return (SKILL_ROOT / relative_path).read_text(encoding="utf-8")


def extract_markdown_h2_section(content, title):
    heading = f"## {title}"
    if content.startswith(heading):
        section_start = 0
    else:
        section_start = content.index(f"\n{heading}") + 1

    next_section = content.find(
        "\n## ",
        section_start + len(heading),
    )
    if next_section == -1:
        return content[section_start:]
    return content[section_start:next_section]


def extract_markdown_h3_section(content, title):
    heading = f"### {title}"
    if content.startswith(heading):
        section_start = 0
    else:
        section_start = content.index(f"\n{heading}") + 1

    next_sections = [
        position
        for position in (
            content.find(
                "\n### ",
                section_start + len(heading),
            ),
            content.find(
                "\n## ",
                section_start + len(heading),
            ),
        )
        if position != -1
    ]
    if not next_sections:
        return content[section_start:]
    next_section = min(next_sections)
    return content[section_start:next_section]


def extract_plan_task(content, task_number):
    task_start = f"### Task {task_number}:"
    section = content.split(task_start, maxsplit=1)[1]
    next_task = f"### Task {task_number + 1}:"
    if next_task in section:
        return section.split(next_task, maxsplit=1)[0]
    return section


TRIGGER_CAPABILITIES = (
    "知识检索",
    "标准生成",
    "材料编目",
    "材料预检",
    "版本比对",
    "审核质控",
)


def assert_regex_sequence(test_case, label, content, patterns):
    cursor = 0
    for pattern in patterns:
        match = re.search(pattern, content[cursor:], flags=re.DOTALL)
        test_case.assertIsNotNone(
            match,
            f"{label}: 顺序契约缺少 {pattern}",
        )
        cursor += match.end()


def assert_trigger_section(test_case, label, section):
    for capability in TRIGGER_CAPABILITIES:
        test_case.assertIn(
            capability,
            section,
            f"{label}: 缺少能力 {capability}",
        )
    test_case.assertRegex(
        section,
        r"明确要求.*制定(?:工作)?计划.*拆解任务.*安排步骤",
        f"{label}: 明确规划请求未直接触发",
    )
    test_case.assertRegex(
        section,
        r"(?:两项及以上(?:（含两项）)?|两项以上|两个或以上)",
        f"{label}: 未锁定任意两项即触发",
    )
    for contradiction in (
        r"(?:资料较多|大量资料|大量内容)"
        r"(?:即可|可以|应当|必须|一律|会|将|无条件)"
        r"(?:无条件)?(?:触发|进入)",
        r"明确要求.*(?:制定|拆解|安排).*(?:不触发|不使用规划助手)",
        r"(?:单一明确任务|指定能力).*即使.*明确要求.*"
        r"(?:不触发|直接办理)",
        r"(?:两项及以上|两项以上|任意两项|两个或以上)"
        r".{0,80}(?:不触发|不使用规划助手)",
    ):
        test_case.assertNotRegex(
            section,
            contradiction,
            f"{label}: 出现相反触发语义 {contradiction}",
        )
    heavy_material_lines = [
        line
        for line in section.splitlines()
        if re.search(r"资料较多|大量资料|大量内容", line)
    ]
    test_case.assertTrue(
        heavy_material_lines,
        f"{label}: 缺少资料较多入口",
    )
    for line in heavy_material_lines:
        test_case.assertRegex(
            line,
            r"未说明期望成果|未说明希望得到什么成果|"
            r"没有说明希望得到什么成果",
            f"{label}: 资料较多入口缺少未说明期望成果限定: {line}",
        )
    test_case.assertRegex(
        section,
        r"(?:无法判断|信息不足以判断|暂时无法判断|尚无法判断)"
        r".*?(?:能力|Skill)",
        f"{label}: 缺少无法判断具体能力入口",
    )


def assert_standard_section(test_case, label, chapters):
    test_case.assertEqual(
        set(chapters),
        {"完全未提供", "已提供未确认", "已确认", "标准修改"},
        f"{label}: 标准状态章节不完整",
    )

    missing = chapters["完全未提供"]
    assert_regex_sequence(
        test_case,
        f"{label}完全未提供",
        missing,
        (
            r"(?:完全未提供|没有提供|手头没有).*?标准",
            r"(?:知识库检索|检索候选|检索.*候选)",
            r"(?:用户确认|请用户确认|确认候选|"
            r"补充修正|补充或修正|补充或修订|"
            r"补充、确认或修订)",
        ),
    )

    unconfirmed = chapters["已提供未确认"]
    assert_regex_sequence(
        test_case,
        f"{label}已提供未确认",
        unconfirmed,
        (
            r"(?:已提供但未确认|已经提供标准但未确认|"
            r"已提供.*?尚未确认|标准已提供.*?未确认)",
            r"(?:先|首先).*?(?:确认|请用户确认)",
            r"(?:不自动检索|不能自动检索|不会自动检索|"
            r"仅在.*?要求.*?才.*?检索|只有.*?要求.*?才.*?检索)",
        ),
    )
    test_case.assertNotRegex(
        unconfirmed,
        r"(?:已提供但未确认|已提供.*尚未确认|"
        r"标准已提供.*未确认|此状态下|确认前|未确认时)"
        r".{0,120}(?<!不)(?<!不应)(?<!不可)(?<!不会)"
        r"(?<!不能)(?<!不得)自动检索",
        f"{label}: 未确认标准不得自动检索",
    )

    confirmed = chapters["已确认"]
    assert_regex_sequence(
        test_case,
        f"{label}已确认",
        confirmed,
        (
            r"已确认标准",
            r"通用准备清单",
            r"(?:引导|邀请|询问).*?"
            r"(?:材料预检|预检|上传.*?材料)",
        ),
    )

    standard_change = chapters["标准修改"]
    assert_regex_sequence(
        test_case,
        f"{label}标准修改",
        standard_change,
        (
            r"(?:确认|提供并确认).*?现行标准",
            r"拟修改内容",
            r"适用范围",
            r"(?:业务原因|原因或目标|业务原因或目标)",
            r"检索",
            r"(?:生成|形成).*?拟修订(?:版|标准)",
            r"(?:用户确认|由用户确认|取得用户确认|"
            r"请您确认|请用户确认)",
            r"(?:版本影响|版本比对|版本比较|"
            r"比较现行版|比较现行版本)",
            r"(?:可选|可邀请).*?(?:真实)?患者材料",
        ),
    )
    test_case.assertNotRegex(
        standard_change,
        r"先检索.{0,160}(?:再|然后).*"
        r"(?:确认|询问).*拟修改内容",
        f"{label}: 修改目标应先确认再检索",
    )


def assert_cross_document_standard_contract(test_case, sections):
    test_case.assertEqual(
        set(sections),
        {"设计稿", "实施计划", "运行时路由", "使用说明"},
    )
    for label, section in sections.items():
        assert_standard_section(test_case, label, section)


def assert_pause_section(test_case, label, section):
    assert_regex_sequence(
        test_case,
        f"{label}独立确认恢复",
        section,
        (
            r"(?:独立确认步骤|独立的确认步骤|"
            r"确认采用的认定标准.*?暂停)",
            r"(?:确认步骤|该确认步骤).*?"
            r"⏸️(?:\s*→\s*|.{0,12}?变为\s*)✅",
            r"(?:下一执行步骤|下一步骤).*?"
            r"⬜(?:\s*→\s*|.{0,12}?变为\s*)⏳",
        ),
    )
    assert_regex_sequence(
        test_case,
        f"{label}能力内部恢复",
        section,
        (
            r"(?:执行中的能力|同一.{0,30}?步骤|预检步骤)",
            r"(?:当前|同一).*?步骤.*?"
            r"⏸️(?:\s*→\s*|.{0,12}?变(?:回|为)\s*)⏳",
            r"(?:能力内部暂停点|下游能力内部暂停点|"
            r"继续当前能力|从暂停位置继续)",
            r"(?:正式成果|JSON.*?HTML).*?"
            r"(?:⏳(?:\s*→\s*|.{0,12}?变为\s*)✅|才.*?✅)",
        ),
    )
    for pattern in (
        r"取消",
        r"(?:接受)?部分交付",
        r"不可恢复失败",
        r"(?:最终状态收敛|终止并收敛|"
        r"不得留下|不得遗留|无.*遗留|全部.*❌)",
    ):
        test_case.assertRegex(
            section,
            pattern,
            f"{label}: 终止收敛缺少 {pattern}",
        )
    for contradiction in (
        r"(?:执行中的能力|同一.*步骤).{0,160}"
        r"⏸️\s*→\s*✅",
        r"(?:内部暂停|暂停位置).{0,160}"
        r"(?:直接进入下一步|可以提前进入下一步|"
        r"可提前进入下一步|会提前进入下一步|"
        r"将提前进入下一步)",
        r"(?:执行中的能力|能力内部|内部暂停).{0,160}"
        r"(?:用户回答|回答后).{0,60}"
        r"(?:即可|可以|直接).{0,30}"
        r"(?:标记|视为|算作)(?:已)?完成",
        r"(?:取消|部分交付|不可恢复失败).{0,160}"
        r"(?:继续执行|保持.*(?:⏳|⏸️|⬜))",
    ):
        test_case.assertNotRegex(
            section,
            contradiction,
            f"{label}: 出现相反暂停语义 {contradiction}",
        )


def assert_cross_document_pause_contract(test_case, sections):
    test_case.assertEqual(
        set(sections),
        {"设计稿", "实施计划", "运行时执行", "使用说明"},
    )
    for label, section in sections.items():
        assert_pause_section(test_case, label, section)


def assert_authorization_section(test_case, label, section):
    for pattern in (
        r"已确认计划范围内",
        r"省局内部应用",
        r"(?:不覆盖|不能覆盖).*其他外部服务",
        r"(?:不覆盖|不能覆盖).*计划外发送",
        r"(?:不绕过|不能覆盖或绕过).*敏感凭据",
        r"(?:业务确认门.*(?:仍保留|仍必须|不能绕过)|"
        r"认定标准选择.*仍必须由用户确认)",
    ):
        test_case.assertRegex(
            section,
            pattern,
            f"{label}: {pattern}",
        )
    for contradiction in (
        r"(?:授权|确认).{0,80}(?:可以|可|允许)"
        r"(?:覆盖|调用).*其他外部服务",
        r"(?:授权|确认).{0,80}(?:可以|可|允许)"
        r"(?:覆盖|进行).*计划外发送",
        r"(?:授权|确认).{0,80}(?:可以|可|允许)"
        r"(?:覆盖|绕过|关闭|跳过).*敏感凭据停止门",
        r"业务确认门.*(?:不再保留|可以绕过)",
    ):
        test_case.assertNotRegex(
            section,
            contradiction,
            f"{label}: 出现相反授权语义 {contradiction}",
        )


def assert_cross_document_authorization_contract(test_case, sections):
    test_case.assertEqual(
        set(sections),
        {"设计稿", "实施计划", "运行时执行", "使用说明"},
    )
    for label, section in sections.items():
        assert_authorization_section(test_case, label, section)


def assert_sensitive_credential_contract(test_case, content, relative_path):
    for invariant_name, invariant_sentence in SAFEGUARD_INVARIANT_SENTENCES:
        test_case.assertIn(
            invariant_sentence,
            content,
            f"{relative_path}: 不可变安全句：{invariant_name}",
        )

    literal_contracts = {
        "每轮重新检查": "每轮",
        "收到新消息或附件": "收到新消息或附件",
        "第 0 步": "第 0 步",
        "API 密钥": "API 密钥",
        "访问令牌": "访问令牌",
        "Token": "Token",
        "Cookie": "Cookie",
        "授权头": "授权头",
        "账号密码": "账号密码",
        "私密系统提示": "私密系统提示",
        "秘密配置": "秘密配置",
        "立即停止": "立即停止",
        "本轮只能输出": "本轮只能输出",
        "通用脱敏告警": "通用脱敏告警",
        "不得复制具体值": "不得把具体值复制",
        "不得继续生成或更新计划": "不得继续生成或更新计划",
        "不得继续调用": "不得继续调用",
        "重新确认材料范围": "重新确认材料范围",
        "规划助手层执行": "规划助手层",
        "内网授权不能覆盖或绕过": "不能覆盖或绕过",
    }
    regex_contracts = {
        "不得回显": r"不得[^。\n]*回显",
        "不得记录": r"不得[^。\n]*记录",
        "不得转发": r"不得[^。\n]*转发",
        "重新确认当前计划": r"重新确认[^。\n]*当前计划",
        "不能只依赖下游": r"不能(?:仅|只)依赖下游",
    }

    for contract_name, required_term in literal_contracts.items():
        test_case.assertIn(
            required_term,
            content,
            f"{relative_path}: {contract_name}",
        )
    for contract_name, required_pattern in regex_contracts.items():
        test_case.assertRegex(
            content,
            required_pattern,
            f"{relative_path}: {contract_name}",
        )

    pre_processing_sentences = [
        sentence
        for sentence in content.split("。")
        if "输入盘点" in sentence
    ]
    test_case.assertEqual(
        len(pre_processing_sentences),
        1,
        f"{relative_path}: 必须用一个前置处理句绑定所有第 0 步对象",
    )
    pre_processing_sentence = pre_processing_sentences[0]
    for required_term in (
        "输入盘点",
        "内容复述",
        "澄清提问",
        "工作计划生成或更新",
        "摘要或日志记录",
        "下游调用",
        "发送或上传",
        "之前",
    ):
        test_case.assertIn(
            required_term,
            pre_processing_sentence,
            f"{relative_path}: 第 0 步必须早于{required_term}",
        )

    no_copy_sentences = [
        sentence
        for sentence in content.split("。")
        if "不得把具体值复制" in sentence
    ]
    test_case.assertEqual(
        len(no_copy_sentences),
        1,
        f"{relative_path}: 必须集中声明具体值不得进入用户态或内部记录",
    )
    no_copy_sentence = no_copy_sentences[0]
    for prohibited_target in (
        "计划",
        "摘要",
        "问题",
        "日志",
        "拟传递内容",
    ):
        test_case.assertIn(
            prohibited_target,
            no_copy_sentence,
            f"{relative_path}: 具体值不得复制进{prohibited_target}",
        )


def assert_no_inline_markdown_link_examples(test_case, content):
    test_case.assertNotIn(
        "](",
        content,
        "markdown-plan-template.md 不得包含任何可复制的 Markdown 内联链接示例",
    )


class WorkPlannerSkillTests(unittest.TestCase):
    def test_markdown_h2_section_stops_before_the_next_h2(self):
        content = (
            "# 文档\n"
            "\n"
            "## 测试用例\n"
            "\n"
            "章节内文字\n"
            "\n"
            "## 后续章节\n"
            "\n"
            "章节外文字\n"
        )

        section = extract_markdown_h2_section(content, "测试用例")

        self.assertIn("章节内文字", section)
        self.assertNotIn("后续章节", section)
        self.assertNotIn("章节外文字", section)

    def test_required_files_exist(self):
        required_files = (
            "SKILL.md",
            "使用说明.md",
            "agents/openai.yaml",
            "references/intent-routing.md",
            "references/continuous-execution.md",
            "references/markdown-plan-template.md",
        )

        for relative_path in required_files:
            self.assertTrue(
                (SKILL_ROOT / relative_path).is_file(),
                relative_path,
            )

    def test_skill_declares_trigger_modes_and_question_limit(self):
        content = read("SKILL.md")
        required_terms = (
            "name: chronic-disease-work-planner",
            "只制定计划",
            "自动连续执行",
            "二至三个",
            "患者申请材料",
            "病种认定标准",
            "审核结果",
            "政策与临床依据",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)
        self.assertNotIn("一至三个", content)

    def test_runtime_guided_interaction_contract(self):
        runtime_skill = read("SKILL.md")
        intent_routing = read("references/intent-routing.md")
        plan_template = read("references/markdown-plan-template.md")
        usage = read("使用说明.md")
        design = DESIGN_PATH.read_text(encoding="utf-8")
        plan = PLAN_PATH.read_text(encoding="utf-8")

        for label, content in {
            "运行时 Skill": runtime_skill,
            "意图路由": intent_routing,
        }.items():
            with self.subTest(label=label):
                for required_term in (
                    "意图不确定",
                    "关键输入不足",
                    "热情、友好、温暖",
                    "推荐",
                    "二至三个关键问题",
                    "可选路径",
                    "各自产物",
                ):
                    self.assertIn(required_term, content, required_term)

        for required_term in (
            "详细澄清问题",
            "计划之外单独提问",
            "问题摘要",
            "⏸️ 正在确认",
        ):
            self.assertIn(required_term, plan_template, required_term)

        for required_term in (
            "热情、友好、温暖",
            "推荐",
            "二至三个关键问题",
            "可选路径",
            "各自产物",
        ):
            self.assertIn(required_term, usage, required_term)

        for label, content in {
            "运行时 Skill": runtime_skill,
            "使用说明": usage,
            "设计稿": design,
            "实施计划": plan,
        }.items():
            with self.subTest(label=label):
                self.assertNotIn("一至三个", content)

        self.assertIn(
            "单一明确任务或指定具体能力",
            runtime_skill,
        )

    def test_skill_narrows_trigger_boundary(self):
        content = read("SKILL.md")
        required_terms = (
            "在门诊慢特病业务中",
            "未说明期望成果",
            "两项以上",
            "单一明确任务",
            "指定具体能力",
            "改写、排版",
            "非门诊慢特病任务",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_execution_entry_includes_exactly_two_capabilities(self):
        content = read("SKILL.md")
        execution_entry = extract_markdown_h2_section(content, "执行入口")

        self.assertIn(
            "涉及两项及以上环节（含两项）",
            execution_entry,
        )

    def test_explicit_planning_request_overrides_default_non_trigger(self):
        content = read("SKILL.md")
        required_terms = (
            "默认不自动触发",
            "明确要求制定计划",
            "拆解任务",
            "安排步骤",
            "单一明确任务或指定具体能力",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_routing_reference_names_all_six_capabilities(self):
        content = read("references/intent-routing.md")
        required_terms = (
            "chronic-disease-knowledge-retrieval",
            "chronic-disease-certification-standard-flash",
            "chronic-disease-material-catalog-flash",
            "chronic-disease-material-precheck-flash",
            "chronic-disease-standard-version-impact-flash",
            "chronic-disease-certification-qc-flash",
            "没有原审核结果",
            "不得自动采用",
            "不得自动成为医保准入条件",
            "标准修改",
            "拟修订版",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_routing_distinguishes_standard_states_and_review_intents(self):
        content = read("references/intent-routing.md")
        required_terms = (
            "完全未提供标准",
            "已提供但未确认",
            "不自动检索",
            "已确认标准",
            "现行有效性",
            "临床或业务合理性",
            "能否配置",
            "现有患者材料能否覆盖规则",
            "拟修改内容",
            "适用范围",
            "业务原因或目标",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_continuous_execution_keeps_business_confirmation_gates(self):
        content = read("references/continuous-execution.md")
        required_terms = (
            "完整工作计划",
            "认定标准选择",
            "规则解释",
            "材料完整性",
            "版本顺序",
            "暂停",
            "恢复",
            "重新规划",
            "省局内网",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_planner_level_sensitive_credential_gate_stops_all_dispatch(self):
        safety_documents = {
            "SKILL.md": read("SKILL.md"),
            "references/continuous-execution.md": read(
                "references/continuous-execution.md"
            ),
        }
        for relative_path, document in safety_documents.items():
            with self.subTest(relative_path=relative_path):
                safety_gate = extract_markdown_h2_section(
                    document,
                    "敏感凭据停止门",
                )
                assert_sensitive_credential_contract(
                    self,
                    safety_gate,
                    relative_path,
                )

        core = safety_documents["SKILL.md"]
        self.assertLess(
            core.index("## 敏感凭据停止门"),
            core.index("## 执行入口"),
        )

        continuous = safety_documents["references/continuous-execution.md"]
        safety_gate_position = continuous.index("## 敏感凭据停止门")
        for later_section in (
            "## 模式选择与执行授权",
            "## 只制定计划",
            "## 自动连续执行",
        ):
            self.assertLess(
                safety_gate_position,
                continuous.index(later_section),
                later_section,
            )

    def test_sensitive_credential_checker_rejects_negated_invariants(self):
        safety_gate = extract_markdown_h2_section(
            read("SKILL.md"),
            "敏感凭据停止门",
        )
        negating_mutations = (
            (
                "必须改成可以",
                "必须立即执行",
                "可以稍后执行",
                "立即且不可跳过",
            ),
            (
                "不得延后改成无需立即",
                "不得延后或跳过",
                "无需立即执行",
                "立即且不可跳过",
            ),
            (
                "只能告警改成还可输出其他内容",
                "本轮只能输出不含具体值的通用脱敏告警，不得输出其他内容",
                "本轮还可输出其他内容",
                "仅输出脱敏告警",
            ),
        )

        for mutation_name, original, replacement, failed_invariant in negating_mutations:
            with self.subTest(mutation_name=mutation_name):
                self.assertIn(original, safety_gate, mutation_name)
                mutated_safety_gate = safety_gate.replace(
                    original,
                    replacement,
                    1,
                )
                with self.assertRaisesRegex(
                    AssertionError,
                    failed_invariant,
                ):
                    assert_sensitive_credential_contract(
                        self,
                        mutated_safety_gate,
                        "SKILL.md",
                    )

    def test_markdown_plan_has_visual_states_and_real_links_only(self):
        content = read("references/markdown-plan-template.md")
        required_terms = (
            "✅",
            "❌",
            "⏳",
            "⏸️",
            "⬜",
            "本次交付",
            "实际返回",
            "计划之外单独提问",
            "不得伪造链接",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_execution_mode_selection_precedes_authorization(self):
        required_terms = (
            "先展示完整工作计划",
            "选择执行方式不等于授权执行",
            "计划未变化",
            "不重复确认",
        )

        for relative_path in (
            "SKILL.md",
            "references/continuous-execution.md",
        ):
            content = read(relative_path)
            for required_term in required_terms:
                self.assertIn(
                    required_term,
                    content,
                    f"{relative_path}: {required_term}",
                )

    def test_continuous_execution_defines_state_transitions_and_end_states(self):
        content = read("references/continuous-execution.md")
        required_terms = (
            "⬜ → ⏳",
            "⏳ → ✅",
            "⏳ → ⏸️",
            "用户取消",
            "接受部分交付",
            "不可恢复失败",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_markdown_plan_separates_planned_and_executed_deliverables(self):
        content = read("references/markdown-plan-template.md")
        required_terms = (
            "任务目标",
            "已具备内容",
            "需提前准备",
            "依赖",
            "⬜ 计划执行后生成",
            "知识库未返回来源地址",
            "检索无结果",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

        planning_example = content.split(
            "### 计划模式最小示例",
            maxsplit=1,
        )[1].split(
            "### 自动执行模式最小示例",
            maxsplit=1,
        )[0]
        self.assertNotIn("❌", planning_example)
        self.assertNotIn("chronic-disease-", content)

    def test_planner_markdown_and_downstream_file_delivery_boundaries(self):
        for relative_path in (
            "SKILL.md",
            "references/intent-routing.md",
            "references/markdown-plan-template.md",
        ):
            content = read(relative_path)
            for required_term in (
                "工作计划只在对话中以 Markdown 展示",
                "不生成规划 JSON 或规划 HTML",
            ):
                self.assertIn(
                    required_term,
                    content,
                    f"{relative_path}: {required_term}",
                )

        routing = read("references/intent-routing.md")
        flash_skill_ids = (
            "chronic-disease-certification-standard-flash",
            "chronic-disease-material-catalog-flash",
            "chronic-disease-material-precheck-flash",
            "chronic-disease-standard-version-impact-flash",
            "chronic-disease-certification-qc-flash",
        )
        for skill_id in flash_skill_ids:
            row = next(
                line
                for line in routing.splitlines()
                if f"`{skill_id}`" in line
            )
            self.assertIn("JSON", row, skill_id)
            self.assertIn("HTML", row, skill_id)

        delivery_contract = (
            read("SKILL.md")
            + "\n"
            + read("references/markdown-plan-template.md")
        )
        for required_term in (
            "JSON 和 HTML 分别列出",
            "分别使用下游或平台实际返回的真实链接",
            "知识库检索没有固定文件",
            "实际来源链接",
            "不得伪造",
        ):
            self.assertIn(required_term, delivery_contract, required_term)

    def test_plan_only_mode_updates_plan_before_stopping(self):
        content = read("references/continuous-execution.md")
        required_terms = (
            "先把计划中的执行方式更新为“只制定计划”",
            "当前状态更新为“计划已制定”",
            "未来步骤和成果保持 `⬜`",
            "然后停止",
            "不调用下游能力",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_final_delivery_reference_contains_no_inline_markdown_link_syntax(self):
        content = read("references/markdown-plan-template.md")
        final_delivery_section = extract_markdown_h2_section(
            content,
            "最终交付模板",
        )

        assert_no_inline_markdown_link_examples(self, final_delivery_section)
        self.assertIn("本参考不提供占位链接示例", final_delivery_section)
        self.assertIn("没有实际地址时输出纯文本状态", final_delivery_section)

    def test_final_delivery_link_check_rejects_empty_and_nested_examples(self):
        content = read("references/markdown-plan-template.md")
        final_delivery_section = extract_markdown_h2_section(
            content,
            "最终交付模板",
        )

        for inline_link_example in (
            "[](地址)",
            "[名称]()",
            "[外层 [内层]](地址)",
        ):
            with self.subTest(inline_link_example=inline_link_example):
                with self.assertRaisesRegex(AssertionError, "不得包含"):
                    assert_no_inline_markdown_link_examples(
                        self,
                        f"{final_delivery_section}\n{inline_link_example}",
                    )

    def test_planning_example_closes_standard_confirmation_dependencies(self):
        content = read("references/markdown-plan-template.md")
        planning_example = content.split(
            "### 计划模式最小示例",
            maxsplit=1,
        )[1].split(
            "### 自动执行模式最小示例",
            maxsplit=1,
        )[0]
        task_progress = planning_example.split(
            "## 一、任务进度",
            maxsplit=1,
        )[1].split(
            "## 二、当前状态",
            maxsplit=1,
        )[0]

        self.assertIn("确认采用的认定标准", task_progress)
        self.assertEqual(task_progress.count("| ⬜ 计划执行 |"), 3)
        self.assertIn(
            "| 3 | 生成结构化标准 | 认定标准生成 | 步骤 2 的确认结果 |",
            task_progress,
        )
        self.assertNotIn("❌", planning_example)

    def test_paused_execution_resumes_the_correct_step(self):
        content = read("references/continuous-execution.md")
        required_terms = (
            "独立确认步骤",
            "执行中的能力",
            "当前步骤 ⏸️ → ⏳",
            "取得正式成果后",
            "从下游能力内部暂停点继续",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_automatic_example_confirms_standard_and_preserves_lookup_errors(self):
        content = read("references/markdown-plan-template.md")
        automatic_example = content.split(
            "### 自动执行模式最小示例",
            maxsplit=1,
        )[1].split(
            "## 最终交付模板",
            maxsplit=1,
        )[0]

        required_example_terms = (
            "> 任务目标：检索并生成糖尿病结构化认定标准",
            "> 已具备内容：病种名称、适用地区、政策时间范围",
            "> 需提前准备：确认本次采用的认定标准",
            "确认采用的认定标准",
            "⏸️ 等待确认",
        )
        for required_term in required_example_terms:
            self.assertIn(required_term, automatic_example, required_term)

        task_progress = automatic_example.split(
            "## 一、任务进度",
            maxsplit=1,
        )[1].split(
            "## 二、当前状态",
            maxsplit=1,
        )[0]
        lookup_row = next(
            line
            for line in task_progress.splitlines()
            if "| 1 | 检索认定标准 |" in line
        )
        self.assertNotIn("患者申请材料", automatic_example)
        for policy_locator in ("病种", "地区", "时间范围"):
            self.assertIn(policy_locator, lookup_row, policy_locator)

        self.assertLess(
            task_progress.index("检索认定标准"),
            task_progress.index("确认采用的认定标准"),
        )
        self.assertLess(
            task_progress.index("确认采用的认定标准"),
            task_progress.index("生成结构化标准"),
        )

        required_error_terms = (
            "未配置",
            "鉴权失败",
            "不可访问",
            "不得归并为“检索无结果”",
        )
        for required_term in required_error_terms:
            self.assertIn(required_term, content, required_term)

    def test_skill_preserves_business_boundaries(self):
        content = read("SKILL.md")
        required_terms = (
            "不输出最终医保资格结论",
            "不机械调用全部",
            "不替用户确认",
            "详细澄清问题不得写入工作计划",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_usage_guide_preserves_execution_failure_paths(self):
        content = read("使用说明.md")
        required_terms = (
            "可恢复失败",
            "不可恢复失败",
            "重大重新规划",
            "重新确认",
        )

        for required_term in required_terms:
            self.assertIn(required_term, content, required_term)

    def test_usage_guide_defines_visual_status_contract(self):
        content = read("使用说明.md")
        status_section = content.split(
            "## 计划展示说明",
            maxsplit=1,
        )[1].split(
            "\n## ",
            maxsplit=1,
        )[0]
        status_lines = {
            icon: next(
                line
                for line in status_section.splitlines()
                if line.startswith(f"- {icon} ")
            )
            for icon in ("✅", "❌", "⏳", "⏸️", "⬜")
        }

        self.assertIn("已完成", status_lines["✅"])
        self.assertIn("取得实际成果", status_lines["✅"])
        self.assertIn("未完成或执行失败", status_lines["❌"])
        self.assertIn("进行中", status_lines["⏳"])
        self.assertIn("正在办理", status_lines["⏳"])
        self.assertIn("等待确认、补充或恢复", status_lines["⏸️"])
        self.assertIn("尚未开始", status_lines["⬜"])
        self.assertIn("只制定计划", status_lines["⬜"])
        self.assertIn("计划执行", status_lines["⬜"])
        for required_term in (
            "自动执行结束时（包括正常完成或提前终止）",
            "不得遗留",
            "⏳",
            "⏸️",
            "⬜",
            "计划模式",
            "未来步骤和成果",
            "保持 ⬜",
            "不得标为 ❌",
            "用户取消",
            "接受部分交付",
        ):
            self.assertIn(required_term, status_section, required_term)

    def test_design_and_plan_use_one_execution_authorization_order(self):
        canonical_flow = (
            "展示完整工作计划 → 用户选择执行方式 → "
            "选择自动连续执行后明确确认按当前计划开始 → 开始执行"
        )
        documents = {
            "设计稿执行模式": extract_markdown_h2_section(
                DESIGN_PATH.read_text(encoding="utf-8"),
                "8. 两种执行模式",
            ),
            "实施计划 Task 4": PLAN_PATH.read_text(encoding="utf-8").split(
                "### Task 4:",
                maxsplit=1,
            )[1].split(
                "### Task 5:",
                maxsplit=1,
            )[0],
        }

        for label, section in documents.items():
            with self.subTest(label=label):
                self.assertIn(canonical_flow, section)
                display_position = section.index("展示完整工作计划")
                selection_position = section.index(
                    "用户选择执行方式",
                    display_position,
                )
                confirmation_position = section.index(
                    "明确确认按当前计划开始",
                    selection_position,
                )
                execution_position = section.index(
                    "开始执行",
                    confirmation_position,
                )
                self.assertLess(display_position, selection_position)
                self.assertLess(selection_position, confirmation_position)
                self.assertLess(confirmation_position, execution_position)
                self.assertIn("选择模式不等于授权执行", section)
                self.assertIn("计划未变化", section)
                self.assertIn("不重复展示", section)
                self.assertIn("不重复确认", section)
                self.assertIn("计划已制定", section)
                self.assertIn("不调用下游", section)
                for reversed_flow in (
                    "用户选择“自动连续执行”后，展示完整工作计划",
                    "用户选择自动连续执行。\n2. 展示完整工作计划",
                ):
                    self.assertNotIn(reversed_flow, section)

    def test_design_and_plan_place_sensitive_gate_before_inputs_and_planning(
        self,
    ):
        design = DESIGN_PATH.read_text(encoding="utf-8")
        self.assertIn("## 2.1 敏感凭据第 0 步停止门", design)
        design_gate = extract_markdown_h2_section(
            design,
            "2.1 敏感凭据第 0 步停止门",
        )
        assert_sensitive_credential_contract(
            self,
            design_gate,
            "设计稿安全门",
        )
        design_gate_position = design.index(
            "## 2.1 敏感凭据第 0 步停止门"
        )
        for later_heading in (
            "## 4. 四类关键业务输入",
            "## 5. 触发规则",
            "## 6. 面向非专业用户的交互原则",
            "## 8. 两种执行模式",
        ):
            self.assertLess(
                design_gate_position,
                design.index(later_heading),
                later_heading,
            )
        self.assertNotIn("## 7A. 敏感凭据第 0 步停止门", design)

        plan = PLAN_PATH.read_text(encoding="utf-8")
        task_four = plan.split(
            "### Task 4:",
            maxsplit=1,
        )[1].split(
            "### Task 5:",
            maxsplit=1,
        )[0]
        self.assertIn("## 敏感凭据第 0 步停止门", task_four)
        plan_gate = task_four.split(
            "## 敏感凭据第 0 步停止门",
            maxsplit=1,
        )[1].split(
            "\n## 只制定计划",
            maxsplit=1,
        )[0]
        assert_sensitive_credential_contract(
            self,
            plan_gate,
            "实施计划 Task 4 安全门",
        )
        self.assertLess(
            task_four.index("## 敏感凭据第 0 步停止门"),
            task_four.index("## 只制定计划"),
        )
        for required_test_contract in (
            "安全门位置早于模式与计划流程",
            "test_design_and_plan_place_sensitive_gate_before_inputs_and_planning",
            "每轮新消息或附件",
            "命中后只输出通用脱敏告警",
            "清理后重新确认材料范围和当前计划",
            "内网授权不能绕过",
        ):
            self.assertIn(
                required_test_contract,
                task_four,
                required_test_contract,
            )
        task_four_run_command = task_four.split(
            "Run:",
            maxsplit=1,
        )[1].split(
            "Expected:",
            maxsplit=1,
        )[0]
        for test_method in (
            "test_continuous_execution_keeps_business_confirmation_gates",
            "test_markdown_plan_has_visual_states_and_real_links_only",
            "test_design_and_plan_place_sensitive_gate_before_inputs_and_planning",
        ):
            self.assertIn(test_method, task_four_run_command, test_method)
        self.assertIn("Expected: 3 tests PASS.", task_four)

        design_test_strategy = design.split(
            "## 21. 测试策略",
            maxsplit=1,
        )[1].split(
            "\n## 22. ",
            maxsplit=1,
        )[0]
        for required_test_contract in (
            "每轮第 0 步",
            "早于输入盘点、内容复述、澄清提问和计划",
            "只输出通用脱敏告警",
            "清理后重新确认材料范围和当前计划",
            "内网授权不能绕过",
        ):
            self.assertIn(
                required_test_contract,
                design_test_strategy,
                required_test_contract,
            )

    def test_design_plan_example_keeps_all_later_steps_unstarted_at_pause(
        self,
    ):
        design = DESIGN_PATH.read_text(encoding="utf-8")
        example = design.split(
            "### 17.2 计划示例",
            maxsplit=1,
        )[1].split(
            "\n## 18. 澄清问题与工作计划分离",
            maxsplit=1,
        )[0]
        self.assertIn("> 当前进度：1 / 5", example)
        task_table = example.split(
            "## 一、任务进度",
            maxsplit=1,
        )[1].split(
            "## 二、当前状态",
            maxsplit=1,
        )[0]
        task_rows = [
            line
            for line in task_table.splitlines()
            if re.match(r"^\|\s*\d+\s*\|", line)
        ]
        first_paused_index = next(
            index
            for index, row in enumerate(task_rows)
            if "⏸️" in row
        )
        later_rows = task_rows[first_paused_index + 1 :]
        self.assertTrue(later_rows)
        for row in later_rows:
            self.assertIn("⬜", row, row)
            self.assertNotIn("✅", row, row)

        delivery_table = example.split(
            "## 三、交付物汇总",
            maxsplit=1,
        )[1]
        for deliverable in (
            "认定标准 JSON 数据文件",
            "认定标准离线页面",
            "材料编目 JSON 数据文件",
            "材料编目离线页面",
            "材料预检 JSON 数据文件",
            "材料预检离线页面",
        ):
            self.assertIn(deliverable, delivery_table, deliverable)
        self.assertNotIn("| 结构化认定标准 |", delivery_table)
        self.assertNotIn("| 材料预检与补件清单 |", delivery_table)
        self.assertNotIn("](", delivery_table)

    def test_design_and_plan_keep_future_states_planned_while_waiting(self):
        design = DESIGN_PATH.read_text(encoding="utf-8")
        plan = PLAN_PATH.read_text(encoding="utf-8")
        sections = {
            "设计稿计划展示与交付": (
                design.split(
                    "## 17. Markdown 工作计划",
                    maxsplit=1,
                )[1].split(
                    "\n## 18. ",
                    maxsplit=1,
                )[0]
                + "\n"
                + design.split(
                    "## 19. 交付物超链接规则",
                    maxsplit=1,
                )[1].split(
                    "\n## 20. ",
                    maxsplit=1,
                )[0]
            ),
            "实施计划 Task 4": plan.split(
                "### Task 4:",
                maxsplit=1,
            )[1].split(
                "### Task 5:",
                maxsplit=1,
            )[0],
        }

        for label, section in sections.items():
            with self.subTest(label=label):
                self.assertIn("等待确认期间", section)
                self.assertIn("⬜ 尚未开始", section)
                self.assertIn("⬜ 计划执行后生成", section)
                self.assertIn("不得提前使用 `❌`", section)
                self.assertIn("自动执行正常完成或提前结束收敛时", section)
                self.assertIn("最终未完成", section)
                self.assertIn("写明原因", section)
                self.assertNotIn(
                    "| 结构化认定标准 | ❌ 尚未生成 | 等待确认采用标准 |",
                    section,
                )
                self.assertNotIn(
                    "| 材料预检与补件清单 | ❌ 尚未生成 | 依赖结构化认定标准 |",
                    section,
                )

    def test_design_distinguishes_pause_recovery_and_terminal_convergence(
        self,
    ):
        design = DESIGN_PATH.read_text(encoding="utf-8")
        pause_section = extract_markdown_h2_section(
            design,
            "9. 暂停与重新规划",
        )
        interaction_section = extract_markdown_h2_section(
            design,
            "18. 澄清问题与工作计划分离",
        )

        for section in (pause_section, interaction_section):
            for required_term in (
                "独立确认步骤",
                "确认步骤从 ⏸️ → ✅",
                "下一执行步骤从 ⬜ → ⏳",
                "执行中的能力",
                "当前同一步骤从 ⏸️ → ⏳",
                "能力内部暂停点",
                "取得正式成果后才从 ⏳ → ✅",
                "不得提前进入下一步",
                "取消",
                "部分交付",
                "不可恢复失败",
                "最终状态收敛",
            ):
                self.assertIn(required_term, section, required_term)
            independent_pause = section.index("独立确认步骤")
            independent_complete = section.index(
                "确认步骤从 ⏸️ → ✅",
                independent_pause,
            )
            next_running = section.index(
                "下一执行步骤从 ⬜ → ⏳",
                independent_complete,
            )
            in_capability_pause = section.index(
                "执行中的能力",
                next_running,
            )
            in_capability_resume = section.index(
                "当前同一步骤从 ⏸️ → ⏳",
                in_capability_pause,
            )
            in_capability_complete = section.index(
                "取得正式成果后才从 ⏳ → ✅",
                in_capability_resume,
            )
            terminal_convergence = section.index(
                "最终状态收敛",
                in_capability_complete,
            )
            self.assertEqual(
                [
                    independent_pause,
                    independent_complete,
                    next_running,
                    in_capability_pause,
                    in_capability_resume,
                    in_capability_complete,
                    terminal_convergence,
                ],
                sorted(
                    [
                        independent_pause,
                        independent_complete,
                        next_running,
                        in_capability_pause,
                        in_capability_resume,
                        in_capability_complete,
                        terminal_convergence,
                    ]
                ),
            )
        self.assertNotIn(
            "用户回答后：\n\n"
            "- 更新原计划状态；\n"
            "- 将确认步骤标记为完成；\n"
            "- 将下一步骤标记为执行中；",
            interaction_section,
        )
        execution_test_strategy = extract_markdown_h3_section(
            extract_markdown_h2_section(design, "21. 测试策略"),
            "21.2 执行模式",
        )
        for required_term in (
            "独立确认步骤",
            "确认步骤从 ⏸️ → ✅",
            "下一执行步骤从 ⬜ → ⏳",
            "执行中的能力",
            "当前同一步骤从 ⏸️ → ⏳",
            "取得正式成果后才从 ⏳ → ✅",
            "取消",
            "部分交付",
            "不可恢复失败",
            "最终状态收敛",
        ):
            self.assertIn(
                required_term,
                execution_test_strategy,
                required_term,
            )
        self.assertNotIn(
            "用户回答后从暂停点恢复",
            execution_test_strategy,
        )

    def test_implementation_plan_task2_matches_runtime_trigger_boundary(
        self,
    ):
        plan = PLAN_PATH.read_text(encoding="utf-8")
        design = DESIGN_PATH.read_text(encoding="utf-8")
        runtime_skill = read("SKILL.md")
        usage = read("使用说明.md")
        task_two = extract_plan_task(plan, 2)
        trigger_contracts = {
            "设计稿": extract_markdown_h2_section(
                design,
                "5. 触发规则",
            ),
            "实施计划": task_two,
            "运行时 Skill": runtime_skill,
            "使用说明": extract_markdown_h2_section(
                usage,
                "适用场景",
            ),
        }
        for label, content in trigger_contracts.items():
            with self.subTest(label=label):
                assert_trigger_section(self, label, content)

        default_direct = task_two.index(
            "默认不自动触发单一明确任务或指定能力"
        )
        planning_override = task_two.index(
            "用户明确要求制定计划、拆解任务或安排步骤时优先触发",
            default_direct,
        )
        self.assertLess(default_direct, planning_override)
        self.assertNotIn(
            "涉及知识检索与两个以上审核环节",
            task_two,
        )

    def test_cross_document_trigger_contract_rejects_design_and_usage_drift(
        self,
    ):
        design_section = extract_markdown_h2_section(
            DESIGN_PATH.read_text(encoding="utf-8"),
            "5. 触发规则",
        )
        usage_section = extract_markdown_h2_section(
            read("使用说明.md"),
            "适用场景",
        )
        mutated_sections = {
            "设计稿反例": (
                design_section
                + "\n即使用户明确要求制定计划，也不触发规划助手。\n"
            ),
            "使用说明反例": (
                usage_section
                + "\n涉及六项能力中的任意两项时，也不触发规划助手。\n"
            ),
        }
        for label, content in mutated_sections.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    AssertionError,
                    "出现相反触发语义",
                ):
                    assert_trigger_section(self, label, content)

    def test_trigger_contract_rejects_missing_heavy_material_qualifier(
        self,
    ):
        runtime_skill = read("SKILL.md")
        self.assertIn("资料较多且未说明期望成果", runtime_skill)
        mutated_runtime_skill = runtime_skill.replace(
            "资料较多且未说明期望成果",
            "资料较多",
            1,
        )

        with self.assertRaisesRegex(
            AssertionError,
            "资料较多入口缺少未说明期望成果限定",
        ):
            assert_trigger_section(
                self,
                "运行时 Skill 反例",
                mutated_runtime_skill,
            )

    def test_trigger_contract_rejects_unconditional_heavy_material_trigger(
        self,
    ):
        plan = PLAN_PATH.read_text(encoding="utf-8")
        task_two = plan.split(
            "### Task 2:",
            maxsplit=1,
        )[1].split(
            "### Task 3:",
            maxsplit=1,
        )[0]
        mutated_task_two = (
            task_two
            + "\n资料较多即可无条件触发规划助手。\n"
        )

        with self.assertRaisesRegex(
            AssertionError,
            "出现相反触发语义",
        ):
            assert_trigger_section(
                self,
                "实施计划反例",
                mutated_task_two,
            )

    def test_standard_contract_is_consistent_across_relevant_documents(
        self,
    ):
        design = DESIGN_PATH.read_text(encoding="utf-8")
        plan = PLAN_PATH.read_text(encoding="utf-8")
        routing = read("references/intent-routing.md")
        usage = read("使用说明.md")
        design_missing = extract_markdown_h2_section(
            design,
            "11. 缺少认定标准时的公共前置流程",
        )
        task_three = extract_plan_task(plan, 3)
        routing_missing = extract_markdown_h2_section(
            routing,
            "缺少认定标准",
        )
        usage_boundaries = extract_markdown_h2_section(
            usage,
            "重要边界",
        )

        assert_cross_document_standard_contract(
            self,
            {
                "设计稿": {
                    "完全未提供": extract_markdown_h3_section(
                        design_missing,
                        "完全未提供认定标准",
                    ),
                    "已提供未确认": extract_markdown_h3_section(
                        design_missing,
                        "标准已提供但未确认",
                    ),
                    "已确认": extract_markdown_h3_section(
                        extract_markdown_h2_section(
                            design,
                            "15. 典型意图处理",
                        ),
                        "15.2 只有标准，询问需要准备什么材料",
                    ),
                    "标准修改": extract_markdown_h2_section(
                        design,
                        "14. 标准修改与版本影响路线",
                    ),
                },
                "实施计划": {
                    "完全未提供": extract_markdown_h3_section(
                        task_three,
                        "完全未提供认定标准",
                    ),
                    "已提供未确认": extract_markdown_h3_section(
                        task_three,
                        "已提供但未确认",
                    ),
                    "已确认": (
                        task_three.split(
                            "### 已确认标准",
                            maxsplit=1,
                        )[1].split(
                            "## 标准修改",
                            maxsplit=1,
                        )[0]
                    ),
                    "标准修改": task_three.split(
                        "## 标准修改",
                        maxsplit=1,
                    )[1],
                },
                "运行时路由": {
                    "完全未提供": extract_markdown_h3_section(
                        routing_missing,
                        "完全未提供标准",
                    ),
                    "已提供未确认": extract_markdown_h3_section(
                        routing_missing,
                        "已提供但未确认",
                    ),
                    "已确认": extract_markdown_h3_section(
                        extract_markdown_h2_section(
                            routing,
                            "关键分流",
                        ),
                        "只有已确认标准，询问准备什么材料",
                    ),
                    "标准修改": extract_markdown_h2_section(
                        routing,
                        "标准修改",
                    ),
                },
                "使用说明": {
                    "完全未提供": extract_markdown_h3_section(
                        usage_boundaries,
                        "完全未提供认定标准",
                    ),
                    "已提供未确认": extract_markdown_h3_section(
                        usage_boundaries,
                        "标准已提供但未确认",
                    ),
                    "已确认": extract_markdown_h3_section(
                        usage_boundaries,
                        "已确认标准",
                    ),
                    "标准修改": extract_markdown_h3_section(
                        usage_boundaries,
                        "修改认定标准",
                    ),
                },
            },
        )

    def test_standard_contract_rejects_automatic_lookup_for_unconfirmed_input(
        self,
    ):
        routing = read("references/intent-routing.md")
        missing_section = extract_markdown_h2_section(
            routing,
            "缺少认定标准",
        )
        unconfirmed = extract_markdown_h3_section(
            missing_section,
            "已提供但未确认",
        )
        self.assertIn("此状态下不自动检索", unconfirmed)
        mutated_unconfirmed = (
            unconfirmed
            + "\n此状态下自动检索。\n"
        )
        chapters = {
            "完全未提供": extract_markdown_h3_section(
                missing_section,
                "完全未提供标准",
            ),
            "已提供未确认": mutated_unconfirmed,
            "已确认": extract_markdown_h3_section(
                extract_markdown_h2_section(
                    routing,
                    "关键分流",
                ),
                "只有已确认标准，询问准备什么材料",
            ),
            "标准修改": extract_markdown_h2_section(
                routing,
                "标准修改",
            ),
        }

        with self.assertRaisesRegex(
            AssertionError,
            "未确认|不自动检索",
        ):
            assert_standard_section(
                self,
                "运行时路由反例",
                chapters,
            )

    def test_pause_contract_is_consistent_across_relevant_documents(
        self,
    ):
        design = DESIGN_PATH.read_text(encoding="utf-8")
        plan = PLAN_PATH.read_text(encoding="utf-8")
        execution = read("references/continuous-execution.md")
        usage = read("使用说明.md")
        assert_cross_document_pause_contract(
            self,
            {
                "设计稿": (
                    extract_markdown_h2_section(
                        design,
                        "9. 暂停与重新规划",
                    )
                    + "\n"
                    + extract_markdown_h2_section(
                        design,
                        "18. 澄清问题与工作计划分离",
                    )
                ),
                "实施计划": extract_plan_task(plan, 4),
                "运行时执行": (
                    extract_markdown_h2_section(
                        execution,
                        "状态转移",
                    )
                    + "\n"
                    + extract_markdown_h2_section(
                        execution,
                        "终止路径与状态收敛",
                    )
                    + "\n"
                    + extract_markdown_h2_section(
                        execution,
                        "暂停、恢复与重新规划",
                    )
                ),
                "使用说明": extract_markdown_h2_section(
                    usage,
                    "两种使用方式",
                ),
            },
        )

    def test_pause_contract_rejects_completing_an_internal_pause(
        self,
    ):
        execution = read("references/continuous-execution.md")
        execution_contract = (
            extract_markdown_h2_section(
                execution,
                "状态转移",
            )
            + "\n"
            + extract_markdown_h2_section(
                execution,
                "终止路径与状态收敛",
            )
            + "\n"
            + extract_markdown_h2_section(
                execution,
                "暂停、恢复与重新规划",
            )
        )
        self.assertIn(
            "⏸️ → ⏳",
            execution_contract,
        )
        mutated_execution = (
            execution_contract
            + "\n执行中的能力暂停后，用户回答即可直接标记完成。\n"
        )

        with self.assertRaises(AssertionError):
            assert_pause_section(
                self,
                "运行时执行反例",
                mutated_execution,
            )

    def test_authorization_contract_is_consistent_across_relevant_documents(
        self,
    ):
        design = DESIGN_PATH.read_text(encoding="utf-8")
        plan = PLAN_PATH.read_text(encoding="utf-8")
        execution = read("references/continuous-execution.md")
        usage = read("使用说明.md")
        task_four = extract_plan_task(plan, 4)
        assert_cross_document_authorization_contract(
            self,
            {
                "设计稿": extract_markdown_h2_section(
                    design,
                    "16. 省局内网授权前提",
                ),
                "实施计划": (
                    task_four.split(
                        "## 省局内网授权",
                        maxsplit=1,
                    )[1].split(
                        "\n```",
                        maxsplit=1,
                    )[0]
                ),
                "运行时执行": extract_markdown_h2_section(
                    execution,
                    "省局内网授权",
                ),
                "使用说明": extract_markdown_h2_section(
                    usage,
                    "重要边界",
                ),
            },
        )

    def test_authorization_contract_rejects_external_and_unplanned_sending(
        self,
    ):
        execution = read("references/continuous-execution.md")
        authorization = extract_markdown_h2_section(
            execution,
            "省局内网授权",
        )
        self.assertIn(
            "不覆盖其他外部服务或任何计划外发送",
            authorization,
        )
        mutated_authorization = (
            authorization
            + "\n该授权可以覆盖其他外部服务和任何计划外发送。\n"
        )

        with self.assertRaises(AssertionError):
            assert_authorization_section(
                self,
                "运行时执行反例",
                mutated_authorization,
            )

    def test_implementation_plan_task3_distinguishes_standard_states_and_order(
        self,
    ):
        plan = PLAN_PATH.read_text(encoding="utf-8")
        task_three = plan.split(
            "### Task 3:",
            maxsplit=1,
        )[1].split(
            "### Task 4:",
            maxsplit=1,
        )[0]
        for required_term in (
            "完全未提供认定标准",
            "已提供但未确认",
            "不自动检索",
            "核验来源",
            "核验现行有效性",
            "继续查找其他标准",
            "只有已确认标准",
        ):
            self.assertIn(required_term, task_three, required_term)
        missing_standard = task_three.index("完全未提供认定标准")
        missing_lookup = task_three.index(
            "调用 `chronic-disease-knowledge-retrieval`",
            missing_standard,
        )
        provided_unconfirmed = task_three.index(
            "已提供但未确认",
            missing_lookup,
        )
        no_automatic_lookup = task_three.index(
            "不自动检索",
            provided_unconfirmed,
        )
        self.assertEqual(
            [
                missing_standard,
                missing_lookup,
                provided_unconfirmed,
                no_automatic_lookup,
            ],
            sorted(
                [
                    missing_standard,
                    missing_lookup,
                    provided_unconfirmed,
                    no_automatic_lookup,
                ]
            ),
        )

        standard_change = task_three.split(
            "## 标准修改",
            maxsplit=1,
        )[1]
        change_positions = [
            standard_change.index("提供并确认现行标准"),
            standard_change.index(
                "确认拟修改内容、适用范围和业务原因或目标"
            ),
            standard_change.index("检索政策、指南、共识等修改依据"),
            standard_change.index("生成拟修订版并取得用户确认"),
            standard_change.index("版本比对"),
            standard_change.index("可选患者材料"),
        ]
        self.assertEqual(change_positions, sorted(change_positions))
        self.assertNotIn(
            "只有标准并询问准备什么材料：先给通用准备清单",
            task_three,
        )

    def test_implementation_plan_task4_has_two_resume_paths_and_termination(
        self,
    ):
        plan = PLAN_PATH.read_text(encoding="utf-8")
        task_four = plan.split(
            "### Task 4:",
            maxsplit=1,
        )[1].split(
            "### Task 5:",
            maxsplit=1,
        )[0]
        for required_term in (
            "独立确认步骤",
            "确认步骤从 ⏸️ → ✅",
            "下一执行步骤从 ⬜ → ⏳",
            "执行中的能力",
            "当前同一步骤从 ⏸️ → ⏳",
            "能力内部暂停点",
            "取得正式成果后才从 ⏳ → ✅",
            "不得提前进入下一步",
            "取消",
            "接受部分交付",
            "不可恢复失败",
            "终止并收敛",
        ):
            self.assertIn(required_term, task_four, required_term)
        independent_pause = task_four.index("独立确认步骤")
        next_running = task_four.index(
            "下一执行步骤从 ⬜ → ⏳",
            independent_pause,
        )
        in_capability_pause = task_four.index(
            "执行中的能力",
            next_running,
        )
        in_capability_resume = task_four.index(
            "当前同一步骤从 ⏸️ → ⏳",
            in_capability_pause,
        )
        terminal_convergence = task_four.index(
            "终止并收敛",
            in_capability_resume,
        )
        self.assertEqual(
            [
                independent_pause,
                next_running,
                in_capability_pause,
                in_capability_resume,
                terminal_convergence,
            ],
            sorted(
                [
                    independent_pause,
                    next_running,
                    in_capability_pause,
                    in_capability_resume,
                    terminal_convergence,
                ]
            ),
        )
        self.assertNotIn(
            "用户回答后从暂停点恢复",
            task_four,
        )

    def test_design_and_plan_limit_internal_authorization_scope(self):
        design = DESIGN_PATH.read_text(encoding="utf-8")
        plan = PLAN_PATH.read_text(encoding="utf-8")
        sections = {
            "设计稿省局内网授权": extract_markdown_h2_section(
                design,
                "16. 省局内网授权前提",
            ),
            "实施计划 Task 4 省局内网授权": (
                plan.split(
                    "### Task 4:",
                    maxsplit=1,
                )[1].split(
                    "### Task 5:",
                    maxsplit=1,
                )[0].split(
                    "## 省局内网授权",
                    maxsplit=1,
                )[1].split(
                    "\n```",
                    maxsplit=1,
                )[0]
            ),
        }
        for label, section in sections.items():
            with self.subTest(label=label):
                for required_term in (
                    "已确认计划范围内的省局内部应用",
                    "不覆盖其他外部服务",
                    "计划外发送",
                    "不绕过敏感凭据停止门",
                    "业务确认门仍保留",
                ):
                    self.assertIn(
                        required_term,
                        section,
                        f"{label}: {required_term}",
                    )

    def test_design_and_plan_define_planner_and_downstream_delivery_boundaries(self):
        documents = {
            "设计稿": DESIGN_PATH.read_text(encoding="utf-8"),
            "实施计划": PLAN_PATH.read_text(encoding="utf-8"),
        }
        required_contracts = (
            "工作计划只在对话中以 Markdown 展示",
            "不生成规划 JSON 或规划 HTML",
            "五个 Flash 下游",
            "JSON 数据文件",
            "离线 HTML 页面",
            "分别列出两个真实链接",
            "知识检索交付对话结果及实际来源链接",
            "知识检索没有固定文件",
            "不得伪造链接或规划文件",
        )

        for label, content in documents.items():
            with self.subTest(label=label):
                for contract in required_contracts:
                    self.assertIn(contract, content, f"{label}: {contract}")

    def test_design_delivery_sections_do_not_offer_placeholder_links(self):
        design = DESIGN_PATH.read_text(encoding="utf-8")
        delivery_sections = (
            design.split(
                "## 17. Markdown 工作计划",
                maxsplit=1,
            )[1].split(
                "\n## 18. ",
                maxsplit=1,
            )[0]
            + "\n"
            + design.split(
                "## 19. 交付物超链接规则",
                maxsplit=1,
            )[1].split(
                "\n## 20. ",
                maxsplit=1,
            )[0]
        )

        self.assertNotIn("](", delivery_sections)
        self.assertIn("拿到真实地址后才渲染", delivery_sections)
        self.assertIn("本稿不提供占位链接示例", delivery_sections)

    def test_usage_guide_multiturn_acceptance_scripts_have_required_fields(self):
        content = read("使用说明.md")
        self.assertIn("## 多轮验收脚本", content)
        section = extract_markdown_h2_section(content, "多轮验收脚本")
        policy = section.split("### 脚本一：", maxsplit=1)[0]

        for required_policy in (
            "全部材料均为虚构",
            "真实平台",
            "平台版本",
            "模型版本",
            "验收时间",
            "逐轮脱敏对话",
            "实际链接",
            "未实测不能声称通过",
        ):
            self.assertIn(required_policy, policy, required_policy)

        script_titles = (
            "脚本一：只制定计划",
            "脚本二：自动连续执行并完成",
            "脚本三：候选标准暂停后接受部分交付并终止",
            "脚本四：敏感凭据第 0 步拦截",
        )
        for title in script_titles:
            script = extract_markdown_h3_section(section, title)
            for field in (
                "验收目标",
                "验收前置条件",
                "用户输入或回复",
                "预期状态快照",
                "预期能力调用",
                "预期交付",
                "不得出现",
            ):
                self.assertIn(f"**{field}**", script, f"{title}: {field}")
            first_round = script.split(
                "**用户输入或回复**",
                maxsplit=1,
            )[1].split(
                "第 2 轮",
                maxsplit=1,
            )[0]
            self.assertIn("第 1 轮", first_round, title)
            self.assertNotIn("上述标准", first_round, title)
            self.assertNotIn("这些材料", first_round, title)

        for title in script_titles[:2]:
            first_round = extract_markdown_h3_section(
                section,
                title,
            ).split(
                "**用户输入或回复**",
                maxsplit=1,
            )[1].split(
                "第 2 轮",
                maxsplit=1,
            )[0]
            for fixture_term in (
                "虚构标准",
                "测试病种",
                "已确认用于测试",
                "虚构患者材料",
                "材料名",
                "2026-07-01",
            ):
                self.assertIn(fixture_term, first_round, f"{title}: {fixture_term}")

        script_three = extract_markdown_h3_section(
            section,
            script_titles[2],
        )
        for fixture_term in (
            "ADP 测试知识库",
            "固定返回",
            "候选标准甲（测试）",
            "候选标准乙（测试）",
            "不配置真实网址",
        ):
            self.assertIn(fixture_term, script_three, fixture_term)
        script_three_first_round = script_three.split(
            "**用户输入或回复**",
            maxsplit=1,
        )[1].split(
            "第 2 轮",
            maxsplit=1,
        )[0]
        for fixture_term in (
            "虚构患者材料",
            "材料名",
            "2026-07-03",
        ):
            self.assertIn(
                fixture_term,
                script_three_first_round,
                fixture_term,
            )

    def test_plan_only_multiturn_script_preserves_planned_states(self):
        content = read("使用说明.md")
        self.assertIn("## 多轮验收脚本", content)
        section = extract_markdown_h3_section(
            extract_markdown_h2_section(content, "多轮验收脚本"),
            "脚本一：只制定计划",
        )
        display_position = section.index("展示完整工作计划")
        waiting_position = section.index(
            "执行方式：待选择",
            display_position,
        )
        plan_only_reply_position = section.index(
            "只制定计划",
            waiting_position,
        )
        positions = [
            display_position,
            waiting_position,
            plan_only_reply_position,
            section.index(
                "执行方式：只制定计划",
                plan_only_reply_position,
            ),
            section.index(
                "当前状态：计划已制定",
                plan_only_reply_position,
            ),
        ]

        self.assertEqual(positions, sorted(positions))
        for required_term in (
            "已确认标准",
            "虚构患者材料",
            "先编目再预检",
            "所有未来步骤和成果保持 ⬜",
            "不调用任何下游",
            "不得出现 ❌",
        ):
            self.assertIn(required_term, section, required_term)

    def test_auto_and_partial_delivery_multiturn_state_sequences(self):
        content = read("使用说明.md")
        self.assertIn("## 多轮验收脚本", content)
        acceptance = extract_markdown_h2_section(
            content,
            "多轮验收脚本",
        )
        auto = extract_markdown_h3_section(
            acceptance,
            "脚本二：自动连续执行并完成",
        )
        waiting_position = auto.index("执行方式：待选择")
        automatic_reply_position = auto.index(
            "自动连续执行",
            waiting_position,
        )
        confirmation_position = auto.index(
            "确认按当前计划开始",
            automatic_reply_position,
        )
        ordered_state_terms = (
            "编目步骤 ⏳",
            "编目步骤 ⏸️",
            "确认编目所用材料清单完整",
            "编目步骤从 ⏸️ → ⏳",
            "编目步骤 ✅",
            "预检步骤从 ⬜ → ⏳",
            "预检步骤从 ⏳ → ⏸️",
            "确认用于预检的材料清单完整",
            "预检步骤从 ⏸️ → ⏳",
            "预检步骤从 ⏳ → ✅",
        )
        for state_term in ordered_state_terms:
            self.assertIn(state_term, auto, state_term)
        catalog_running_position = auto.index(
            "编目步骤 ⏳",
            confirmation_position,
        )
        catalog_paused_position = auto.index(
            "编目步骤 ⏸️",
            catalog_running_position,
        )
        catalog_reply_position = auto.index(
            "确认编目所用材料清单完整",
            catalog_paused_position,
        )
        catalog_resumed_position = auto.index(
            "编目步骤从 ⏸️ → ⏳",
            catalog_reply_position,
        )
        catalog_completed_position = auto.index(
            "编目步骤 ✅",
            catalog_resumed_position,
        )
        precheck_running_position = auto.index(
            "预检步骤从 ⬜ → ⏳",
            catalog_completed_position,
        )
        precheck_paused_position = auto.index(
            "预检步骤从 ⏳ → ⏸️",
            precheck_running_position,
        )
        precheck_reply_position = auto.index(
            "确认用于预检的材料清单完整",
            precheck_paused_position,
        )
        precheck_resumed_position = auto.index(
            "预检步骤从 ⏸️ → ⏳",
            precheck_reply_position,
        )
        precheck_completed_position = auto.index(
            "预检步骤从 ⏳ → ✅",
            precheck_resumed_position,
        )
        auto_positions = [
            waiting_position,
            automatic_reply_position,
            confirmation_position,
            catalog_running_position,
            catalog_paused_position,
            catalog_reply_position,
            catalog_resumed_position,
            catalog_completed_position,
            precheck_running_position,
            precheck_paused_position,
            precheck_reply_position,
            precheck_resumed_position,
            precheck_completed_position,
        ]
        self.assertEqual(auto_positions, sorted(auto_positions))
        self.assertNotIn("预检步骤从 ⬜ → ⏸️", auto)
        for required_term in (
            "第 2 轮不执行",
            "第 3 轮",
            "计划外单独询问",
            "第 4 轮",
            "第 5 轮",
            "编目阶段的材料完整性确认只授权编目继续",
            "预检独立材料完整性确认门",
            "编目 JSON",
            "编目 HTML",
            "预检 JSON",
            "预检 HTML",
            "共 4 个",
            "实际链接",
            "不得使用固定或伪造地址",
            "不输出正式资格结论",
        ):
            self.assertIn(required_term, auto, required_term)

        partial = extract_markdown_h3_section(
            acceptance,
            "脚本三：候选标准暂停后接受部分交付并终止",
        )
        paused_snapshot = partial.index("知识检索步骤 ✅")
        accepted = partial.index(
            "停止后续任务，接受当前检索结果作为部分交付"
        )
        final_snapshot = partial.index("最终状态快照", accepted)
        self.assertLess(paused_snapshot, accepted)
        self.assertLess(accepted, final_snapshot)
        for required_term in (
            "确认候选步骤 ⏸️",
            "后续步骤 ⬜",
            "候选标准甲",
            "候选标准乙",
            "用户接受部分交付/取消后续",
            "本次承诺但未完成的步骤全部 ❌",
            "无 ⏳、⏸️、⬜ 遗留",
            "不自动选择候选标准甲或候选标准乙",
            "对话结果",
            "实际来源链接",
        ):
            self.assertIn(required_term, partial, required_term)

    def test_sensitive_credential_multiturn_script_stops_at_step_zero(self):
        content = read("使用说明.md")
        self.assertIn("## 多轮验收脚本", content)
        section = extract_markdown_h3_section(
            extract_markdown_h2_section(content, "多轮验收脚本"),
            "脚本四：敏感凭据第 0 步拦截",
        )
        for required_term in (
            "访问令牌=<虚构测试值>",
            "第 0 步",
            "只输出不含具体值的通用脱敏告警",
            "不盘点",
            "不复述",
            "不提问",
            "不生成计划",
            "不调用知识库或下游",
            "不得回显占位值",
            "清理并重新提交",
            "重新确认材料范围",
            "重新确认当前计划",
            "第 2 轮",
            "第 3 轮",
            "第 4 轮",
            "测试病种",
            "材料名",
            "2026-07-04",
            "执行方式：待选择",
            "第 3 轮不调用",
            "第 4 轮才调用预检能力",
            "预检步骤从 ⬜ → ⏳",
            "预检步骤从 ⏳ → ⏸️",
            "**预检能力内部完整状态约定**",
            "⬜ → ⏳",
            "⏳ → ⏸️",
            "⏸️ → ⏳",
            "⏳ → ✅",
            "本轮验收到达暂停点",
        ):
            self.assertIn(required_term, section, required_term)
        self.assertNotIn("闭合", section)
        dialogue = section.split(
            "**用户输入或回复**",
            maxsplit=1,
        )[1].split(
            "**预期状态快照**",
            maxsplit=1,
        )[0]
        round_positions = [
            dialogue.index("第 1 轮"),
            dialogue.index("第 2 轮"),
            dialogue.index("第 3 轮"),
            dialogue.index("第 4 轮"),
        ]
        self.assertEqual(round_positions, sorted(round_positions))
        precheck_running_position = dialogue.index(
            "预检步骤从 ⬜ → ⏳",
            round_positions[-1],
        )
        precheck_paused_position = dialogue.index(
            "预检步骤从 ⏳ → ⏸️",
            precheck_running_position,
        )
        self.assertLess(precheck_running_position, precheck_paused_position)
        self.assertNotIn("预检步骤从 ⬜ → ⏸️", section)

        full_transition_contract = section.split(
            "**预检能力内部完整状态约定**",
            maxsplit=1,
        )[1].split(
            "**预期状态快照**",
            maxsplit=1,
        )[0]
        transition_positions = [
            full_transition_contract.index("⬜ → ⏳"),
            full_transition_contract.index("⏳ → ⏸️"),
            full_transition_contract.index("⏸️ → ⏳"),
            full_transition_contract.index("⏳ → ✅"),
        ]
        self.assertEqual(transition_positions, sorted(transition_positions))
        state_snapshot = section.split(
            "**预期状态快照**",
            maxsplit=1,
        )[1].split(
            "**预期能力调用**",
            maxsplit=1,
        )[0]
        expected_calls = section.split(
            "**预期能力调用**",
            maxsplit=1,
        )[1].split(
            "**预期交付**",
            maxsplit=1,
        )[0]
        for transition in (
            "⬜ → ⏳",
            "⏳ → ⏸️",
            "⏸️ → ⏳",
            "⏳ → ✅",
        ):
            self.assertIn(transition, state_snapshot, transition)
            self.assertIn(transition, expected_calls, transition)

    def test_usage_guide_acceptance_cases_are_reproducible(self):
        content = read("使用说明.md")
        acceptance_section = extract_markdown_h2_section(content, "测试用例")
        acceptance_policy = acceptance_section.split(
            "### 用例一：",
            maxsplit=1,
        )[0]
        self.assertIn(
            "必须先按各用例的 `验收前置条件` 准备或上传材料，再复制 `用户输入`",
            acceptance_policy,
        )
        self.assertIn("均为虚构测试材料", acceptance_policy)
        self.assertIn("不得包含患者隐私", acceptance_policy)
        self.assertNotIn("可选真实患者材料", acceptance_section)

        case_titles = (
            "用例一：没有认定标准的材料预检",
            "用例二：资料齐全但目标模糊",
            "用例三：两份标准下的同一测试患者判读",
            "用例四：修改现行认定标准",
            "用例五：只有已确认标准时询问准备材料",
            "用例六：只要求客观整理患者材料",
        )
        cases = {}
        for case_number, case_title in zip(
            ("一", "二", "三", "四", "五", "六"),
            case_titles,
        ):
            case_content = extract_markdown_h3_section(
                acceptance_section,
                case_title,
            )
            cases[case_number] = case_content
            for field in (
                "验收前置条件",
                "用户输入",
                "期望引导",
                "计划路线",
                "预期成果",
                "不得出现",
            ):
                self.assertIn(f"**{field}**", case_content, f"用例{case_number}: {field}")

        preconditions = {
            case_number: cases[case_number].split(
                "**验收前置条件**",
                maxsplit=1,
            )[1].split(
                "**用户输入**",
                maxsplit=1,
            )[0]
            for case_number in cases
        }

        for case_number in cases:
            self.assertTrue(preconditions[case_number].strip(), f"用例{case_number}: 前置条件为空")
        self.assertNotIn(
            "## 多轮验收脚本",
            cases["六"],
            "用例六不得吞并后续多轮验收脚本",
        )

        for case_number in ("一", "二", "三", "六"):
            self.assertIn(
                "患者材料",
                preconditions[case_number],
                f"用例{case_number}: 前置条件未说明患者材料夹具",
            )
            self.assertIn(
                "虚构",
                preconditions[case_number],
                f"用例{case_number}: 患者材料夹具前置条件未明确为虚构材料",
            )

    def test_implementation_plan_validates_all_suites_and_scans(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        task_six = content.split(
            "### Task 6:",
            maxsplit=1,
        )[1]
        suite_contracts = (
            (
                ROOT / "SKILLS" / "开发验证（非 Skill）",
                "SKILLS/开发验证（非 Skill）",
                "开发验证",
            ),
            (
                ROOT
                / "SKILLS"
                / "慢病知识库检索"
                / "chronic-disease-knowledge-retrieval"
                / "tests",
                "SKILLS/慢病知识库检索/"
                "chronic-disease-knowledge-retrieval/tests",
                "慢病知识库检索",
            ),
            (
                ROOT
                / "SKILLS"
                / "门诊慢特病认定标准与审核质控助手（完整版）"
                / "chronic-disease-certification-qc"
                / "tests",
                "SKILLS/门诊慢特病认定标准与审核质控助手（完整版）/"
                "chronic-disease-certification-qc/tests",
                "门诊慢特病认定标准与审核质控助手（完整版）",
            ),
        )
        discovered_counts = {}

        for suite_directory, suite_path, suite_label in suite_contracts:
            discovered_count = unittest.defaultTestLoader.discover(
                str(suite_directory),
                pattern="test_*.py",
            ).countTestCases()
            discovered_counts[suite_label] = discovered_count
            self.assertIn(suite_path, task_six, suite_path)
            self.assertIn(
                f"- {suite_label}：{discovered_count} 项；",
                task_six,
                suite_label,
            )

        total_count = sum(discovered_counts.values())
        self.assertIn(f"- 当前期望合计：{total_count} 项。", task_six)
        self.assertIn(
            "计数以每次实际运行输出为准，当前数字仅为快照，"
            "测试增减时同步更新",
            task_six,
        )
        self.assertIn(
            "TBD|TODO|待实现|lorem ipsum|placeholder",
            task_six,
        )
        self.assertNotIn(
            "TBD|TODO|待补充|placeholder|lorem ipsum",
            task_six,
        )
        self.assertIn("rg -n '[A-Za-z]'", task_six)
        for allowed_english in (
            "JSON",
            "HTML",
            "API",
            "Token",
            "Cookie",
            "Authorization",
            "Flash",
            "Skill ID",
            "Markdown",
            "ADP",
            "配置字段",
            "测试代号",
            "医学单位",
        ):
            self.assertIn(allowed_english, task_six, allowed_english)

        task_five = content.split(
            "### Task 5:",
            maxsplit=1,
        )[1].split(
            "### Task 6:",
            maxsplit=1,
        )[0]
        self.assertIn("虚构测试患者材料", task_five)
        self.assertNotIn("真实患者材料", task_five)

    def test_usage_guide_case_four_static_contract_supports_manual_acceptance(self):
        content = read("使用说明.md")
        case_four = content.split(
            "### 用例四：",
            maxsplit=1,
        )[1].split(
            "### 用例五：",
            maxsplit=1,
        )[0]
        precondition = case_four.split(
            "**验收前置条件**",
            maxsplit=1,
        )[1].split(
            "**用户输入**",
            maxsplit=1,
        )[0]
        expected_guidance = case_four.split(
            "**期望引导**",
            maxsplit=1,
        )[1].split(
            "**计划路线**",
            maxsplit=1,
        )[0]
        planned_route = case_four.split(
            "**计划路线**",
            maxsplit=1,
        )[1].split(
            "**预期成果**",
            maxsplit=1,
        )[0]

        for supplied_context in ("适用范围", "原因"):
            self.assertIn(supplied_context, precondition)
        for expected_behavior in (
            "复述已识别",
            "不重复询问",
            "具体阈值",
            "观察期限",
            "阻断性歧义",
        ):
            self.assertIn(expected_behavior, expected_guidance)
        for route_behavior in (
            "按已知信息推进",
            "未明确的阈值和观察期限",
            "计划外确认",
        ):
            self.assertIn(route_behavior, planned_route)

        for ordered_stage in (
            "确认",
            "阈值",
            "观察期限",
            "检索",
            "拟修订版",
            "版本影响",
        ):
            self.assertIn(ordered_stage, planned_route)

        confirmation_position = planned_route.index("确认")
        threshold_position = planned_route.index("阈值")
        duration_position = planned_route.index("观察期限")
        retrieval_position = planned_route.index("检索")
        draft_position = planned_route.index("拟修订版")
        impact_position = planned_route.index("版本影响")

        for prerequisite_position in (
            confirmation_position,
            threshold_position,
            duration_position,
        ):
            self.assertLess(prerequisite_position, retrieval_position)
        self.assertLess(retrieval_position, draft_position)
        self.assertLess(draft_position, impact_position)

        # 助手在实际对话中是否确实避免重复提问，仍须由 ADP 人工验收。

    def test_usage_guide_limits_qc_when_original_review_is_incomplete(self):
        content = read("使用说明.md")
        for required_term in (
            "原审核只有结论或摘要时",
            "仅复核可见内容",
            "未核查",
        ):
            self.assertIn(required_term, content, required_term)


if __name__ == "__main__":
    unittest.main()
