"""Reglas de observabilidad para tool calls (PostToolUse).

Registra telemetría de tokens y actividad. Sin efectos de bloqueo.
"""

from __future__ import annotations
from higpertext.kernel.config_paths import WORKSPACE_DIR_NAME
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RuleSeverity = Literal["continue", "context", "block"]


@dataclass
class RuleResult:
    severity: RuleSeverity
    message: str = ""


# ── Regla 1: Registro de telemetría de tokens ─────────────────────────────────


def record_telemetry(payload: dict, root: Path) -> RuleResult:
    import higpertext.hooks.hook_tasks.telemetry_utils as telem

    session = _read_json(root / WORKSPACE_DIR_NAME / "state" / "session.json")
    sid = session.get("session_id", "unknown")

    tool_name = payload.get("tool_name", "unknown")
    tool_input = payload.get("tool_input", {})
    tool_response = payload.get("tool_response", {})

    input_str = json.dumps(tool_input, ensure_ascii=False)
    output_str = json.dumps(tool_response, ensure_ascii=False)

    cmd = (
        (tool_input.get("command") or tool_input.get("CommandLine") or "")
        if isinstance(tool_input, dict)
        else ""
    )
    is_higpertext_call = ("htx" in cmd or "htx.py" in cmd) and "task" in cmd

    telem.tool_call(
        root,
        session_id=sid,
        tool_name=tool_name,
        input_chars=len(input_str),
        output_chars=len(output_str),
        is_higpertext_call=is_higpertext_call,
    )

    op_type, target, scope = _extract_activity(tool_name, tool_input, is_higpertext_call)
    if op_type:
        telem.activity(
            root,
            session_id=sid,
            tool=tool_name,
            op_type=op_type,
            target=target,
            scope=scope,
            higpertext_related=is_higpertext_call,
        )

    return RuleResult(severity="continue")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _rel(path_str: str) -> str:
    try:
        return str(Path(path_str).relative_to(os.getcwd()))
    except ValueError:
        return Path(path_str).name


def _extract_activity(
    tool: str, tool_input: dict, is_higpertext_call: bool
) -> tuple[str, str, str]:
    if not isinstance(tool_input, dict):
        return "", "", ""

    if tool == "Edit":
        rel = _rel(tool_input.get("file_path", ""))
        return "code-change", rel, str(Path(rel).parent)

    if tool == "Write":
        rel = _rel(tool_input.get("file_path", ""))
        return "new-file", rel, str(Path(rel).parent)

    if tool == "Read":
        rel = _rel(tool_input.get("file_path", ""))
        return "file-read", rel, str(Path(rel).parent)

    if tool in ("Bash", "PowerShell"):
        cmd = (tool_input.get("command") or tool_input.get("CommandLine") or "")[:100]
        if is_higpertext_call:
            parts = cmd.split()
            try:
                idx = parts.index("task")
                cap = parts[idx + 1] if idx + 1 < len(parts) else cmd
            except ValueError:
                cap = cmd
            return "higpertext-task", cap, "higpertext"
        return "bash-cmd", cmd, "bash"

    if tool == "Skill":
        skill = tool_input.get("skill", tool_input.get("name", "unknown"))
        return "skill-invoked", skill, "skill"

    return "", "", ""


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}