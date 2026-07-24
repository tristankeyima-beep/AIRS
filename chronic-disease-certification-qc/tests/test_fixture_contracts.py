import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE_ROOT = ROOT / "tests" / "fixtures" / "qc-cases"
GENERATOR_PATH = ROOT / "tests" / "build_mutation_fixtures.py"
VALIDATOR_PATH = ROOT / "scripts" / "validate_certification.py"

KNOWN_CASES = {
    "correct",
    "false-missing",
    "evidence-mismatch",
    "over-inference",
    "contradiction",
    "false-approval",
    "false-rejection",
    "rule-maintenance",
}

KNOWN_MUTATIONS = {
    "and-to-or",
    "deleted-key-evidence",
    "false-missing-with-evidence",
    "flipped-final-result",
    "negated-diagnosis",
    "reason-result-contradiction",
    "reordered-materials",
    "unrelated-material-added",
    "weakened-diagnosis",
    "weakened-treatment",
}

# This matrix is deliberately independent of expected.json. It locks the actual
# input semantics so a fixture cannot pass merely by agreeing with its own label.
INPUT_MATRIX = {
    "correct": {
        "material": "出院诊断：测试病种，需继续治疗。",
        "standard": ("出院诊断为测试病种", "且需要继续治疗"),
        "audit": {"finalResult": "通过", "evidence": "出院诊断：测试病种，需继续治疗。"},
        "advice": "材料已明确诊断为测试病种，并注明需继续治疗",
        "expected": ("可靠", "未发现明显风险", []),
    },
    "false-missing": {
        "material": "患者规律接受长期治疗三年",
        "standard": ("患者已经规律接受长期治疗",),
        "audit": {"finalResult": "不通过"},
        "advice": "缺少长期治疗证据",
        "expected": ("不可靠", "错误拒绝风险", ["误报缺失"]),
    },
    "evidence-mismatch": {
        "material": "未发现测试病种相关表现。",
        "standard": ("发现测试病种相关表现",),
        "audit": {
            "finalResult": "通过",
            "evidence": "已发现测试病种相关表现",
        },
        "advice": "相关表现符合认定标准",
        "expected": ("不可靠", "错误放行风险", ["证据含义提取错误"]),
    },
    "over-inference": {
        "material": "建议进一步评估是否需要长期治疗。",
        "standard": ("患者已经接受长期治疗",),
        "audit": {"finalResult": "通过"},
        "advice": "患者已经接受长期治疗",
        "expected": ("不可靠", "错误放行风险", ["过度推理"]),
    },
    "contradiction": {
        "material": "已明确诊断为测试病种。",
        "standard": ("已明确诊断为测试病种",),
        "audit": {"finalResult": "通过"},
        "advice": "无法确认诊断",
        "ruleResult": "满足",
        "expected": ("存在重大疑点", "暂时无法判断", ["审核条件与结论矛盾"]),
    },
    "false-approval": {
        "material": "条件A已满足。",
        "standard": ("逻辑：且", "条件A满足", "条件B满足"),
        "audit": {"finalResult": "通过"},
        "advice": "条件A满足，因此通过",
        "expected": ("不可靠", "错误放行风险", ["必需条件缺失但错误放行"]),
    },
    "false-rejection": {
        "material": "条件A已满足。",
        "standard": ("逻辑：或", "条件A满足", "条件B满足"),
        "audit": {"finalResult": "不通过"},
        "advice": "条件B缺失，因此不通过",
        "expected": ("不可靠", "错误拒绝风险", ["OR 逻辑计算错误"]),
    },
    "rule-maintenance": {
        "material": "已明确诊断为测试病种。",
        "audit": {"finalResult": "通过"},
        "advice": "材料支持明确诊断条件",
        "expected": ("基本可靠", "仅影响规则质量", ["规则维护不完整"]),
    },
}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class FixtureContractTests(unittest.TestCase):
    def test_known_case_file_and_expected_contract(self):
        case_dirs = {path.name: path for path in CASE_ROOT.iterdir() if path.is_dir()}
        self.assertEqual(set(case_dirs), KNOWN_CASES)

        for name, case_dir in case_dirs.items():
            with self.subTest(case=name):
                self.assertTrue((case_dir / "materials.txt").is_file())
                self.assertTrue((case_dir / "audit-result.json").is_file())
                self.assertTrue((case_dir / "expected.json").is_file())
                standards = [
                    path
                    for path in (case_dir / "standard.txt", case_dir / "certification.json")
                    if path.is_file()
                ]
                self.assertEqual(len(standards), 1)

                materials = (case_dir / "materials.txt").read_text(encoding="utf-8")
                standard = standards[0].read_text(encoding="utf-8")
                audit_text = (case_dir / "audit-result.json").read_text(encoding="utf-8")
                expected_text = (case_dir / "expected.json").read_text(encoding="utf-8")
                for text in (materials, standard, audit_text, expected_text):
                    self.assertTrue(text.strip())

                audit = json.loads(audit_text)
                expected = json.loads(expected_text)
                self.assertIsInstance(audit, dict)
                self.assertIsInstance(expected["expectedQcConclusion"], str)
                self.assertIsInstance(expected["expectedRisk"], str)
                self.assertIsInstance(expected["expectedIssues"], list)
                self.assertIsInstance(expected["mustFindText"], list)
                self.assertIsInstance(expected["mustNotReport"], list)
                self.assertTrue(expected["mustFindText"])
                for literal in expected["mustFindText"]:
                    self.assertIsInstance(literal, str)
                    self.assertTrue(literal)
                    self.assertIn(literal, materials)
                all_input = materials + "\n" + standard + "\n" + audit_text
                for absent_claim in expected["mustNotReport"]:
                    self.assertIsInstance(absent_claim, str)
                    self.assertTrue(absent_claim)
                    self.assertNotIn(absent_claim, all_input)

    def test_hard_coded_input_semantics_match_the_case_matrix(self):
        self.assertEqual(set(INPUT_MATRIX), KNOWN_CASES)
        for name, contract in INPUT_MATRIX.items():
            case_dir = CASE_ROOT / name
            materials = (case_dir / "materials.txt").read_text(encoding="utf-8")
            standard_path = next(
                path
                for path in (case_dir / "standard.txt", case_dir / "certification.json")
                if path.is_file()
            )
            standard_text = standard_path.read_text(encoding="utf-8")
            audit = json.loads(
                (case_dir / "audit-result.json").read_text(encoding="utf-8")
            )
            expected = json.loads(
                (case_dir / "expected.json").read_text(encoding="utf-8")
            )
            with self.subTest(case=name):
                self.assertIn(contract["material"], materials)
                for standard_literal in contract.get("standard", ()):
                    self.assertIn(standard_literal, standard_text)
                for key, value in contract["audit"].items():
                    self.assertEqual(audit[key], value)
                self.assertEqual(audit["advice"], contract["advice"])
                if "ruleResult" in contract:
                    self.assertEqual(audit["ruleResults"][0]["result"], contract["ruleResult"])
                self.assertEqual(
                    (
                        expected["expectedQcConclusion"],
                        expected["expectedRisk"],
                        expected["expectedIssues"],
                    ),
                    contract["expected"],
                )

    def test_logic_cases_lock_operator_material_and_original_decision(self):
        approval = INPUT_MATRIX["false-approval"]
        self.assertIn("逻辑：且", approval["standard"])
        self.assertEqual(approval["material"], "条件A已满足。")
        self.assertEqual(approval["audit"]["finalResult"], "通过")

        rejection = INPUT_MATRIX["false-rejection"]
        self.assertIn("逻辑：或", rejection["standard"])
        self.assertEqual(rejection["material"], "条件A已满足。")
        self.assertEqual(rejection["audit"]["finalResult"], "不通过")
        self.assertEqual(rejection["advice"], "条件B缺失，因此不通过")

    def test_correct_case_prevents_forced_over_reporting(self):
        expected = json.loads(
            (CASE_ROOT / "correct" / "expected.json").read_text(encoding="utf-8")
        )
        self.assertEqual(expected["expectedIssues"], [])
        self.assertIn("证据不足", expected["mustNotReport"])

    def test_rule_maintenance_has_exactly_one_structural_defect(self):
        validator = load_module("validate_certification_for_fixture", VALIDATOR_PATH)
        standard_path = CASE_ROOT / "rule-maintenance" / "certification.json"
        result = validator.validate_certification(standard_path)
        self.assertFalse(result["valid"])
        self.assertEqual(
            [
                (item["path"], item["code"])
                for item in result["errors"]
            ],
            [("ruleRepository[0].ruleKeywordGuide", "keyword_guide_required")],
        )


class MutationGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("build_mutation_fixtures", GENERATOR_PATH)

    def test_low_level_pure_text_mutations(self):
        self.assertEqual(
            self.module.negate_claim("出院诊断：明确诊断为测试病种。"),
            "出院诊断：明确排除为测试病种。",
        )
        self.assertEqual(
            self.module.weaken_claim("出院诊断：明确诊断为测试病种。"),
            "出院诊断：疑似测试病种。",
        )
        self.assertEqual(
            self.module.weaken_claim("治疗经过：已经接受长期治疗三年。"),
            "治疗经过：建议评估是否需要长期治疗三年。",
        )
        self.assertEqual(self.module.flip_final_result("通过"), "不通过")
        self.assertEqual(self.module.flip_final_result("不通过"), "通过")
        with self.assertRaises(ValueError):
            self.module.flip_final_result("无法判断")
        original = ["材料一", "材料二", "材料三"]
        self.assertEqual(self.module.reorder_materials(original), list(reversed(original)))
        self.assertEqual(original, ["材料一", "材料二", "材料三"])

    def test_each_case_is_derived_from_a_named_correct_base_by_one_pure_transform(self):
        transforms = {
            "deleted-key-evidence": ("diagnosis", self.module.delete_key_evidence),
            "negated-diagnosis": ("diagnosis", self.module.negate_diagnosis),
            "weakened-diagnosis": ("diagnosis", self.module.weaken_to_suspected),
            "weakened-treatment": ("treatment", self.module.weaken_treatment),
            "flipped-final-result": ("diagnosis", self.module.flip_final),
            "and-to-or": ("logic-and-rejection", self.module.and_to_or),
            "false-missing-with-evidence": (
                "treatment",
                self.module.claim_missing_while_retaining_evidence,
            ),
            "reason-result-contradiction": (
                "diagnosis",
                self.module.contradict_reason_and_result,
            ),
            "reordered-materials": ("compound", self.module.reorder_case_materials),
            "unrelated-material-added": (
                "diagnosis",
                self.module.add_unrelated_material,
            ),
        }
        built = self.module.build_cases()
        self.assertEqual(set(built), KNOWN_MUTATIONS)
        for name, (base_name, transform) in transforms.items():
            base = self.module.BASE_CORRECT[base_name]
            frozen = copy.deepcopy(base)
            with self.subTest(case=name):
                self.assertEqual(built[name], transform(base))
                self.assertEqual(base, frozen)
                self.assertEqual(built[name]["baseCase"], base_name)

    def test_mutations_have_the_required_base_to_case_relationship(self):
        bases = self.module.BASE_CORRECT
        cases = self.module.build_cases()

        self.assertNotIn("明确诊断", "\n".join(cases["deleted-key-evidence"]["materials"]))
        self.assertIn("明确诊断", "\n".join(bases["diagnosis"]["materials"]))
        self.assertEqual(
            cases["negated-diagnosis"]["materials"][0],
            self.module.negate_claim(bases["diagnosis"]["materials"][0]),
        )
        self.assertEqual(
            cases["weakened-diagnosis"]["materials"][0],
            self.module.weaken_claim(bases["diagnosis"]["materials"][0]),
        )
        self.assertEqual(
            cases["weakened-treatment"]["materials"][0],
            self.module.weaken_claim(bases["treatment"]["materials"][0]),
        )
        self.assertEqual(
            cases["flipped-final-result"]["audit"]["finalResult"],
            self.module.flip_final_result(bases["diagnosis"]["audit"]["finalResult"]),
        )
        self.assertEqual(
            cases["and-to-or"]["standard"],
            bases["logic-and-rejection"]["standard"].replace("逻辑：且", "逻辑：或", 1),
        )
        retained = cases["false-missing-with-evidence"]
        self.assertEqual(retained["materials"], bases["treatment"]["materials"])
        self.assertIn("缺少长期治疗证据", retained["audit"]["advice"])
        contradiction = cases["reason-result-contradiction"]
        self.assertEqual(
            contradiction["audit"]["finalResult"],
            bases["diagnosis"]["audit"]["finalResult"],
        )
        self.assertNotEqual(
            contradiction["audit"]["advice"],
            bases["diagnosis"]["audit"]["advice"],
        )
        self.assertEqual(
            cases["reordered-materials"]["materials"],
            list(reversed(bases["compound"]["materials"])),
        )
        self.assertEqual(
            cases["unrelated-material-added"]["materials"][1:],
            bases["diagnosis"]["materials"],
        )

    def test_invariance_cases_preserve_the_base_expected_outcome(self):
        cases = self.module.build_cases()
        for name in ("reordered-materials", "unrelated-material-added"):
            case = cases[name]
            base_expected = self.module.BASE_CORRECT[case["baseCase"]]["expected"]
            with self.subTest(case=name):
                self.assertTrue(case["expected"]["expectedInvariant"])
                self.assertEqual(case["expected"]["expectedQcConclusion"], base_expected["expectedQcConclusion"])
                self.assertEqual(case["expected"]["expectedRisk"], base_expected["expectedRisk"])
                self.assertEqual(case["expected"]["expectedIssues"], base_expected["expectedIssues"])

    def test_generator_builds_ten_deterministic_contract_cases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            anchor = Path(temp_dir)
            trusted = anchor / "fixtures"
            trusted.mkdir()
            generated = trusted / "generated"
            self.module.generate(
                output_root=generated,
                trusted_base=trusted,
                trusted_anchor=anchor,
            )
            first_digest = tree_digest(generated)
            first_bytes = {
                path.relative_to(generated): path.read_bytes()
                for path in generated.rglob("*")
                if path.is_file()
            }

            self.module.generate(
                output_root=generated,
                trusted_base=trusted,
                trusted_anchor=anchor,
            )
            self.assertEqual(tree_digest(generated), first_digest)
            self.assertEqual(
                {
                    path.relative_to(generated): path.read_bytes()
                    for path in generated.rglob("*")
                    if path.is_file()
                },
                first_bytes,
            )

            case_dirs = sorted(path for path in generated.iterdir() if path.is_dir())
            self.assertEqual({path.name for path in case_dirs}, KNOWN_MUTATIONS)
            for case_dir in case_dirs:
                with self.subTest(case=case_dir.name):
                    self.assertEqual(
                        {path.name for path in case_dir.iterdir()},
                        {
                            "materials.txt",
                            "standard.txt",
                            "audit-result.json",
                            "expected.json",
                        },
                    )
                    for path in case_dir.iterdir():
                        self.assertFalse(path.is_symlink())
                        data = path.read_bytes()
                        self.assertTrue(data)
                        self.assertTrue(data.endswith(b"\n"))
                        self.assertFalse(data.endswith(b"\n\n"))
                        data.decode("utf-8")
                    expected = json.loads(
                        (case_dir / "expected.json").read_text(encoding="utf-8")
                    )
                    self.assertIsInstance(expected["expectedQcConclusion"], str)
                    self.assertIsInstance(expected["expectedRisk"], str)
                    self.assertIsInstance(expected["expectedIssues"], list)
                    self.assertTrue(expected["mustFindText"])
                    self.assertTrue(expected["mustNotReport"])
                    self.assertIsInstance(expected["expectedInvariant"], bool)
                    self.assertIn(expected["mutationKind"], {"defect", "invariance"})
                    self.assertEqual(
                        expected["expectedInvariant"],
                        expected["mutationKind"] == "invariance",
                    )
                    materials = (case_dir / "materials.txt").read_text(encoding="utf-8")
                    standard = (case_dir / "standard.txt").read_text(encoding="utf-8")
                    audit_text = (case_dir / "audit-result.json").read_text(
                        encoding="utf-8"
                    )
                    for literal in expected["mustFindText"]:
                        self.assertIn(literal, materials)
                    for absent_claim in expected["mustNotReport"]:
                        self.assertNotIn(
                            absent_claim,
                            materials + "\n" + standard + "\n" + audit_text,
                        )

    def test_generator_preserves_unknown_files_and_rejects_root_symlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            anchor = Path(temp_dir)
            trusted = anchor / "fixtures"
            generated = trusted / "generated"
            generated.mkdir(parents=True)
            unknown = generated / "user-note.txt"
            unknown.write_text("保留我\n", encoding="utf-8")
            self.module.generate(
                output_root=generated,
                trusted_base=trusted,
                trusted_anchor=anchor,
            )
            self.assertEqual(unknown.read_text(encoding="utf-8"), "保留我\n")

        with tempfile.TemporaryDirectory() as temp_dir:
            anchor = Path(temp_dir)
            trusted = anchor / "fixtures"
            trusted.mkdir()
            real_root = anchor / "real"
            real_root.mkdir()
            generated = trusted / "generated"
            generated.symlink_to(real_root, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.module.generate(
                    output_root=generated,
                    trusted_base=trusted,
                    trusted_anchor=anchor,
                )
            self.assertEqual(list(real_root.iterdir()), [])

    def test_generator_rejects_symlink_in_an_ancestor_above_fixtures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            anchor = Path(temp_dir) / "anchor"
            anchor.mkdir()
            external = Path(temp_dir) / "external"
            external.mkdir()
            linked_parent = anchor / "link"
            linked_parent.symlink_to(external, target_is_directory=True)
            trusted = linked_parent / "nested" / "fixtures"
            generated = trusted / "generated"
            with self.assertRaisesRegex(ValueError, "符号链接"):
                self.module.generate(
                    output_root=generated,
                    trusted_base=trusted,
                    trusted_anchor=anchor,
                )
            self.assertEqual(list(external.iterdir()), [])

    def test_generator_rejects_escape_and_regular_file_roots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            anchor = Path(temp_dir)
            trusted = anchor / "fixtures"
            trusted.mkdir()
            outside = anchor / "outside" / "generated"
            with self.assertRaisesRegex(ValueError, "可信目录"):
                self.module.generate(
                    output_root=outside,
                    trusted_base=trusted,
                    trusted_anchor=anchor,
                )
            self.assertFalse(outside.exists())

            generated = trusted / "generated"
            generated.write_text("不是目录\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "普通目录"):
                self.module.generate(
                    output_root=generated,
                    trusted_base=trusted,
                    trusted_anchor=anchor,
                )
            self.assertEqual(generated.read_text(encoding="utf-8"), "不是目录\n")

    def test_custom_generation_requires_an_explicit_existing_trusted_anchor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            anchor = Path(temp_dir)
            trusted = anchor / "fixtures"
            trusted.mkdir()
            generated = trusted / "generated"
            with self.assertRaisesRegex(ValueError, "trusted_anchor"):
                self.module.generate(output_root=generated, trusted_base=trusted)

            missing_anchor = anchor / "missing"
            with self.assertRaisesRegex(ValueError, "已存在"):
                self.module.generate(
                    output_root=generated,
                    trusted_base=trusted,
                    trusted_anchor=missing_anchor,
                )

    def test_main_generated_fixtures_match_the_contract(self):
        self.module.generate()
        generated = ROOT / "tests" / "fixtures" / "generated"
        self.assertEqual(
            {path.name for path in generated.iterdir() if path.is_dir()},
            KNOWN_MUTATIONS,
        )


if __name__ == "__main__":
    unittest.main()
