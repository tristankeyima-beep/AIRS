import importlib.util
import unittest
from pathlib import Path


NODE_PATH = Path(__file__).with_name("代码-选择原始或ADP组装的certification_list.py")


def load_node_module():
    spec = importlib.util.spec_from_file_location("certification_list_selector", NODE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CertificationListSelectorTests(unittest.TestCase):
    def setUp(self):
        self.original = {"meta": {"version": "v20260517"}, "ruleRepository": [{"ruleCode": "01001"}]}
        self.assembled = {"meta": {"version": "ADP-尿毒症透析-认定标准-v20260517"}, "ruleRepository": [{"ruleCode": "01001"}, {"ruleCode": "01002"}]}

    def test_returns_original_certification_list_when_knowledge_content_is_blank(self):
        node = load_node_module()

        result = node.main(
            knowledgeContent=" \n\t ",
            originalCertificationList=self.original,
            assembledCertificationList=self.assembled,
        )

        self.assertEqual(result, {"certification_list": self.original})

    def test_returns_assembled_certification_list_when_knowledge_content_exists(self):
        node = load_node_module()

        result = node.main(
            knowledgeContent="文档名：尿毒症透析-认定标准-v20260517",
            originalCertificationList=self.original,
            assembledCertificationList=self.assembled,
        )

        self.assertEqual(result, {"certification_list": self.assembled})


if __name__ == "__main__":
    unittest.main()
