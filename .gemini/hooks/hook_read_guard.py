"""Hook PreToolUse:Read — bloquea lecturas completas de archivos grandes."""

from __future__ import annotations
from higpertext.hooks.hook_tasks.hook_utils import get_project_root
from higpertext.hooks.hook_tasks.hook_io import (
    hook_main,
    read_payload,
    emit_continue,
    emit_block,
)

import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _threshold_bytes() -> int:
    try:
        return int(os.environ.get("HIGPERTEXT_READ_GUARD_BYTES", str(100 * 1024)))
    except ValueError:
        return 100 * 1024


def _extract_path(tool_input: dict) -> str:
    return (
        tool_input.get("filePath")
        or tool_input.get("filepath")
        or tool_input.get("path")
        or tool_input.get("file")
        or ""
    )


def _has_range(tool_input: dict) -> bool:
    return any(
        key in tool_input and tool_input.get(key) not in (None, "") for key in ("offset", "limit")
    )


def evaluate_read_guard(tool_input: dict, root: Path) -> str:
    """Devuelve mensaje de bloqueo o cadena vacía si la lectura es segura."""
    raw_path = _extract_path(tool_input)
    if not raw_path or _has_range(tool_input):
        return ""
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    if not path.exists() or not path.is_file():
        return ""
    threshold = _threshold_bytes()
    size = path.stat().st_size
    if size <= threshold:
        return ""
    display = raw_path
    return "\n".join(
        [
            "╔─ HIGPERTEXT  ·  Bloqueo de Read masivo ───────────────────",
            f"│  Archivo : {display} ({size / 1024:.1f} KB)",
            f"│  Límite  : {threshold / 1024:.1f} KB",
            "│  ⚠  Evita leer el archivo completo para no saturar contexto.",
            "│  → Usa lectura inteligente:",
            f"│    htx task common.smart-read --path {display} --mode auto",
            "│  → O inspecciona firmas:",
            f"│    htx task common.code-skeletonizer --path {display}",
            "╚────────────────────────────────────────────────────────────",
        ]
    )


@hook_main
def main() -> None:
    payload = read_payload()
    message = evaluate_read_guard(payload.get("tool_input", {}), get_project_root())
    if message:
        emit_block("PreToolUse", message)
        return
    emit_continue()


if __name__ == "__main__":
    main()
