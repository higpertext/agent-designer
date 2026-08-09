"""Verifica y registra la evidencia de entrega de un agente higpertext."""
from __future__ import annotations
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REQUIRED_ARTIFACTS = ("htx.py", ".higpertext/config/environment.json", ".higpertext/config/hooks_config.json", ".higpertext/state/semantic_graph.md")
RESERVED_PROFILES = {"agent_designer", "base_agent", "base_auditor", "base_developer", "base_operator", "global"}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verifica la entrega de un agente higpertext")
    parser.add_argument("--target", required=True)
    parser.add_argument("--profile", default="")
    return parser.parse_args()

def resolve_profile(root: Path, requested: str) -> tuple[Path | None, str]:
    profiles = root / "src/config/profiles"
    if requested:
        return profiles / f"{requested}.json", requested
    candidates = [path for path in profiles.glob("*.json") if path.stem not in RESERVED_PROFILES]
    return (candidates[0], candidates[0].stem) if len(candidates) == 1 else (None, "")

def validate_profile(path: Path | None, name: str) -> tuple[bool, str]:
    if path is None:
        return False, "No se pudo inferir el perfil; usa --profile."
    if not path.is_file():
        return False, f"Perfil inexistente: {path.name}"
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False, f"JSON inválido: {path.name}"
    if profile.get("name") != name:
        return False, "El campo name no coincide con el perfil solicitado."
    if not isinstance(profile.get("governance_access"), bool):
        return False, "governance_access debe ser booleano."
    return True, "Perfil JSON válido."

def write_report(root: Path, profile: str, checks: dict[str, dict[str, str | bool]]) -> Path:
    report = root / ".higpertext/reports/agent_delivery.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"schema_version": 1, "generated_at": datetime.now(UTC).isoformat(), "target": str(root), "profile": profile, "passed": all(bool(item["passed"]) for item in checks.values()), "checks": checks}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report

def main() -> None:
    args = parse_args()
    root = Path(args.target).resolve()
    if not root.is_dir():
        print(f"[ERROR] --target no existe o no es directorio: {args.target}", file=sys.stderr)
        raise SystemExit(1)
    profile_path, profile_name = resolve_profile(root, args.profile)
    checks = {artifact: {"passed": (root / artifact).is_file(), "message": "Presente" if (root / artifact).is_file() else "Faltante"} for artifact in REQUIRED_ARTIFACTS}
    profile_ok, profile_message = validate_profile(profile_path, profile_name)
    checks["profile"] = {"passed": profile_ok, "message": profile_message}
    report = write_report(root, profile_name, checks)
    if all(bool(item["passed"]) for item in checks.values()):
        print(f"[SUCCESS] Entrega verificada. Reporte: {report}")
        return
    failed = ", ".join(name for name, item in checks.items() if not item["passed"])
    print(f"[ERROR] Entrega incompleta ({failed}). Reporte: {report}", file=sys.stderr)
    raise SystemExit(1)

if __name__ == "__main__":
    main()
