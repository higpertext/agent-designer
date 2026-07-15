"""Reglas de seguridad comunes para hooks de asistentes higpertext."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

RuleSeverity = Literal["continue", "context", "warn", "ask", "block"]


@dataclass
class RuleResult:
    severity: RuleSeverity
    message: str = ""
    replacement_output: str = ""


_SENSITIVE_PATH_PATTERNS = [
    r"(^|/)\.env(\..*)?$",
    r"(^|/)\.npmrc$",
    r"(^|/)\.pypirc$",
    r"(^|/)\.netrc$",
    r"(^|/)id_(rsa|dsa|ecdsa|ed25519)$",
    r"\.(pem|key|p12|pfx|crt)$",
    r"(^|/)(secrets?|credentials?)(/|\.|$)",
    r"(^|/)\.aws/credentials$",
    r"(^|/)\.azure(/|$)",
    r"(^|/)\.kube/config$",
]


def evaluate_command_guard(command: str, root: Path) -> RuleResult | None:
    """Evalúa comandos peligrosos definidos por gobernanza."""
    if not command:
        return None
    for pattern, reason, severity in _command_rules(root):
        if re.search(pattern, command, re.IGNORECASE):
            normalized = _normalize_severity(severity)
            return RuleResult(
                severity=normalized,
                message=_format_command_message(command, reason, normalized),
            )
    return None


def evaluate_path_guard(tool_name: str, tool_input: dict[str, Any]) -> RuleResult | None:
    """Bloquea acceso a rutas sensibles desde Read/Write/Edit."""
    path = _extract_path(tool_input)
    if not path or not _is_sensitive_path(path):
        return None
    return RuleResult(
        severity="block",
        message="\n".join(
            [
                "╔─ HIGPERTEXT  ·  Security Guard ───────────────────────────",
                f"│  ✗  {tool_name} sobre ruta sensible bloqueado.",
                f"│  Ruta: {path}",
                "│  Usa una capacidad segura o pide aprobación humana explícita.",
                "╚────────────────────────────────────────────────────────────",
            ]
        ),
    )


def mask_tool_output(tool_response: Any, root: Path) -> RuleResult | None:
    """Enmascara secretos presentes en outputs de herramientas."""
    output = _stringify_response(tool_response)
    if not output:
        return None
    masked = output
    for pattern, replacement in _masking_patterns(root):
        masked = re.sub(pattern, replacement, masked, flags=re.IGNORECASE | re.DOTALL)
    if masked == output:
        return None
    return RuleResult(
        severity="context",
        message="[HIGPERTEXT SECURITY] Se enmascararon secretos detectados en el output.",
        replacement_output=masked,
    )


def _command_rules(root: Path) -> list[tuple[str, str, str]]:
    data = _load_security_guardrails(root)
    entries = [
        (
            item.get("pattern", ""),
            item.get("reason", "Comando restringido por seguridad"),
            item.get("severity", "block"),
        )
        for item in data.get("blocked_patterns", [])
        if item.get("pattern")
    ]
    entries.extend(
        (
            item.get("pattern", ""),
            item.get("reason", "Acción requiere aprobación humana explícita"),
            "ask",
        )
        for item in data.get("approval_patterns", [])
        if item.get("pattern")
    )
    entries.extend(
        (
            item.get("pattern", ""),
            item.get("reason", "Acción potencialmente riesgosa"),
            item.get("severity", "warn"),
        )
        for item in data.get("warning_patterns", [])
        if item.get("pattern")
    )
    forbidden = data.get("guardrails", {}).get("forbidden_commands", [])
    entries.extend(
        (
            re.escape(command),
            f"'{command}' está prohibido por política de seguridad",
            "block",
        )
        for command in forbidden
        if command
    )
    return entries


def _normalize_severity(value: str) -> RuleSeverity:
    lowered = str(value).lower().strip()
    if lowered in {"warn", "warning", "context"}:
        return "warn"
    if lowered in {"ask", "approval", "human_approval"}:
        return "ask"
    return "block"


def _format_command_message(command: str, reason: str, severity: RuleSeverity) -> str:
    if severity == "warn":
        marker = "⚠"
        action = "Advertencia: la acción continuará, pero queda registrada."
    elif severity == "ask":
        marker = "?"
        action = "Requiere aprobación humana explícita antes de ejecutar."
    else:
        marker = "✗"
        action = "Comando bloqueado por política de seguridad."
    return "\n".join(
        [
            "╔─ HIGPERTEXT  ·  Security Guard ───────────────────────────",
            f"│  {marker}  {reason}",
            f"│  Severidad: {severity}",
            f"│  Acción   : {action}",
            f"│  Comando  : {command}",
            "╚────────────────────────────────────────────────────────────",
        ]
    )


def _masking_patterns(root: Path) -> list[tuple[str, str]]:
    data = _load_security_guardrails(root)
    configured = data.get("data_masking", {}).get("patterns", [])
    patterns = [
        (item.get("regex", ""), item.get("mask", "[MASKED]"))
        for item in configured
        if item.get("regex")
    ]
    patterns.extend(
        [
            (
                r"(?i)(token|password|secret|api[_-]?key)\s*[:=]\s*['\"]?[^\s'\"]{8,}",
                r"\1=********[MASKED]",
            ),
            (r"(?i)bearer\s+[a-z0-9._\-]{20,}", "Bearer ********[MASKED]"),
        ]
    )
    return patterns


def _load_security_guardrails(root: Path) -> dict[str, Any]:
    path = root / "src" / "config" / "governance" / "security_guardrails.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _extract_path(tool_input: dict[str, Any]) -> str:
    return str(
        tool_input.get("filePath")
        or tool_input.get("filepath")
        or tool_input.get("path")
        or tool_input.get("file_path")
        or tool_input.get("file")
        or ""
    )


def _is_sensitive_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(
        re.search(pattern, normalized, re.IGNORECASE) for pattern in _SENSITIVE_PATH_PATTERNS
    )


def _stringify_response(tool_response: Any) -> str:
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        for key in ("output", "content", "text", "stdout"):
            if key in tool_response and isinstance(tool_response[key], str):
                return tool_response[key]
    try:
        return json.dumps(tool_response, ensure_ascii=False)
    except TypeError:
        return str(tool_response)
