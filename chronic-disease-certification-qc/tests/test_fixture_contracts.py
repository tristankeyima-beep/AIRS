import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE_ROOT = ROOT / "tests" / "fixtures" / "qc-cases"
GENERATOR_PATH = ROOT / "tests" / "build_mutation_fixtures.py"

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

EXPECTED_MATRIX = {
    "correct": ("可靠", "未发现明显风险", []),
    "false-missing": ("不可靠", "错误拒绝风险", ["误报缺失"]),
    "evidence-mismatch": ("不可靠", "错误放行风险", ["证据含义提取错误"]),
    "over-inference": ("不可靠", "错误放行风险", ["过度推理"]),
    "contradiction": ("存在重大疑点", "暂时无法判断", ["审核条件与结论矛盾"]),
    "false-approval": ("不可靠", "错误放行风险", ["必需条件缺失但错误放行"]),
    "false-rejection": ("不可靠", "错误拒绝风险", ["OR 逻辑计算错误"]),
    "rule-maintenance": ("基本可靠", "仅影响规则质量", ["规则维护不完整"]),
}


def load_generator():
    spec = importlib.util.spec_from_file_location("build_mutation_fixtures", GENERATOR_PATH)
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
    def test_known_case_matrix_and_file_contract(self):
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
                self.assertTrue(materials.strip())
                self.assertTrue(standard.strip())
                self.assertTrue(audit_text.strip())
                self.assertTrue(expected_text.strip())

                audit = json.loads(audit_text)
                expected = json.loads(expected_text)
                self.assertIsInstance(audit, dict)
                self.assertEqual(
                    (
                        expected["expectedQcConclusion"],
                        expected["expectedRisk"],
                        expected["expectedIssues"],
                    ),
                    EXPECTED_MATRIX[name],
                )
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
                combined_input = materials + "\n" + audit_text
                for absent_claim in expected["mustNotReport"]:
                    self.assertIsInstance(absent_claim, str)
                    self.assertTrue(absent_claim)
                    self.assertNotIn(absent_claim, combined_input)

    def test_correct_case_prevents_forced_over_reporting(self):
        expected = json.loads(
            (CASE_ROOT / "correct" / "expected.json").read_text(encoding="utf-8")
        )
        self.assertEqual(expected["expectedIssues"], [])
        self.assertIn("证据不足", expected["mustNotReport"])

    def test_rule_maintenance_case_uses_incomplete_structured_standard(self):
        standard = json.loads(
            (CASE_ROOT / "rule-maintenance" / "certification.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(standard["ruleRepository"][0]["ruleKeywordGuide"], [])


class MutationGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_generator()

    def test_pure_mutation_functions(self):
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

    def test_generator_builds_ten_deterministic_contract_cases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generated = Path(temp_dir) / "fixtures" / "generated"
            self.module.build_mutation_fixtures(generated)
            first_digest = tree_digest(generated)
            first_bytes = {
                path.relative_to(generated): path.read_bytes()
                for path in generated.rglob("*")
                if path.is_file()
            }

            self.module.build_mutation_fixtures(generated)
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
                    self.assertIsInstance(expected["mustFindText"], list)
                    self.assertIsInstance(expected["mustNotReport"], list)
                    self.assertTrue(expected["mustFindText"])
                    self.assertTrue(expected["mustNotReport"])
                    self.assertIsInstance(expected["expectedInvariant"], bool)
                    self.assertIn(expected["mutationKind"], {"defect", "invariance"})
                    self.assertEqual(
                        expected["expectedInvariant"],
                        expected["mutationKind"] == "invariance",
                    )
                    materials = (case_dir / "materials.txt").read_text(encoding="utf-8")
                    audit_text = (case_dir / "audit-result.json").read_text(
                        encoding="utf-8"
                    )
                    for literal in expected["mustFindText"]:
                        self.assertIn(literal, materials)
                    for absent_claim in expected["mustNotReport"]:
                        self.assertNotIn(absent_claim, materials + "\n" + audit_text)

    def test_generator_preserves_unknown_files_and_fails_closed_on_symlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generated = Path(temp_dir) / "fixtures" / "generated"
            generated.mkdir(parents=True)
            unknown = generated / "user-note.txt"
            unknown.write_text("保留我\n", encoding="utf-8")
            self.module.build_mutation_fixtures(generated)
            self.assertEqual(unknown.read_text(encoding="utf-8"), "保留我\n")

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            real_root = base / "real"
            real_root.mkdir()
            generated = base / "fixtures" / "generated"
            generated.parent.mkdir()
            generated.symlink_to(real_root, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.module.build_mutation_fixtures(generated)
            self.assertEqual(list(real_root.iterdir()), [])

    def test_generator_rejects_a_regular_file_as_generated_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generated = Path(temp_dir) / "fixtures" / "generated"
            generated.parent.mkdir()
            generated.write_text("不是目录\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "普通目录"):
                self.module.build_mutation_fixtures(generated)
            self.assertEqual(generated.read_text(encoding="utf-8"), "不是目录\n")

    def test_main_generated_fixtures_match_the_contract(self):
        self.module.build_mutation_fixtures()
        generated = ROOT / "tests" / "fixtures" / "generated"
        self.assertGreaterEqual(
            len([path for path in generated.iterdir() if path.is_dir()]),
            10,
        )


if __name__ == "__main__":
    unittest.main()
