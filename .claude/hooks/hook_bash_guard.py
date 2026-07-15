"""Hook PreToolUse:Bash — evalúa todas las reglas de comandos Bash en cadena."""

from __future__ import annotations
from higpertext.hooks.hook_tasks._rules.bash_rules import (
    RuleResult,
    is_whitelisted,
    check_git_commit_block,
    check_hard_blocks,
    check_branch_protection,
    check_deployment_gate,
    check_ls_redirect,
    check_grep_redirect,
    check_git_redirect,
    check_knowledge_redirect,
    check_large_file_read_redirect,
    check_list_rules,
    check_load_rules,
    check_exit_guard,
    check_higpertext_enforcer,
    check_profile_rules,
)
import higpertext.hooks.hook_tasks.telemetry_utils as telem
from higpertext.hooks.hook_tasks.hook_utils import get_project_root
from higpertext.hooks.hook_tasks.hook_io import (
    hook_main,
    read_payload,
    read_tool_command,
    emit_continue,
    emit_context,
    emit_block,
)
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]  # src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from higpertext.kernel.config_paths import WORKSPACE_DIR_NAME


sys.path.insert(0, str(Path(__file__).parent))

_RULES = [
    check_git_commit_block,
    check_hard_blocks,
    check_branch_protection,
    check_deployment_gate,
    check_ls_redirect,
    check_grep_redirect,
    check_git_redirect,
    check_knowledge_redirect,
    check_large_file_read_redirect,
    check_list_rules,
    check_load_rules,
    check_exit_guard,
    check_higpertext_enforcer,
    check_profile_rules,
]


@hook_main
def main() -> None:
    payload = read_payload()
    cmd = read_tool_command(payload)

    if is_whitelisted(cmd):
        emit_continue()
        return

    root = get_project_root()
    session_data = {}
    try:
        import json

        session_data = json.loads(
            (root / WORKSPACE_DIR_NAME / "state" / "session.json").read_text(encoding="utf-8")
        )
    except Exception:  # nosec B110
        pass
    sid = session_data.get("session_id", "unknown")

    for rule_fn in _RULES:
        result: RuleResult | None = rule_fn(cmd, root)
        if result is None:
            continue

        if result.severity == "block":
            telem.hook_intercept(root, sid, result.capability or "BLOCKED", cmd)
            emit_block("PreToolUse", result.message)
            return

        if result.severity == "context":
            telem.hook_intercept(root, sid, result.capability or "context", cmd)
            emit_context("PreToolUse", result.message)
            return

    emit_continue()


if __name__ == "__main__":
    main()