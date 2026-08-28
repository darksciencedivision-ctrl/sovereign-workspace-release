from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    validator: str
    passed: bool
    measured: dict[str, Any] = field(default_factory=dict)
    failures: tuple[str, ...] = ()


def sandbox_exit_status(exit_code: int) -> ValidationResult:
    return ValidationResult("sandbox_exit_status", exit_code == 0, {"exit_code": exit_code}, () if exit_code == 0 else (f"sandbox exited {exit_code}",))


def code_vs_tests(*, compile_exit: int, test_exit: int, tests_collected: int) -> ValidationResult:
    failures = []
    if compile_exit != 0:
        failures.append("compile failed")
    if tests_collected < 1:
        failures.append("no tests collected")
    if test_exit != 0:
        failures.append("tests failed")
    return ValidationResult("code_vs_tests", not failures, {"compile_exit": compile_exit, "test_exit": test_exit, "tests_collected": tests_collected}, tuple(failures))


def exact_answer(actual: Any, expected: Any) -> ValidationResult:
    passed = actual == expected
    return ValidationResult("exact_answer", passed, {}, () if passed else ("answer mismatch",))


def structured_output(value: str | Any, schema: dict[str, Any]) -> ValidationResult:
    try:
        document = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as exc:
        return ValidationResult("structured_output", False, {}, (f"invalid JSON: {exc.msg}",))
    failures: list[str] = []
    _validate(document, schema, "$", failures)
    return ValidationResult("structured_output", not failures, {}, tuple(failures))


def tool_call_schema(call: Any, schema: dict[str, Any]) -> ValidationResult:
    result = structured_output(call, schema)
    return ValidationResult("tool_call_schema", result.passed, result.measured, result.failures)


def _validate(value: Any, schema: dict[str, Any], path: str, failures: list[str]) -> None:
    if "enum" in schema and value not in schema["enum"]:
        failures.append(f"{path}: value not in enum")
        return
    expected = schema.get("type")
    if isinstance(expected, list):
        if value is None and "null" in expected:
            return
        expected = next((item for item in expected if item != "null"), None)
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if expected in checks and not checks[expected](value):
        failures.append(f"{path}: expected {expected}")
        return
    if expected == "object":
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                failures.append(f"{path}: missing required property {name}")
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    failures.append(f"{path}: unexpected property {name}")
        for name, child_schema in properties.items():
            if name in value:
                _validate(value[name], child_schema, f"{path}.{name}", failures)
    elif expected == "array" and "items" in schema:
        for index, item in enumerate(value):
            _validate(item, schema["items"], f"{path}[{index}]", failures)
