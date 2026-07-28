"""Hook UserPromptSubmit — inyecta estado de sesión y contexto de skills activas."""

from __future__ import annotations
from higpertext.hooks.hook_tasks._rules.context_engine_rule import inject_context_pack
from higpertext.hooks.hook_tasks._rules.session_rules import (
    auto_start_session,
    reset_window_accumulator,
    inject_session_status,
    inject_skills_context,
    handle_compact_command,
)
from higpertext.hooks.hook_tasks.hook_io import read_payload
from higpertext.hooks.hook_tasks.hook_utils import get_project_root
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]  # src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from higpertext.kernel.config_paths import WORKSPACE_DIR_NAME

from higpertext.kernel.infrastructure.logger import get_logger
_log = get_logger()


def _emit_hook_context(message: str) -> None:
    print(
        json.dumps(
            {
                "continue": True,
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": message,
                },
            }
        )
    )


def _handle_slash_commands(root: Path, prompt: str) -> bool:
    if prompt == "/compact" or prompt.startswith("/compact "):
        _emit_hook_context(handle_compact_command(root).message)
        return True
    return False


def _ensure_active_session(root: Path) -> None:
    session_file = root / WORKSPACE_DIR_NAME / "state" / "session.json"
    session = json.loads(session_file.read_text(encoding="utf-8")) if session_file.exists() else {}
    if session.get("status") != "active":
        auto_start_session(root)


def _build_context(root: Path, prompt: str) -> str:
    reset_window_accumulator(root)
    parts = [inject_session_status(root).message]
    ctx = inject_skills_context(root)
    if ctx and ctx.message:
        parts.append(ctx.message)
    pack = inject_context_pack(root, prompt)
    if pack and pack.message:
        parts.append(pack.message)
    return "\n".join(parts)


def main() -> None:
    try:
        root = get_project_root()
        payload = read_payload()
        prompt = (payload.get("prompt", "") or payload.get("user_prompt", "") or "").strip().lower()

        if _handle_slash_commands(root, prompt):
            return

        _ensure_active_session(root)
        _emit_hook_context(_build_context(root, prompt))
    except Exception as exc:
        print(json.dumps({"continue": True, "error": str(exc)}))


if __name__ == "__main__":
    main()