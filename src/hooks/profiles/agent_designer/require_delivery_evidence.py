"""Hook Stop: exige evidencia solo cuando hay un destino de entrega declarado."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

def main() -> int:
    target = os.environ.get("HIGPERTEXT_DELIVERY_TARGET")
    if not target:
        return 0
    try:
        data = json.loads((Path(target) / ".higpertext/reports/agent_delivery.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("[ERROR] Falta evidencia de entrega; ejecuta agent_designer.verify-delivery.", file=sys.stderr)
        return 1
    if data.get("passed") is True:
        return 0
    print("[ERROR] La evidencia de entrega no aprobó; corrige los checks antes de concluir.", file=sys.stderr)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
