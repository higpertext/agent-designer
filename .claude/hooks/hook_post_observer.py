"""Hook PostToolUse — registra telemetría de tokens y actividad por tool call."""

from __future__ import annotations
from higpertext.hooks.hook_tasks._rules.context_rules import (
    check_large_output,
    check_window_pressure,
)
from higpertext.hooks.hook_tasks._rules.telemetry_rules import record_telemetry
from higpertext.hooks.hook_tasks.hook_utils import get_project_root
import json
import sys
from pathlib import Path

from higpertext.kernel.infrastructure.logger import get_logger
_log = get_logger()

_SRC = Path(__file__).resolve().parents[3]  # src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


sys.path.insert(0, str(Path(__file__).parent))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        root = get_project_root()
        record_telemetry(payload, root)

        large = check_large_output(payload)
        pressure = check_window_pressure(payload, root)

        extra_parts = [r.message for r in (large, pressure) if r is not None]
        if extra_parts:
            print(
                json.dumps(
                    {
                        "continue": True,
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUse",
                            "additionalContext": "\n".join(extra_parts),
                        },
                    }
                )
            )
        else:
            print(json.dumps({"continue": True}))
    except Exception as exc:
        print(json.dumps({"continue": True, "error": str(exc)}))


if __name__ == "__main__":
    main()
