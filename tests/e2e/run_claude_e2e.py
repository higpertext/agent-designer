"""Ejecutor auditable de evaluaciones conversacionales mediante ``claude -p``."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta casos E2E de Claude para agent-designer")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("claude_cases.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--timeout", type=int, default=180)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if shutil.which(args.claude_bin) is None:
        raise SystemExit(f"[ERROR] No se encontró el ejecutable: {args.claude_bin}")
    if not args.workspace.is_dir():
        raise SystemExit(f"[ERROR] Workspace inexistente: {args.workspace}")

    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    results = []
    for case in cases:
        run = subprocess.run(
            [args.claude_bin, "-p", case["prompt"]],
            cwd=args.workspace,
            text=True,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
        response = run.stdout.strip()
        lowered = response.casefold()
        required = [term.casefold() for term in case.get("response_contains_any", [])]
        semantic_ok = not required or any(term in lowered for term in required)
        results.append(
            {
                "id": case["id"],
                "prompt": case["prompt"],
                "exit_code": run.returncode,
                "response": response,
                "stderr": run.stderr.strip(),
                "passed": run.returncode == 0 and semantic_ok,
                "required_response_terms": required,
            }
        )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "workspace": str(args.workspace),
        "cases": results,
        "passed": all(case["passed"] for case in results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[{'SUCCESS' if report['passed'] else 'ERROR'}] Reporte: {args.output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
