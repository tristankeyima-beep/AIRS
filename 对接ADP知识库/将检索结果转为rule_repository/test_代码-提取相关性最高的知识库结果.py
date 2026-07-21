import importlib.util
import unittest
from pathlib import Path


NODE_PATH = Path(__file__).with_name("代码-提取相关性最高的知识库结果.py")


def load_node_module():
    spec = importlib.util.spec_from_file_location("knowledge_selector", NODE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KnowledgeSelectorTests(unittest.TestCase):
    def test_accepts_platform_system_parameters_with_knowledge_content_array(self):
        node = load_node_module()
        platform_params = {
            "chronicDiseaseName": "帅哥",
            "knowledgeContent": [
                {
                    "KnowledgeType": "DOC",
                    "Content": "文档名：尿毒症透析-认定标准-v20260517",
                    "DocName": "尿毒症透析-认定标准-v20260517.md",
                    "Confidence": 0.8122648,
                }
            ],
        }

        result = node.main(platform_params)

        self.assertEqual(result, {"knowledgeContent": "", "documentName": ""})

    def test_selects_matching_disease_from_platform_knowledge_content_array(self):
        node = load_node_module()
        platform_params = {
            "chronicDiseaseName": "尿毒症透析",
            "knowledgeContent": [
                {
                    "KnowledgeType": "DOC",
                    "Content": "文档名：癫痫-认定标准-v20260517",
                    "DocName": "癫痫-认定标准-v20260517.md",
                    "Confidence": 0.99,
                },
                {
                    "KnowledgeType": "DOC",
                    "Content": "文档名：尿毒症透析-认定标准-v20260517",
                    "DocName": "尿毒症透析-认定标准-v20260517.md",
                    "Confidence": 0.81,
                },
            ],
        }

        result = node.main(platform_params)

        self.assertEqual(
            result,
            {
                "knowledgeContent": "文档名：尿毒症透析-认定标准-v20260517",
                "documentName": "尿毒症透析-认定标准-v20260517.md",
            },
        )


if __name__ == "__main__":
    unittest.main()
