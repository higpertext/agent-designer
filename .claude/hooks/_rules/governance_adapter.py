"""Adaptador de gobernanza — lee contratos de dominio y expone valores para hooks."""

from __future__ import annotations
import sys
from pathlib import Path

DEFAULT_HARD_BLOCKS = [
    (r"\bsudo\b", "sudo no está permitido en este entorno por política de seguridad"),
    (
        r"\bgit\s+push\b",
        "git push es una acción exclusiva del usuario"
        " — el agente no puede publicar cambios al remoto",
    ),
]
DEFAULT_FUNC_LIMIT = 30
DEFAULT_CLASS_LIMIT = 200
DEFAULT_UNCOMMITTED_LIMIT = 5


def _load_domain(root: Path, name: str) -> dict:
    """Carga un archivo de contrato de dominio via ContractLoader."""
    core_path = str(root / "src")
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    try:
        from higpertext.kernel.infrastructure import ContractLoader

        return getattr(ContractLoader(root), f"load_{name}")()
    except Exception:
        return {}


def get_bash_blocks(root: Path) -> list[tuple[str, str]]:
    """Bloqueos hard de bash: security_guardrails + branching_strategy."""
    blocks: list[tuple[str, str]] = []
    for source in ("security_guardrails", "branching_strategy"):
        data = _load_domain(root, source)
        for entry in data.get("blocked_patterns", []) + data.get("rules", []):
            pattern = entry.get("pattern")
            reason = entry.get("reason", "Comando bloqueado por política de gobernanza")
            if pattern:
                blocks.append((pattern, reason))
    return blocks or DEFAULT_HARD_BLOCKS


def get_deployment_blocks(root: Path) -> list[tuple[str, str, str]]:
    """Retorna (pattern, reason, severity) desde deployment_gates.json."""
    data = _load_domain(root, "deployment_gates")
    result = []
    for entry in data.get("blocked_patterns", []):
        pattern = entry.get("pattern")
        reason = entry.get("reason", "Acción de deployment bloqueada por gobernanza")
        severity = entry.get("severity", "warn")
        if pattern:
            result.append((pattern, reason, severity))
    return result


def get_code_limits(root: Path) -> tuple[int, int]:
    """Retorna (max_function_lines, max_class_lines) desde quality_gates.json."""
    data = _load_domain(root, "quality_gates")
    limits = data.get("code_quality_limits", {})
    return (
        limits.get("max_function_lines", DEFAULT_FUNC_LIMIT),
        limits.get("max_class_lines", DEFAULT_CLASS_LIMIT),
    )


def get_session_limits(root: Path) -> int:
    """Retorna max_uncommitted_files desde quality_gates.json."""
    data = _load_domain(root, "quality_gates")
    return data.get("gitflow_limits", {}).get("max_uncommitted_files", DEFAULT_UNCOMMITTED_LIMIT)
