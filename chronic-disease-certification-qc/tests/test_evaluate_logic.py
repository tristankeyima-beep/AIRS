import copy
import importlib.util
import json
from itertools import product
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_logic.py"
SPEC = importlib.util.spec_from_file_location("evaluate_logic", SCRIPT)
evaluator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluator)


STATES = ("满足", "不满足", "无法判断", "不适用")


def rule(code):
    return {"type": "RULE_REF", "ruleCode": code}


def group(operator, *children):
    return {"type": "GROUP", "operator": operator, "children": list(children)}


class EvaluateLogicTests(unittest.TestCase):
    def evaluate_pair(self, operator, first, second):
        return evaluator.evaluate_logic(
            group(operator, rule("first"), rule("second")),
            {"first": first, "second": second},
        )["result"]

    def test_valid_results_are_the_four_supported_states(self):
        self.assertEqual(evaluator.VALID_RESULTS, set(STATES))

    def test_and_satisfied_and_unsatisfied_is_unsatisfied(self):
        self.assertEqual(self.evaluate_pair("AND", "满足", "不满足"), "不满足")

    def test_or_satisfied_and_unknown_is_satisfied(self):
        self.assertEqual(self.evaluate_pair("OR", "满足", "无法判断"), "满足")

    def test_and_satisfied_and_unknown_is_unknown(self):
        self.assertEqual(self.evaluate_pair("AND", "满足", "无法判断"), "无法判断")

    def test_and_satisfied_and_not_applicable_is_satisfied(self):
        self.assertEqual(self.evaluate_pair("AND", "满足", "不适用"), "满足")

    def test_or_all_not_applicable_is_not_applicable(self):
        self.assertEqual(self.evaluate_pair("OR", "不适用", "不适用"), "不适用")

    def test_and_state_table(self):
        expected = {
            ("满足", "满足"): "满足",
            ("满足", "不满足"): "不满足",
            ("满足", "无法判断"): "无法判断",
            ("满足", "不适用"): "满足",
            ("不满足", "满足"): "不满足",
            ("不满足", "不满足"): "不满足",
            ("不满足", "无法判断"): "不满足",
            ("不满足", "不适用"): "不满足",
            ("无法判断", "满足"): "无法判断",
            ("无法判断", "不满足"): "不满足",
            ("无法判断", "无法判断"): "无法判断",
            ("无法判断", "不适用"): "无法判断",
            ("不适用", "满足"): "满足",
            ("不适用", "不满足"): "不满足",
            ("不适用", "无法判断"): "无法判断",
            ("不适用", "不适用"): "不适用",
        }
        self.assertEqual(set(expected), set(product(STATES, repeat=2)))
        for states, result in expected.items():
            with self.subTest(states=states):
                self.assertEqual(self.evaluate_pair("AND", *states), result)

    def test_or_state_table(self):
        expected = {
            ("满足", "满足"): "满足",
            ("满足", "不满足"): "满足",
            ("满足", "无法判断"): "满足",
            ("满足", "不适用"): "满足",
            ("不满足", "满足"): "满足",
            ("不满足", "不满足"): "不满足",
            ("不满足", "无法判断"): "无法判断",
            ("不满足", "不适用"): "不满足",
            ("无法判断", "满足"): "满足",
            ("无法判断", "不满足"): "无法判断",
            ("无法判断", "无法判断"): "无法判断",
            ("无法判断", "不适用"): "无法判断",
            ("不适用", "满足"): "满足",
            ("不适用", "不满足"): "不满足",
            ("不适用", "无法判断"): "无法判断",
            ("不适用", "不适用"): "不适用",
        }
        self.assertEqual(set(expected), set(product(STATES, repeat=2)))
        for states, result in expected.items():
            with self.subTest(states=states):
                self.assertEqual(self.evaluate_pair("OR", *states), result)

    def test_nested_tree_returns_a_trace_at_every_node_in_child_order(self):
        node = group("AND", rule("a"), group("OR", rule("b"), rule("c")))
        trace = evaluator.evaluate_logic(
            node,
            {"a": "满足", "b": "不满足", "c": "无法判断"},
        )
        self.assertEqual(
            trace,
            {
                "type": "GROUP",
                "operator": "AND",
                "children": [
                    {"type": "RULE_REF", "ruleCode": "a", "result": "满足"},
                    {
                        "type": "GROUP",
                        "operator": "OR",
                        "children": [
                            {"type": "RULE_REF", "ruleCode": "b", "result": "不满足"},
                            {"type": "RULE_REF", "ruleCode": "c", "result": "无法判断"},
                        ],
                        "result": "无法判断",
                    },
                ],
                "result": "无法判断",
            },
        )

    def test_missing_rule_result_defaults_to_unknown(self):
        self.assertEqual(evaluator.evaluate_logic(rule("missing"), {}), {
            "type": "RULE_REF", "ruleCode": "missing", "result": "无法判断"
        })

    def test_rejects_invalid_nodes_with_stable_messages(self):
        cases = [
            (None, "Node must be an object."),
            ({"type": "OTHER"}, "Node type must be GROUP or RULE_REF."),
            ({"type": "GROUP", "operator": "X", "children": [rule("a")]}, "GROUP operator must be AND or OR."),
            ({"type": "GROUP", "operator": "AND", "children": []}, "GROUP must have nonempty children."),
            ({"type": "RULE_REF"}, "RULE_REF ruleCode must be a nonempty string."),
            ({"type": "RULE_REF", "ruleCode": "   "}, "RULE_REF ruleCode must be a nonempty string."),
        ]
        for node, message in cases:
            with self.subTest(node=node):
                with self.assertRaisesRegex(ValueError, "^" + message.replace(".", r"\.") + "$"):
                    evaluator.evaluate_logic(node, {})

    def test_rejects_invalid_rule_results_with_a_stable_message(self):
        with self.assertRaisesRegex(ValueError, r"^Rule result must be one of: 不满足, 不适用, 无法判断, 满足\.$"):
            evaluator.evaluate_logic(rule("a"), {"a": "通过"})
        with self.assertRaisesRegex(ValueError, r"^rule_results must be an object\.$"):
            evaluator.evaluate_logic(rule("a"), [])

    def test_rejects_cycles_without_recursion_error(self):
        node = group("AND", rule("a"))
        node["children"].append(node)
        with self.assertRaisesRegex(ValueError, r"^Logic tree contains a cycle\.$"):
            evaluator.evaluate_logic(node, {"a": "满足"})

    def test_rejects_trees_deeper_than_supported_limit_without_recursion_error(self):
        node = rule("a")
        for _ in range(evaluator.MAX_LOGIC_DEPTH + 1):
            node = group("AND", node)
        with self.assertRaisesRegex(ValueError, r"^Logic tree exceeds the supported depth\.$"):
            evaluator.evaluate_logic(node, {"a": "满足"})

    def test_does_not_mutate_inputs_and_trace_is_json_serializable(self):
        node = group("OR", rule("b"), rule("a"))
        results = {"a": "满足", "b": "不适用"}
        original_node = copy.deepcopy(node)
        original_results = copy.deepcopy(results)
        trace = evaluator.evaluate_logic(node, results)
        self.assertEqual(node, original_node)
        self.assertEqual(results, original_results)
        self.assertEqual([child["ruleCode"] for child in trace["children"]], ["b", "a"])
        self.assertEqual(json.loads(json.dumps(trace, ensure_ascii=False)), trace)


if __name__ == "__main__":
    unittest.main()
