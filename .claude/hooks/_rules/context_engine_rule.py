"""Regla UserPromptSubmit — inyecta ContextPack ensamblado en cada prompt del usuario.

Integra el context_engine con el sistema de hooks para que el modelo reciba
símbolos relevantes, memorias y esqueletos de archivos en cada turno.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RuleSeverity = Literal["continue", "context", "block"]

_DEFAULT_TOKEN_BUDGET = 4_000

# Importación al nivel de módulo — permite patch en tests y falla limpio si no existe.
try:
    from higpertext.kernel.application.context_engine import ContextAssembler
    from higpertext.kernel.domain.context_engine import TaskIntent

    _ENGINE_AVAILABLE = True
except ImportError:
    _ENGINE_AVAILABLE = False


@dataclass
class RuleResult:
    severity: RuleSeverity
    message: str = ""


def inject_context_pack(root: Path, prompt: str) -> RuleResult | None:
    """Ensambla un ContextPack a partir del prompt y lo retorna como contexto.

    Returns:
        RuleResult con el pack en markdown, o None si no hay contenido relevante
        o si el context_engine no está disponible.
    """
    if not _ENGINE_AVAILABLE:
        return None

    budget = _resolve_budget()
    intent = TaskIntent.from_goal(goal=prompt, task_type="general", token_budget=budget)

    try:
        assembler = ContextAssembler(project_root=root)
        pack = assembler.assemble(intent)
    except Exception:
        return None

    if not pack.relevant_symbols and not pack.applicable_memories:
        return None

    return RuleResult(severity="context", message=_format_pack(pack))


def _resolve_budget() -> int:
    """Retorna el budget de tokens desde variable de entorno o usa el default."""
    try:
        return int(os.environ.get("HIGPERTEXT_CONTEXT_BUDGET", _DEFAULT_TOKEN_BUDGET))
    except ValueError:
        return _DEFAULT_TOKEN_BUDGET


def _format_pack(pack: object) -> str:
    """Envuelve el markdown del ContextPack en un banner higpertext."""
    lines = [
        "╔─ HIGPERTEXT  ·  Context Engine — Contexto ensamblado ──────",
        # type: ignore[attr-defined]
        f"│  Tokens estimados : {pack.estimated_tokens:,} / {pack.intent.token_budget:,}",
        f"│  Símbolos         : {len(pack.relevant_symbols)}",  # type: ignore[attr-defined]
        f"│  Memorias         : {len(pack.applicable_memories)}",  # type: ignore[attr-defined]
        f"│  Esqueletos       : {len(pack.skeletons)}",  # type: ignore[attr-defined]
        "╠────────────────────────────────────────────────────────────",
        pack.to_markdown(),  # type: ignore[attr-defined]
        "╚───────────────────────────────────────────────────────────",
    ]
    return "\n".join(lines)
