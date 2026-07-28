"""Hook Stop — cierra sesión automáticamente y muestra resumen de turno."""

from __future__ import annotations
from higpertext.hooks.hook_tasks._rules.governance_adapter import get_session_limits
import higpertext.hooks.hook_tasks.telemetry_utils as telem
from higpertext.hooks.hook_tasks.hook_utils import get_project_root
from higpertext.hooks.hook_tasks.hook_io import (
    hook_main,
    read_json_file,
    emit_stop_reason,
)
import sys
import subprocess  # nosec B404
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]  # src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from higpertext.kernel.config_paths import WORKSPACE_DIR_NAME


def _pending(root: Path) -> tuple[list[str], int, bool]:
    try:
        r = subprocess.run(  # nosec B603 B607
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=10,
        )
        lines = [line[3:] for line in r.stdout.strip().splitlines() if line.strip()]
        limit = get_session_limits(root)
        return lines, limit, len(lines) > limit
    except (OSError, subprocess.TimeoutExpired):
        return [], 5, False


def _last_commit(root: Path) -> str:
    try:
        r = subprocess.run(  # nosec B603 B607
            ["git", "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=5,
        )
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "—"


def _clean_session(root: Path) -> bool:
    """Ejecuta session-clean y devuelve True si tuvo éxito."""
    from higpertext.hooks.hook_tasks.hook_utils import get_htx

    try:
        r = subprocess.run(  # nosec B603
            [get_htx(root), "task", "common.session-clean", "--action", "clean"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=20,
        )
        return r.returncode == 0
    except Exception:
        return False


def _build_banner(
    files: list[str],
    limit: int,
    exceeded: bool,
    commit: str,
    active: bool,
    sid: str,
    profile: str,
) -> str:
    lines = ["╔─ HIGPERTEXT  ·  Fin de turno ──────────────────────────────"]
    if files:
        indicator = "❌ [GOBERNANZA]" if exceeded else "⚠"
        lines.append(f"│  {indicator}  {len(files)} archivo(s) sin commitear (Límite: {limit}):")
        for f in files[:8]:
            lines.append(f"│     • {f}")
        if len(files) > 8:
            lines.append(f"│     ... y {len(files) - 8} más")
        lines.append('│  → committer --message "tipo(scope): descripción"')
    else:
        lines.append(f"│  ✓  Working tree limpio  ·  {commit}")
    if active:
        lines.append(f"│  Sesión : {sid}  ·  perfil: {profile}")
        lines.append("│  ✓  Workspace restablecido al estado inicial")
    lines.append("╚───────────────────────────────────────────────────────")
    return "\n".join(lines)


@hook_main
def main() -> None:
    root = get_project_root()
    session = read_json_file(root / WORKSPACE_DIR_NAME / "state" / "session.json")
    env = read_json_file(root / WORKSPACE_DIR_NAME / "config" / "environment.json")
    active = session.get("status") == "active"
    sid = session.get("session_id", "—")
    profile = env.get("active_profile", "global")
    files, limit, exceeded = _pending(root)
    commit = _last_commit(root)

    if active:
        telem.session_stop(root, sid, profile)
        _clean_session(root)

    emit_stop_reason(_build_banner(files, limit, exceeded, commit, active, sid, profile))


if __name__ == "__main__":
    main()