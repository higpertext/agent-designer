"""Hook común de seguridad para PreToolUse y PostToolUse."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from higpertext.hooks.hook_tasks.hook_io import (  # noqa: E402
    hook_main,
    read_payload,
    read_tool_command,
    emit_block,
    emit_context,
    emit_continue,
)
from higpertext.hooks.hook_tasks.hook_utils import get_project_root  # noqa: E402
from higpertext.hooks.hook_tasks._rules.security_rules import (  # noqa: E402
    evaluate_command_guard,
    evaluate_path_guard,
    mask_tool_output,
)
from higpertext.kernel.infrastructure.logger import get_logger

_log = get_logger()


def _tool_name(payload: dict) -> str:
    return str(payload.get("tool_name") or payload.get("tool") or "")


def _emit_masked_output(message: str, replacement_output: str) -> None:
    print(
        json.dumps(
            {
                "continue": True,
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": message,
                    "replacementOutput": replacement_output,
                },
            }
        )
    )


@hook_main
def main() -> None:
    payload = read_payload()
    event = payload.get("event", "PreToolUse")
    tool_name = _tool_name(payload)
    root = get_project_root()

    if event == "PreToolUse":
        if tool_name in {"Bash", "PowerShell"}:
            result = evaluate_command_guard(read_tool_command(payload), root)
        else:
            result = evaluate_path_guard(tool_name, payload.get("tool_input", {}))
        if result:
            if result.severity == "warn":
                emit_context("PreToolUse", result.message)
                return
            emit_block("PreToolUse", result.message)
            return
        emit_continue()
        return

    if event == "PostToolUse":
        result = mask_tool_output(payload.get("tool_response", {}), root)
        if result:
            _emit_masked_output(result.message, result.replacement_output)
            return
    emit_continue()


if __name__ == "__main__":
    main()
