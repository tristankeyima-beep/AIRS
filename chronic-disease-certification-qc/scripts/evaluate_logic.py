"""Evaluate chronic-disease certification logic trees with four result states."""

VALID_RESULTS = {"满足", "不满足", "无法判断", "不适用"}
MAX_LOGIC_DEPTH = 64
_RESULT_MESSAGE = "Rule result must be one of: 不满足, 不适用, 无法判断, 满足."


def _combine(operator, child_results):
    """Apply a GROUP operator after removing not-applicable children."""
    applicable_results = [result for result in child_results if result != "不适用"]
    if not applicable_results:
        return "不适用"
    if operator == "AND":
        if "不满足" in applicable_results:
            return "不满足"
        if "无法判断" in applicable_results:
            return "无法判断"
        return "满足"
    if "满足" in applicable_results:
        return "满足"
    if "无法判断" in applicable_results:
        return "无法判断"
    return "不满足"


def evaluate_logic(node, rule_results):
    """Return a JSON-serializable evaluation trace for a logic-tree ``node``.

    ``rule_results`` maps rule codes to one of the four supported result states.
    Missing referenced rules are treated as ``无法判断``.  The input node and result
    mapping are only read; the returned trace is a newly created object.
    """
    if not isinstance(rule_results, dict):
        raise ValueError("rule_results must be an object.")

    def evaluate(current, depth, ancestors):
        if depth > MAX_LOGIC_DEPTH:
            raise ValueError("Logic tree exceeds the supported depth.")
        if not isinstance(current, dict):
            raise ValueError("Node must be an object.")

        current_id = id(current)
        if current_id in ancestors:
            raise ValueError("Logic tree contains a cycle.")

        node_type = current.get("type")
        if node_type == "RULE_REF":
            rule_code = current.get("ruleCode")
            if not isinstance(rule_code, str) or not rule_code.strip():
                raise ValueError("RULE_REF ruleCode must be a nonempty string.")
            result = rule_results.get(rule_code, "无法判断")
            if not isinstance(result, str) or result not in VALID_RESULTS:
                raise ValueError(_RESULT_MESSAGE)
            return {"type": "RULE_REF", "ruleCode": rule_code, "result": result}

        if node_type != "GROUP":
            raise ValueError("Node type must be GROUP or RULE_REF.")
        operator = current.get("operator")
        if operator not in ("AND", "OR"):
            raise ValueError("GROUP operator must be AND or OR.")
        children = current.get("children")
        if not isinstance(children, list) or not children:
            raise ValueError("GROUP must have nonempty children.")

        child_ancestors = ancestors | {current_id}
        trace_children = [
            evaluate(child, depth + 1, child_ancestors)
            for child in children
        ]
        result = _combine(operator, [child["result"] for child in trace_children])
        return {
            "type": "GROUP",
            "operator": operator,
            "children": trace_children,
            "result": result,
        }

    return evaluate(node, 0, frozenset())
