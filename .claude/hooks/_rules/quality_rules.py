"""Reglas de evaluación para escritura de código (PreToolUse:Write|Edit).

Cada función retorna una RuleResult o None si no aplica.
"""

from __future__ import annotations
from .governance_adapter import get_code_limits
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RuleSeverity = Literal["continue", "context", "block"]


_PYTHON_FILE = re.compile(r"\.py$")


@dataclass
class RuleResult:
    severity: RuleSeverity
    message: str = ""


def is_python_file(file_path: str) -> bool:
    return bool(_PYTHON_FILE.search(file_path))


# ── Regla 1: Longitud de funciones y clases ───────────────────────────────────


def check_code_length(file_path: str, root: Path) -> RuleResult | None:
    func_limit, class_limit = get_code_limits(root)
    violations = _scan_file(file_path, func_limit, class_limit)
    if not violations:
        return None
    msg = "[HIGPERTEXT QUALITY GATE] Violaciones detectadas:\n" + "\n".join(violations)
    return RuleResult(severity="context", message=msg)


def _check_func_limit(in_func: bool, current_line: int, func_start: int, func_limit: int, func_name: str, violations: list[str]) -> None:
    if in_func and (current_line - func_start) > func_limit:
        violations.append(
            f"  función '{func_name}' excede {func_limit} líneas (línea {func_start})"
        )


def _check_class_limit(in_class: bool, current_line: int, class_start: int, class_limit: int, class_name: str, violations: list[str]) -> None:
    if in_class and (current_line - class_start) > class_limit:
        violations.append(
            f"  clase '{class_name}' excede {class_limit} líneas (línea {class_start})"
        )


def _scan_file(filepath: str, func_limit: int, class_limit: int) -> list[str]:
    violations: list[str] = []
    try:
        lines = Path(filepath).read_text(encoding="utf-8").splitlines()
    except OSError:
        return violations

    in_func = False
    in_class = False
    func_start = 0
    class_start = 0
    func_name = ""
    class_name = ""

    total = len(lines)
    for i, line in enumerate(lines, 1):
        m_func = re.match(r"\s*def\s+(\w+)", line)
        m_class = re.match(r"\s*class\s+(\w+)", line)

        if m_func:
            _check_func_limit(in_func, i, func_start, func_limit, func_name, violations)
            in_func, func_start, func_name = True, i, m_func.group(1)

        elif m_class:
            _check_class_limit(in_class, i, class_start, class_limit, class_name, violations)
            in_class, class_start, class_name = True, i, m_class.group(1)

    # Chequeo final: última función/clase del archivo
    _check_func_limit(in_func, total + 1, func_start, func_limit, func_name, violations)
    _check_class_limit(in_class, total + 1, class_start, class_limit, class_name, violations)

    return violations
