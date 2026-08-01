import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "render_payment_audit_html.py"


class PaymentAuditHtmlRenderTests(unittest.TestCase):
    def test_renders_rule_cards_with_logic_and_keyword_guides(self):
        standard = {
            "meta": {
                "version": "V20260728",
                "chronicDiseaseName": "黄斑病变眼内注射药品报销审核",
                "chronicDiseaseCode": "SJ05",
                "createdAt": "2026-07-28",
                "description": "某类药品报销审核。",
                "sourceFile": "八类疾病准入条件及细则-20260517.xlsx",
            },
            "ruleRepository": [{
                "ruleCode": "05001",
                "ruleContent": "本次拟用雷珠单抗，且符合限定适应范围。",
                "ruleSource": "八类疾病准入条件及细则-20260517.xlsx",
                "experience": "",
                "sourceRuleContent": "雷珠单抗限：50岁以上湿性AMD。",
                "sourceMdFile": "黄斑病变眼内注射药品-报销审核规则-v20260728.md",
                "sourceSection": "雷珠单抗",
                "ruleKeywordGuide": [{
                    "keywordCode": "05001001",
                    "dataType": "enum",
                    "required": True,
                    "keywordContent": "提取本次拟用药品是否为雷珠单抗。",
                    "enumOptions": ["是", "否", "无法判断"],
                }],
            }],
            "logicTopology": {"type": "GROUP", "operator": "AND", "children": [{"type": "RULE_REF", "ruleCode": "05001"}]},
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "standard.json"
            output = Path(directory) / "rendered.html"
            source.write_text(json.dumps(standard, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(RENDERER), str(source), str(output)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            html = output.read_text(encoding="utf-8")
        for fragment in ("逻辑拓扑", "规则库详情", "提取项说明", "05001001", "展开完整数据结构"):
            self.assertIn(fragment, html)


if __name__ == "__main__":
    unittest.main()
