"""Hook PreCompact — preserva estado higpertext crítico antes de compresión de contexto."""

from __future__ import annotations
from higpertext.hooks.hook_tasks._rules.context_rules import check_context_pressure
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
        root = get_project_root()
        result = check_context_pressure(root)
        if result.severity == "context":
            print(
                json.dumps(
                    {
                        "continue": True,
                        "hookSpecificOutput": {
                            "hookEventName": "PreCompact",
                            "additionalContext": result.message,
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
