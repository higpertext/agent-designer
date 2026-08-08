"""Hook local: exige evidencia de validación después de operaciones de diseño."""

from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    rendered = json.dumps(payload, ensure_ascii=False)
    if "agent-builder" not in rendered and "config/profiles" not in rendered:
        return 0

    print(
        json.dumps(
            {
                "additionalContext": (
                    "Antes de entregar, valida el perfil, el estado del agente y los hooks "
                    "aplicables; ejecuta también el arnés e2e."
                )
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
