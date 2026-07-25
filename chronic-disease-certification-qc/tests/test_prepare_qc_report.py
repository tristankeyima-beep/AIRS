import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_qc_report.py"
FIXTURE = ROOT / "tests" / "fixtures" / "valid-qc-report.json"
SPEC = importlib.util.spec_from_file_location("prepare_qc_report", SCRIPT)
preparer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preparer)


class PrepareQcReportTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_prepares_content_hashes_and_unperformed_checks_without_mutating_draft(self):
        draft = copy.deepcopy(self.report)
        original = copy.deepcopy(draft)
        material = draft["rawInput"]["materials"][0]
        material["materialContent"] = material.pop("content")
        capability = next(
            item
            for item in draft["capabilities"]
            if item["name"] == "审核条件与结论一致性"
        )
        capability.update({"status": "not_run", "reason": "标准逻辑不可执行"})
        draft["unperformedChecks"] = [{"name": "旧值", "reason": "旧值"}]
        input_snapshot = copy.deepcopy(draft)

        prepared = preparer.prepare_report(draft)

        self.assertEqual(draft, input_snapshot)
        self.assertEqual(
            prepared["rawInput"]["materials"][0]["content"],
            original["rawInput"]["materials"][0]["content"],
        )
        self.assertNotIn("materialContent", prepared["rawInput"]["materials"][0])
        self.assertEqual(
            prepared["unperformedChecks"],
            [{"name": "审核条件与结论一致性", "reason": "标准逻辑不可执行"}],
        )
        inventory = prepared["inputScope"]["inventory"]
        confirmation = prepared["inputScope"]["confirmation"]
        independent = prepared["inputScope"]["independentReview"]
        self.assertEqual(
            inventory["rawInputSha256"],
            preparer.renderer.compute_raw_input_sha256(prepared["rawInput"]),
        )
        self.assertEqual(
            confirmation["inventorySha256"],
            preparer.renderer.compute_inventory_sha256(inventory),
        )
        self.assertEqual(
            independent["artifactSha256"],
            preparer.renderer.compute_independent_review_sha256(independent["artifact"]),
        )
        preparer.renderer.validate_qc_report(prepared)

    def test_accepts_supported_text_aliases_and_rejects_conflicting_values(self):
        for alias in ("materialContent", "text", "rawText"):
            with self.subTest(alias=alias):
                draft = copy.deepcopy(self.report)
                material = draft["rawInput"]["materials"][0]
                material[alias] = material.pop("content")
                prepared = preparer.prepare_report(draft)
                self.assertIn("content", prepared["rawInput"]["materials"][0])
                self.assertNotIn(alias, prepared["rawInput"]["materials"][0])

        conflict = copy.deepcopy(self.report)
        conflict["rawInput"]["materials"][0]["materialContent"] = "不同正文"
        with self.assertRaisesRegex(ValueError, "conflicting material text fields"):
            preparer.prepare_report(conflict)

    def test_does_not_infer_or_rewrite_user_confirmation(self):
        draft = copy.deepcopy(self.report)
        draft["inputScope"]["confirmation"]["userStatement"] = "应该没有"
        with self.assertRaisesRegex(ValueError, "userStatement"):
            preparer.prepare_report(draft)
        self.assertEqual(
            draft["inputScope"]["confirmation"]["userStatement"],
            "应该没有",
        )

    def test_cli_writes_prepared_canonical_json(self):
        draft = copy.deepcopy(self.report)
        material = draft["rawInput"]["materials"][0]
        material["materialContent"] = material.pop("content")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "draft.json"
            output = Path(directory) / "prepared.json"
            source.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), str(output)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            prepared = json.loads(output.read_text(encoding="utf-8"))
        self.assertIn("content", prepared["rawInput"]["materials"][0])
        self.assertNotIn("materialContent", prepared["rawInput"]["materials"][0])


if __name__ == "__main__":
    unittest.main()
