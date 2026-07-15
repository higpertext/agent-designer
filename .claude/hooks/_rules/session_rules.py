"""Reglas de sesión para UserPromptSubmit.

Inyecta estado de sesión y contexto de skills activas en cada prompt.
"""

from __future__ import annotations
from higpertext.kernel.config_paths import WORKSPACE_DIR_NAME
import json
import platform
import shutil
# Auto-start usa lista de argumentos sin shell.
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from higpertext.kernel.infrastructure.logger import get_logger

_log = get_logger()

try:
    from higpertext.kernel.htx_resolver import get_htx_cmd
except ImportError:
    get_htx_cmd = None

try:
    from higpertext.kernel.domain.context_engine import reset_window_state
except ImportError:
    reset_window_state = None

try:
    import higpertext.hooks.hook_tasks.telemetry_utils as telem
except ImportError:
    telem = None

from higpertext.kernel.app_config import (
    ENVIRONMENT_FILE as _ENVIRONMENT_JSON,
    SESSION_FILE as _SESSION_JSON,
    SKILL_DIRS as _SKILL_DIRS,
    AGENT_DIRS as _AGENT_DIRS,
)
RuleSeverity = Literal["continue", "context", "block"]


@dataclass
class RuleResult:
    severity: RuleSeverity
    message: str = ""


# ── Auto-inicio de sesión ─────────────────────────────────────────────────────


def _get_htx(root: Path) -> list[str]:
    if get_htx_cmd is not None:
        try:
            return get_htx_cmd(root)
        except Exception as exc:
            _log.warning(f"[session] No se pudo resolver htx desde config: {exc}")

    venv_htx = root / ".venv" / ("Scripts" if platform.system() == "Windows" else "bin") / "htx"
    if venv_htx.exists():
        return [str(venv_htx)]
    if htx := shutil.which("htx"):
        return [htx]
    return [str(root / ".venv" / "bin" / "python"), str(root / "htx.py")]


def auto_start_session(root: Path) -> None:
    """Inicia sesión automáticamente si no hay una activa."""
    env = _read_json(root / WORKSPACE_DIR_NAME / "config" / _ENVIRONMENT_JSON)
    profile = env.get("active_profile", "software_developer")
    cmd = _get_htx(root) + [
        "task",
        "common.session-start",
        "--action",
        "start",
        "--profile",
        profile,
    ]
    try:
        subprocess.run(cmd, cwd=str(root), timeout=20, capture_output=True)  # nosec B603
    except (OSError, subprocess.SubprocessError) as exc:
        _log.warning(f"[session] Auto-start omitido: {exc}")


# ── Reset de ventana de contexto por turno ──────────────────────────────────


def reset_window_accumulator(root: Path) -> None:
    """Reinicia el acumulador de tokens de la ventana para el nuevo turno."""
    if reset_window_state is not None:
        try:
            reset_window_state(root)
        except Exception as exc:
            _log.warning(f"[session] No se pudo reiniciar window accumulator: {exc}")


# ── Regla 1: Estado de sesión (session_start) ─────────────────────────────────


def inject_session_status(root: Path) -> RuleResult:
    session = _read_json(root / WORKSPACE_DIR_NAME / "state" / _SESSION_JSON)
    env = _read_json(root / WORKSPACE_DIR_NAME / "config" / _ENVIRONMENT_JSON)
    profile = env.get("active_profile", "global")
    asst = env.get("assistant", "claude")
    active = session.get("status") == "active"
    sid = session.get("session_id", "—")

    if active and not _already_recorded(root, sid):
        if telem is not None:
            telem.session_start(root, sid, profile)
        reset_window_accumulator(root)

    if not active:
        available = _available_skills(root, profile)
        skills_hint = f"Skills disponibles : {', '.join(available)}" if available else ""
        lines = [
            "╔─ HIGPERTEXT  ·  Sin sesión activa ────────────────────────",
            f"│  Perfil : {profile}",
        ]
        if skills_hint:
            lines.append(f"│  {skills_hint}")
        lines += [
            f"│  → htx task common.session-start --profile {profile}",
            "╚──────────────────────────────────────────────────────",
        ]
        return RuleResult(severity="context", message="\n".join(lines))

    skills = _list_dir_names(root / _SKILL_DIRS.get(asst, ".claude/skills"))
    subagents = _list_dir_names(root / _AGENT_DIRS.get(asst, ".claude/subagents"), "*.md")
    lines = [
        "╔─ HIGPERTEXT  ·  Sesión activa ─────────────────────────────",
        f"│  {sid}  ·  perfil: {profile}",
        f"│  Skills     : {', '.join(skills) or '—'}",
        f"│  Subagentes : {', '.join(subagents) or '—'}",
        "╚───────────────────────────────────────────────────────",
    ]

    workflows = _available_workflows(root, profile)
    if workflows:
        wf_lines = ["╔─ HIGPERTEXT  ·  Workflows del perfil ──────────────────────"]
        for wf in workflows:
            wf_lines.append(f"│  [{wf['id']}]")
            wf_lines.append(f"│    Cuándo : {wf.get('when', '—')}")
            wf_lines.append(f"│    Comando: {wf.get('command', '—')}")
        wf_lines.append("╚───────────────────────────────────────────────────────")
        lines.append("\n".join(wf_lines))

    learned = _load_learned_profile(root)
    profile_block = _render_profile_block(learned)
    if profile_block:
        lines.append(profile_block)

    return RuleResult(severity="context", message="\n".join(lines))


