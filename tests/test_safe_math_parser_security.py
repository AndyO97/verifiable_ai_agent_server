"""Security-focused tests for the SafeMathEvaluator parser."""

import pytest

from backend.agent_backend import SafeMathEvaluator


def test_safe_math_rejects_import_payload() -> None:
    evaluator = SafeMathEvaluator()
    with pytest.raises(ValueError):
        evaluator.evaluate("__import__('os').system('whoami')")


def test_safe_math_rejects_attribute_traversal_payload() -> None:
    evaluator = SafeMathEvaluator()
    with pytest.raises(ValueError):
        evaluator.evaluate("().__class__.__mro__")


def test_safe_math_rejects_control_flow_payload() -> None:
    evaluator = SafeMathEvaluator()
    with pytest.raises(ValueError):
        evaluator.evaluate("for i in range(10): i")


def test_safe_math_rejects_variable_assignment_payload() -> None:
    evaluator = SafeMathEvaluator()
    with pytest.raises(ValueError):
        evaluator.evaluate("x = 5")


def test_safe_math_accepts_supported_math_expression() -> None:
    evaluator = SafeMathEvaluator()
    result = evaluator.evaluate("max(2, 3, 1) + round(3.14159, 2)")
    assert result == pytest.approx(6.14)
