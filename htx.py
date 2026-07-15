import sys
import subprocess
from pathlib import Path


def main():
    target_htx = Path("/home/aomerge/Documentos/Proyects/agents/LLM-agent/htx.py")
    if not target_htx.exists():
        print(f"[!] Error: No se encontró el orquestador en {target_htx}")
        sys.exit(1)

    current_dir = Path(__file__).resolve().parent
    engine_dir = target_htx.parent
    python_exe = sys.executable
    for venv_path in [current_dir / ".venv", engine_dir / ".venv"]:
        if venv_path.exists():
            exe = (venv_path / ("Scripts/python.exe"
                   if sys.platform == "win32" else "bin/python"))
            if exe.exists():
                python_exe = str(exe)
                break

    sys.exit(subprocess.call([python_exe, str(target_htx)] + sys.argv[1:]))


if __name__ == "__main__":
    main()