# ── Regla 2: Contexto de skills activas (session_context) ────────────────────


def inject_skills_context(root: Path) -> RuleResult | None:
    session = _read_json(root / WORKSPACE_DIR_NAME / "state" / _SESSION_JSON)
    env = _read_json(root / WORKSPACE_DIR_NAME / "config" / _ENVIRONMENT_JSON)

    if session.get("status") != "active":
        return None

    asst = env.get("assistant", "claude")
    sid = session.get("session_id", "—")
    skills_dir = root / _SKILL_DIRS.get(asst, ".claude/skills")

    skill_entries: list[tuple[str, str]] = []
    if skills_dir.exists():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir():
                summary = _skill_summary(d)
                skill_entries.append((d.name, summary))

    if not skill_entries:
        return None

    lines = [f"╔─ HIGPERTEXT  ·  Contexto de sesión  ·  {sid} ─────────────"]
    lines.append("│  Skills activas:")
    for name, summary in skill_entries:
        desc = f"  {summary}" if summary else ""
        lines.append(f"│    • {name}{desc}")
    lines.append("╚───────────────────────────────────────────────────────")

    return RuleResult(severity="context", message="\n".join(lines))


# ── Helpers ───────────────────────────────────────────────────────────────────


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


def _available_skills(root: Path, profile: str) -> list[str]:
    data = _read_json(root / "src" / "config" / "profiles" / f"{profile}.json")
    return data.get("session_skills", [])


def _available_workflows(root: Path, profile: str) -> list[dict]:
    data = _read_json(root / "src" / "config" / "profiles" / f"{profile}.json")
    return data.get("workflows", [])


def _already_recorded(root: Path, session_id: str) -> bool:
    store = root / WORKSPACE_DIR_NAME / "state" / "telemetry.jsonl"
    if not store.exists():
        return False
    try:
        for line in store.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                if e.get("event") == "session_start" and e.get("session_id") == session_id:
                    return True
            except (json.JSONDecodeError, TypeError):
                continue
    except OSError:
        pass
    return False


def _load_learned_profile(root: Path) -> dict:
    return _read_json(root / WORKSPACE_DIR_NAME / "state" / "learned_profile.json")


def _render_profile_block(profile: dict) -> str | None:
    if not profile:
        return None
    strong = ", ".join(profile.get("strong_patterns", [])[:3]) or "—"
    weak = ", ".join(profile.get("weak_patterns", [])[:3]) or "—"
    adoption = profile.get("higpertext_adoption_trend", 0)
    topics = ", ".join(profile.get("commit_topics", [])[:4]) or "—"
    best = profile.get("best_session_pattern", "—")
    cost = profile.get("cost_per_commit_avg", 0.0)
    return "\n".join(
        [
            "╔─ HIGPERTEXT  ·  Perfil aprendido ──────────────────────────",
            f"│  Fortalezas    : {strong}",
            f"│  Debilidades   : {weak}",
            f"│  Adopción prom : {adoption}%",
            f"│  Temas commits : {topics}",
            f"│  Mejor patrón  : {best}",
            f"│  Costo/commit  : ${cost:.4f} USD",
            "╚───────────────────────────────────────────────────────",
        ]
    )


def _skill_summary(skill_dir: Path) -> str:
    md = skill_dir / "SKILL.md"
    if not md.exists():
        return ""
    try:
        for line in md.read_text(encoding="utf-8").splitlines()[1:]:
            s = line.strip()
            if s and not s.startswith("#"):
                return s[:90]
    except OSError:  # nosec B110
        pass
    return ""


def handle_compact_command(root: Path) -> RuleResult:
    """Genera el reporte de compactación y avisa de resetear el chat."""
    session = _read_json(root / WORKSPACE_DIR_NAME / "state" / _SESSION_JSON)
    env = _read_json(root / WORKSPACE_DIR_NAME / "config" / _ENVIRONMENT_JSON)
    sid = session.get("session_id", "—")
    profile = env.get("active_profile", "—")

    changed_files = []
    git_path = shutil.which("git") or "git"
    try:
        r = subprocess.run(
            [git_path, "status", "--porcelain"],  # nosec B603 B607
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=5,
        )
        changed_files = [line[3:].strip() for line in r.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        pass

    files_str = ", ".join(changed_files[:5]) or "Ninguno"
    if len(changed_files) > 5:
        files_str += f" y {len(changed_files) - 5} más"

    msg = "\n".join(
        [
            "╔─ HIGPERTEXT  ·  Checkpoint de Compactación ──────────────",
            f"│  Sesión Activa: {sid} ({profile})",
            f"│  Archivos Modificados: {files_str}",
            "│",
            "│  ⚠  ¡REQUERIDO!: Guarda/actualiza acuerdos y estado clave",
            "│     en '.memory/context.md' (o similar) antes de continuar.",
            "│  → Una vez guardado, escribe '/clear' o usa el botón de",
            "│    reseteo del chat para vaciar el historial redundante.",
            "╚───────────────────────────────────────────────────────",
        ]
    )
    return RuleResult(severity="context", message=msg)
