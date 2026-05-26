import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("代码节点.py")


def load_code_node():
    spec = importlib.util.spec_from_file_location("code_node", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FormatOutputTest(unittest.TestCase):
    def setUp(self):
        self.module = load_code_node()

    def expected_item(self):
        return {
            "dataType": "enum",
            "required": True,
            "keywordContent": "判断材料中是否明确记载2型糖尿病诊断。",
            "enumOptions": ["已确诊", "未确诊"],
        }

    def test_wraps_structured_output_object_as_result_list(self):
        output = {
            "Thought": "structured output",
            "dataType": "enum",
            "required": True,
            "keywordContent": "判断材料中是否明确记载2型糖尿病诊断。",
            "enumOptions": ["已确诊", "未确诊"],
        }

        self.assertEqual(
            self.module.main(output),
            {"result": [self.expected_item()]},
        )

    def test_accepts_rule_keyword_guide_array_directly(self):
        self.assertEqual(
            self.module.main([self.expected_item()]),
            {"result": [self.expected_item()]},
        )

    def test_accepts_rule_keyword_guide_named_argument(self):
        self.assertEqual(
            self.module.main(ruleKeywordGuide=[self.expected_item()]),
            {"result": [self.expected_item()]},
        )

    def test_extracts_rule_keyword_guide_from_structured_object(self):
        self.assertEqual(
            self.module.main({"ruleKeywordGuide": [self.expected_item()]}),
            {"result": [self.expected_item()]},
        )

    def test_extracts_rule_keyword_guide_when_thought_is_present(self):
        output = {
            "Thought": "先拆疾病确诊，再拆医院等级。",
            "ruleKeywordGuide": [self.expected_item()],
        }

        self.assertEqual(
            self.module.main(output),
            {"result": [self.expected_item()]},
        )

    def test_extracts_nested_output_object(self):
        self.assertEqual(
            self.module.main({"Output": self.expected_item()}),
            {"result": [self.expected_item()]},
        )

    def test_keeps_text_json_array_compatible(self):
        text = (
            '[{"dataType":"enum","required":true,'
            '"keywordContent":"判断材料中是否明确记载2型糖尿病诊断。",'
            '"enumOptions":["已确诊","未确诊"]}]'
        )

        self.assertEqual(
            self.module.main(text),
            {"result": [self.expected_item()]},
        )

    def test_extracts_nested_output_text(self):
        text = (
            '{"ruleKeywordGuide":[{"dataType":"enum","required":true,'
            '"keywordContent":"判断材料中是否明确记载2型糖尿病诊断。",'
            '"enumOptions":["已确诊","未确诊"]}]}'
        )

        self.assertEqual(
            self.module.main({"Output": text}),
            {"result": [self.expected_item()]},
        )


if __name__ == "__main__":
    unittest.main()
