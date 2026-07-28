"""Protocolo I/O centralizado para hook tasks de higpertext.

Single source of truth para:
- Leer el payload de stdin (read_payload, read_tool_command)
- Leer archivos JSON del disco (read_json_file)
- Emitir respuestas JSON al runtime del asistente
  (emit_continue, emit_context, emit_block, emit_stop_reason)
- Whitelist cross-platform de comandos permitidos (WHITELIST)
- Directorios de skills/subagentes por asistente (SKILL_DIRS, AGENT_DIRS)
- Decorador @hook_main que envuelve cualquier main() con manejo de errores
"""

from __future__ import annotations
from typing import Callable
import functools
import json
import re
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]  # src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# Directorios efímeros de sesión por asistente — single source para todos los hooks
SKILL_DIRS: dict[str, str] = {
    "claude": ".claude/skills",
    "gemini": ".gemini/skills",
    "antigravity": ".agents/skills",
    "codex": ".agents/skills",
    "opencode": ".opencode/skills",
    "copilot": ".github/skills",
}

AGENT_DIRS: dict[str, str] = {
    "claude": ".claude/subagents",
    "gemini": ".gemini/subagents",
    "antigravity": ".agents/subagents",
    "codex": ".agents/subagents",
    "opencode": ".opencode/subagents",
    "copilot": ".github/subagents",
}

# Single source: permite htx.py directo o venv en Linux/Windows
WHITELIST = re.compile(r"python htx\.py|\.venv[/\\](bin|Scripts)[/\\]python")


def read_json_file(path: Path) -> dict:
    """Lee y parsea un archivo JSON del disco. Retorna {} ante cualquier error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_payload() -> dict:
    """Lee y parsea el JSON de stdin. Retorna {} ante cualquier error."""
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, EOFError):
        return {}


def read_tool_command(payload: dict) -> str:
    """Extrae el comando de tool_input, con fallback a CommandLine (PowerShell)."""
    tool_input = payload.get("tool_input", {})
    return tool_input.get("command") or tool_input.get("CommandLine") or ""


def emit_continue(error: str = "") -> None:
    """Emite continue:True, opcionalmente con campo error."""
    out: dict = {"continue": True}
    if error:
        out["error"] = error
    print(json.dumps(out))


def emit_context(event: str, text: str) -> None:
    """Emite continue:True con additionalContext (hook informativo)."""
    print(
        json.dumps(
            {
                "continue": True,
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": text,
                },
            }
        )
    )


def emit_block(event: str, text: str) -> None:
    """Emite continue:False bloqueando la herramienta (hard block)."""
    print(
        json.dumps(
            {
                "continue": False,
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": text,
                },
            }
        )
    )


def emit_stop_reason(text: str) -> None:
    """Emite continue:True con stopReason para el evento Stop."""
    print(json.dumps({"continue": True, "stopReason": text}))


def hook_main(fn: Callable) -> Callable:
    """Decorador que envuelve main() capturando excepciones → emit_continue+error."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            fn(*args, **kwargs)
        except Exception as exc:
            emit_continue(str(exc))

    return wrapper
