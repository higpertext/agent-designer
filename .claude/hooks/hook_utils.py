"""Utilidades compartidas para hook tasks de higpertext."""

from __future__ import annotations
import sys
from pathlib import Path

# Add src to sys.path so we can import from higpertext

import json
import platform
import shutil
# Helpers ejecutan htx con shell=False.
import subprocess  # nosec B404
from datetime import datetime, timezone

sys_path_src = Path(__file__).resolve().parents[3]
if str(sys_path_src) not in sys.path:
    sys.path.insert(0, str(sys_path_src))
from higpertext.kernel.config_paths import WORKSPACE_DIR_NAME
HIGPERTEXT_DIR = WORKSPACE_DIR_NAME



def get_project_root() -> Path:
    """Resuelve la raíz del proyecto desde environment.json.

    Cuando un hook task se despliega en .<assistant>/hooks/, el archivo
    environment.json se encuentra en ../../.higpertext/environment.json relativo
    al script. Siempre hay un htx.py launcher en esa raíz.
    """
    # Busca environment.json en dos ubicaciones candidatas:
    # 1. Relativo al script (cuando el hook está desplegado en .<assistant>/hooks/)
    # 2. Relativo al CWD del proceso (cuando se ejecuta desde la raíz del proyecto)
    candidates = [
        Path(__file__).resolve().parent
        / ".."
        / ".."
        / HIGPERTEXT_DIR
        / "config"
        / "environment.json",
        Path.cwd() / HIGPERTEXT_DIR / "config" / "environment.json",
    ]
    for env_path in candidates:
        env_path = env_path.resolve()
        if env_path.exists():
            try:
                data = json.loads(env_path.read_text(encoding="utf-8"))
                root = data.get("system_environment", {}).get("project_root")
                if root:
                    return Path(root)
            except (OSError, json.JSONDecodeError):  # nosec B110
                pass
    # Fallback: CWD si contiene htx.py (indica que somos la raíz del proyecto)
    cwd = Path.cwd()
    if (cwd / "htx.py").exists():
        return cwd
    return Path(__file__).resolve().parents[1]


def get_htx() -> str:
    """Retorna el primer elemento del comando htx resuelto via htx_resolver."""
    root = get_project_root()
    try:
        from higpertext.kernel.htx_resolver import get_htx_cmd

        cmd = get_htx_cmd(root)
        return cmd[0]
    except ImportError:
        venv_htx = root / ".venv" / ("Scripts" if platform.system() == "Windows" else "bin") / "htx"
        if venv_htx.exists():
            return str(venv_htx)
        if htx := shutil.which("htx"):
            return htx
        return str(root / ".venv" / "bin" / "python")


def _htx_args(capability: str, params: dict) -> list[str]:
    htx = get_htx()
    base = (
        [htx, "task", capability]
        if not htx.endswith("python")
        else [htx, "htx.py", "task", capability]
    )
    return base + [arg for k, v in params.items() for arg in (f"--{k}", str(v))]


def hook_log_path(root: Path | None = None) -> Path:
    """Retorna la ruta del log estructurado de hooks."""
    base = root or get_project_root()
    return base / HIGPERTEXT_DIR / "logs" / "hooks.jsonl"


def log_hook_event(event: dict, root: Path | None = None) -> None:
    """Registra un evento JSONL de hook sin interrumpir la ejecución."""
    try:
        path = hook_log_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:  # nosec B110
        pass


def log_hook_error(hook_id: str, message: str, root: Path | None = None, **extra: object) -> None:
    """Registra errores no bloqueantes de hooks."""
    log_hook_event(
        {
            "severity": "error",
            "hook_id": hook_id,
            "message": message[:1000],
            **extra,
        },
        root=root,
    )


def run_higpertext_task(capability: str, params: dict) -> str:
    """Ejecuta una capability higpertext y retorna su output combinado."""
    root = get_project_root()
    args = _htx_args(capability, params)
    try:
        result = subprocess.run(args, capture_output=True, text=True, cwd=str(root), timeout=30)
    except subprocess.TimeoutExpired as exc:
        log_hook_error(
            "run_higpertext_task",
            f"Timeout ejecutando capability {capability}",
            root=root,
            capability=capability,
            timeout=exc.timeout,
        )
        return str(exc)
    if result.returncode != 0:
        log_hook_error(
            "run_higpertext_task",
            f"Capability {capability} terminó con código {result.returncode}",
            root=root,
            capability=capability,
            returncode=result.returncode,
        )
    return (result.stdout or "") + (result.stderr or "")
