"""Reglas de gestión de contexto para PreCompact y PostToolUse.

check_context_pressure — preserva estado higpertext crítico antes de compresión.
check_large_output     — avisa al modelo cuando un tool output es demasiado grande.
check_window_pressure  — mide uso acumulado de la ventana de contexto por turno.
"""

from __future__ import annotations
from higpertext.kernel.config_paths import WORKSPACE_DIR_NAME
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RuleSeverity = Literal["continue", "context", "block"]


def _large_output_threshold() -> int:
    """Umbral de chars para output masivo. Configurable vía HIGPERTEXT_LARGE_OUTPUT_CHARS."""
    try:
        return int(os.environ.get("HIGPERTEXT_LARGE_OUTPUT_CHARS", "5000"))
    except ValueError:
        return 5_000


# Mantiene compatibilidad con imports existentes (tests, otros módulos)
LARGE_OUTPUT_CHARS = _large_output_threshold()


@dataclass
class RuleResult:
    severity: RuleSeverity
    message: str = ""


# ── Regla 1: Preservar estado higpertext antes de compresión (PreCompress) ─────────


def check_context_pressure(root: Path) -> RuleResult:
    """Emite resumen compacto de sesión para preservarlo tras la compresión."""
    session = _read_json(root / WORKSPACE_DIR_NAME / "state" / "session.json")
    env = _read_json(root / WORKSPACE_DIR_NAME / "config" / "environment.json")

    sid = session.get("session_id", "—")
    profile = env.get("active_profile", "—")
    asst = env.get("assistant", "claude")
    active = session.get("status") == "active"

    if not active:
        return RuleResult(severity="continue")

    skills = _list_dir_names(root / _SKILL_DIRS.get(asst, ".claude/skills"))
    subagents = _list_dir_names(root / _AGENT_DIRS.get(asst, ".claude/subagents"), "*.md")

    lines = [
        "╔─ HIGPERTEXT  ·  Contexto preservado (pre-compresión) ──────",
        f"│  Sesión  : {sid}",
        f"│  Perfil  : {profile}",
        f"│  Skills  : {', '.join(skills) or '—'}",
        f"│  Agentes : {', '.join(subagents) or '—'}",
        "│  → Continúa usando `htx task <cap>` para",
        "│    invocar capacidades higpertext.",
        "╚───────────────────────────────────────────────────────",
    ]
    return RuleResult(severity="context", message="\n".join(lines))


# ── Regla 2: Aviso de output masivo (PostToolUse) ─────────────────────────────


def check_large_output(payload: dict) -> RuleResult | None:
    """Avisa si la respuesta de un tool supera el umbral de chars."""
    threshold = _large_output_threshold()
    tool_response = payload.get("tool_response", {})
    output_str = json.dumps(tool_response, ensure_ascii=False)
    if len(output_str) <= threshold:
        return None
    tool = payload.get("tool_name", "unknown")
    n_lines = output_str.count("\n") + 1
    suggestion = _large_output_suggestion(tool)
    return RuleResult(
        severity="context",
        message="\n".join(
            [
                "╔─ HIGPERTEXT  ·  Output masivo detectado ───────────────────",
                f"│  Tool    : {tool}",
                f"│  Tamaño  : {len(output_str):,} chars"
                f" · ~{n_lines:,} líneas (límite {threshold:,})",
                "│  ⚠  No re-emitas este blob en tu respuesta.",
                "│     Referencia el archivo por path:line. Si necesitas",
                "│     releer, usa offset/limit en vez de leer todo.",
                f"│  → {suggestion}",
                "╚───────────────────────────────────────────────────────",
            ]
        ),
    )


def _large_output_suggestion(tool: str) -> str:
    """Devuelve acción concreta según herramienta que generó output masivo."""
    normalized = tool.lower()
    if normalized == "read":
        return "Usa: htx task common.smart-read --path <archivo> --mode auto"
    if normalized == "bash":
        return "Si fue cat/head/less, usa: htx task common.code-skeletonizer --path <archivo>"
    if "grep" in normalized or normalized == "common.grep-search":
        return "Reduce con --max_results, --max_per_file y --line_limit"
    return "Reduce la salida con filtros, rangos o capacidades smart-read/grep-search"


# ── Helpers ───────────────────────────────────────────────────────────────────
from higpertext.kernel.app_config import SKILL_DIRS as _SKILL_DIRS, AGENT_DIRS as _AGENT_DIRS


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _list_dir_names(path: Path, glob: str = "*") -> list[str]:
    if not path.exists():
        return []
    if glob == "*.md":
        return sorted(f.stem for f in path.glob(glob))
    return sorted(d.name for d in path.iterdir() if d.is_dir())


# ── Regla 3: Presión de ventana de contexto (PostToolUse) ────────────────────


def _window_config() -> tuple[int, float, float]:
    """Retorna (window_limit, warn_pct, critical_pct) desde env vars o defaults."""
    try:
        limit = int(os.environ.get("HIGPERTEXT_WINDOW_LIMIT", "200000"))
    except ValueError:
        limit = 200_000
    try:
        warn = float(os.environ.get("HIGPERTEXT_WARN_PCT", "0.70"))
    except ValueError:
        warn = 0.70
    try:
        critical = float(os.environ.get("HIGPERTEXT_CRITICAL_PCT", "0.90"))
    except ValueError:
        critical = 0.90
    return limit, warn, critical


def check_window_pressure(payload: dict, root: Path) -> RuleResult | None:
    """Acumula tokens del tool output y alerta si la ventana supera los umbrales.

    Returns:
        None si está bajo el umbral de warning.
        RuleResult(context) con banner WARNING entre warn y critical.
        RuleResult(context) con banner CRITICAL si supera el umbral crítico.
    """
    try:
        from higpertext.kernel.domain.context_engine import (
            load_window_state,
            save_window_state,
        )
    except ImportError:
        return None

    limit, warn_pct, critical_pct = _window_config()
    output_str = json.dumps(payload.get("tool_response", {}), ensure_ascii=False)
    new_tokens = int(len(output_str) / 3.5)

    state = load_window_state(root)
    state.add(new_tokens)
    save_window_state(root, state)

    usage = state.usage_pct(limit)
    if usage < warn_pct:
        return None

    level = "🔴 CRITICAL" if usage >= critical_pct else "🟡 WARNING"
    action = (
        "Ejecuta /compact para comprimir el historial antes de continuar."
        if usage >= critical_pct
        else "Considera ejecutar /compact pronto."
    )
    return RuleResult(
        severity="context",
        message="\n".join(
            [
                f"╔─ HIGPERTEXT  ·  Ventana de Contexto  ·  {level} ─────────────",
                f"│  Uso estimado : {
                state.accumulated_tokens:,} / {
                limit:,} tokens  ({
                usage * 100:.1f}%)",
                f"│  Turno actual : {state.turn}",
                f"│  ⚠  {action}",
                "╚──────────────────────────────────────────────────────────────",
            ]
        ),
    )