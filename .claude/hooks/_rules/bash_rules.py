"""Reglas de evaluación para comandos Bash (PreToolUse:Bash).

Cada función recibe (cmd: str, root: Path) y retorna una RuleResult.
El entrypoint hook_bash_guard.py evalúa todas en cadena.
"""

from __future__ import annotations
from higpertext.kernel.config_paths import WORKSPACE_DIR_NAME
from .governance_adapter import get_bash_blocks, get_deployment_blocks
import json
import re
import shlex
import shutil
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from higpertext.kernel.session_manager import SessionManager

RuleSeverity = Literal["continue", "context", "block"]


@dataclass
class RuleResult:
    severity: RuleSeverity
    message: str = ""
    capability: str = ""


# ── Patrones compartidos ───────────────────────────────────────────────────────

_HIGPERTEXT_DIR = WORKSPACE_DIR_NAME

_WHITELIST = re.compile(
    r"python htx\.py|\.venv[/\\](bin|Scripts)[/\\]python"
    r"|\.venv[/\\](bin|Scripts)[/\\]htx\b|\bhtx\s+(?:task|workflow)\b"
)
_WHITELIST_EXTENDED = re.compile(
    _WHITELIST.pattern + r"|git\s+checkout|git\s+merge|git\s+rebase|git\s+stash|git\s+tag"
    r"|\becho\b"
)
_GIT_ADD_ONLY = re.compile(r"\bgit\s+add\b")
_GIT_COMMIT_PRESENT = re.compile(r"\bgit\s+commit\b")


def is_whitelisted(cmd: str) -> bool:
    if "git commit" in cmd:
        return False
    if _WHITELIST_EXTENDED.search(cmd):
        return True
    if _GIT_ADD_ONLY.search(cmd) and not _GIT_COMMIT_PRESENT.search(cmd):
        return True
    return False


# ── Reglas de Commit ──────────────────────────────────────────────────────────

_GIT_COMMIT_TRIGGER = re.compile(r"\bgit\s+commit\b")


def check_git_commit_block(cmd: str, *_, **__) -> RuleResult | None:
    if _GIT_COMMIT_TRIGGER.search(cmd):
        return RuleResult(
            severity="block",
            capability="git.committer",
            message=render_box(
                "HIGPERTEXT  ·  Commit directo bloqueado",
                [
                    "  ⚠  El uso de 'git commit' nativo está prohibido.",
                    "     Debes usar la capability de committer nativa del motor",
                    "     para cumplir con la gobernanza y Conventional Commits.",
                    "  → Uso correcto:",
                    '    htx task git.committer --message "feat(scope): msg" --rationale "..."',
                ]
            ),
        )
    return None


# ── Regla 1: Bloques duros (sudo, git push) ───────────────────────────────────


def check_hard_blocks(cmd: str, root: Path) -> RuleResult | None:
    hard_blocks = get_bash_blocks(root)
    for pattern, reason in hard_blocks:
        if re.search(pattern, cmd):
            return RuleResult(
                severity="block",
                message=render_box(
                    "HIGPERTEXT  ·  Bloqueado",
                    [
                        f"  ✗  {reason}",
                    ]
                ),
            )
    return None


# ── Regla 2: Branch Protection (push a main/master) ──────────────────────────


def check_branch_protection(cmd: str, root: Path) -> RuleResult | None:
    try:
        from higpertext.kernel.infrastructure import ContractLoader

        data = ContractLoader(root).load_branching_strategy()
    except Exception:
        return None
    for rule in data.get("rules", []):
        pattern = rule.get("pattern")
        if pattern and re.search(pattern, cmd):
            severity = rule.get("severity", "block")
            reason = rule.get("reason", "Acción prohibida por branching strategy")
            return RuleResult(
                severity=severity,
                message=render_box(
                    "HIGPERTEXT  ·  Branch Protection",
                    [
                        f"  ✗  {reason}",
                        f"  Regla: {rule.get('id', 'branching')}",
                    ]
                ),
            )
    return None


# ── Regla 1c: Deployment gate (deployment_gates.json) ────────────────────────


def check_deployment_gate(cmd: str, root: Path) -> RuleResult | None:
    """Warn/block sobre comandos de deploy según deployment_gates.json."""
    for pattern, reason, severity in get_deployment_blocks(root):
        if re.search(pattern, cmd, re.IGNORECASE):
            return RuleResult(
                severity=severity,
                message=render_box(
                    "HIGPERTEXT  ·  Deployment Gate",
                    [
                        f"  ⚠  {reason}",
                    ]
                ),
            )
    return None


# ── Regla 2: Redirect ls → git.ls-files ──────────────────────────────────────

_LS_TRIGGER = re.compile(r"(^|[;&|]\s*)ls(\s|$)|\bgit\s+ls-files\b")
_LS_REASON = (
    "ls directo lista el filesystem crudo y puede incluir carpetas generadas. "
    "git.ls-files muestra archivos trackeados con resúmenes compactos y filtros."
)

_RESULTADO_LINE = "│  RESULTADO:"


def check_ls_redirect(cmd: str, root: Path) -> RuleResult | None:
    if not _LS_TRIGGER.search(cmd):
        return None
    params = _extract_ls_params(cmd)
    output = _run_higpertext("git.ls-files", params, root)
    header = render_box(
        "HIGPERTEXT  ·  Capacidad ejecutada",
        [
            f"  Comando interceptado : {cmd}",
            "  Capacidad usada      : git.ls-files",
            f"  Motivo               : {_LS_REASON}",
            "",
            "  RESULTADO:",
        ]
    )
    return RuleResult(severity="context", message=f"{header}\n{output}", capability="git.ls-files")


def _extract_ls_pattern(cmd: str) -> str:
    """Extrae el primer path de ls ignorando flags; vacío lista todo."""
    params = _extract_ls_params(cmd)
    return params.get("path", "") or params.get("pattern", "")


def _extract_ls_params(cmd: str) -> dict:
    """Traduce usos frecuentes de ls/git ls-files a parámetros gobernados."""
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return {"mode": "summary"}

    params: dict[str, str] = {"mode": "summary"}
    start = _ls_args_start(tokens)
    if start is None:
        return params

    for tok in tokens[start:]:
        if tok in ("--", ".", "./"):
            continue
        if tok.startswith("-"):
            _apply_ls_flag(tok, params)
            continue
        clean = tok.rstrip("/")
        if any(ch in clean for ch in "*?[]"):
            params["include"] = clean
        elif clean.startswith(".") and "/" not in clean:
            params["extension"] = clean.lstrip(".")
        else:
            params["path"] = clean
            if clean.startswith(("tests", "test")):
                params["preset"] = "tests"
    return params


def _ls_args_start(tokens: list[str]) -> int | None:
    if "ls" in tokens:
        return tokens.index("ls") + 1
    for i, tok in enumerate(tokens[:-1]):
        if tok == "git" and tokens[i + 1] == "ls-files":
            return i + 2
    return None


def _apply_ls_flag(flag: str, params: dict) -> None:
    if "R" in flag:
        params["mode"] = "tree"
    if "l" in flag or "h" in flag or "s" in flag:
        params["show_size"] = "true"
        if params.get("mode") == "summary":
            params["mode"] = "list"
    if "d" in flag:
        params["mode"] = "dirs"
    if "1" in flag:
        params["files_only"] = "true"


# ── Regla 3: Redirect grep/find → common.grep-search ─────────────────────────

_GREP_TRIGGER = re.compile(r"\b(grep|find)\s+")
_GREP_PATTERN = re.compile(r'grep\s+(?:-\w+\s+)*["\']?([^"\'\s]+)["\']?\s+([^|]+)')
_FIND_PATTERN = re.compile(r"find\s+(\S+)\s+([^|]+)")
_GREP_REASON = (
    "grep/find directo omite exclusiones de .venv, __pycache__ y .git, "
    "y no formatea los resultados con número de línea agrupado por archivo. "
    "common.grep-search aplica estos filtros automáticamente."
)


def check_grep_redirect(cmd: str, root: Path) -> RuleResult | None:
    if not _GREP_TRIGGER.search(cmd):
        return None

    m_grep = _GREP_PATTERN.search(cmd)
    m_find = _FIND_PATTERN.search(cmd)

    if m_grep:
        pattern, path = m_grep.group(1), m_grep.group(2).strip().split()[0]
    elif m_find:
        path, pattern = m_find.group(1), m_find.group(2).strip()
    else:
        return None

    output = _run_higpertext("common.grep-search", {"pattern": pattern, "path": path}, root)
    header = render_box(
        "HIGPERTEXT  ·  Capacidad ejecutada",
        [
            f"  Comando interceptado : {cmd}",
            "  Capacidad usada      : common.grep-search",
            f"  Motivo               : {_GREP_REASON}",
            "",
            "  RESULTADO:",
        ]
    )
    return RuleResult(
        severity="context",
        message=f"{header}\n{output}",
        capability="common.grep-search",
    )


# ── Regla 4: Redirect git diff/status/log → git.diff ─────────────────────────

_GIT_TRIGGER = re.compile(r"\bgit\s+(diff|status|log)\b")
_GIT_SKIP = re.compile(r"python htx\.py|git\s+add|git\s+commit|git\s+push")
_GIT_DETAIL = re.compile(r"\bgit\s+diff\b")
_GIT_REASON = (
    "git diff/status/log nativo produce output sin clasificar. "
    "git.diff agrupa los archivos por estado (Staged, Unstaged, Untracked) "
    "y formatea el diff en markdown legible para el agente."
)


def check_git_redirect(cmd: str, root: Path) -> RuleResult | None:
    if _GIT_SKIP.search(cmd) or not _GIT_TRIGGER.search(cmd):
        return None

    params = {"detail": "true"} if _GIT_DETAIL.search(cmd) else {}
    output = _run_higpertext("git.diff", params, root)
    header = render_box(
        "HIGPERTEXT  ·  Capacidad ejecutada",
        [
            f"  Comando interceptado : {cmd}",
            "  Capacidad usada      : git.diff",
            f"  Motivo               : {_GIT_REASON}",
            "",
            "  RESULTADO:",
        ]
    )
    return RuleResult(severity="context", message=f"{header}\n{output}", capability="git.diff")


# ── Regla 4: Redirect docs/governance → common.knowledge-asker ───────────────

_KNOWLEDGE_TRIGGER = re.compile(
    r"\bcat\s+.*(docs|governance|\.memory|AGENTS\.md|GEMINI\.md|README)|"
    r"\bhead\s+.*(docs|governance)|"
    r"\bless\s+.*(docs|governance)",
    re.IGNORECASE,
)


def check_knowledge_redirect(cmd: str, root: Path) -> RuleResult | None:
    if not root or not _KNOWLEDGE_TRIGGER.search(cmd):
        return None
    return RuleResult(
        severity="context",
        capability="common.knowledge-asker",
        message=(
            "[HIGPERTEXT] Para consultar gobernanza o documentación usa:\n"
            'htx task common.knowledge-asker --query "<pregunta>"'
        ),
    )


# ── Regla 4b: Bloquear cat/read directo de archivos grandes ────────────────────

_READ_TRIGGER = re.compile(r"\b(cat|head|less|tail)\s+([^\s|;&]+)")


def check_large_file_read_redirect(cmd: str, root: Path) -> RuleResult | None:
    if "htx.py" in cmd:
        return None
    m = _READ_TRIGGER.search(cmd)
    if not m:
        return None
    file_path_str = m.group(2).strip().strip('"').strip("'")
    p = Path(file_path_str)
    if not p.is_absolute():
        p = root / p
    if p.exists() and p.is_file():
        size_kb = p.stat().st_size / 1024
        # Si supera 100 KB lo bloqueamos / interceptamos
        if size_kb > 100:
            return RuleResult(
                severity="block",
                capability="common.code-skeletonizer",
                message=render_box(
                    "HIGPERTEXT  ·  Bloqueo de lectura masiva",
                    [
                        f"  Archivo : {m.group(2)} ({size_kb:.1f} KB)",
                        "  ⚠  La lectura directa de archivos > 100 KB está bloqueada",
                        "     para evitar la saturación de contexto de tokens.",
                        "  → Sugerencia: Usa offsets o usa la capability de",
                        "     skeletons para ver solo las firmas del archivo:",
                        f"     htx task common.code-skeletonizer --path {m.group(2)}",
                    ]
                ),
            )
    return None


# ── Regla 5: Redirect ls capabilities → common.list-rules ────────────────────

_LIST_RULES_TRIGGER = re.compile(
    r"\bls\s+.*(capabilities|rules|profiles|workflows)|"
    r"\bcat\s+.*(list.rules|capabilities.*\.json)|"
    r"\bfind\s+.*(capabilities|profiles)",
    re.IGNORECASE,
)


def check_list_rules(cmd: str, root: Path) -> RuleResult | None:
    if not _LIST_RULES_TRIGGER.search(cmd):
        return None
    output = _run_higpertext("common.list-rules", {"type": "all"}, root)
    return RuleResult(
        severity="block",
        capability="common.list-rules",
        message=(
            f"⚠️  [HIGPERTEXT HOOK] `{cmd}` interceptado"
            f" → ejecutando `common.list-rules`\n\n{output}"
        ),
    )


# ── Regla 6: Redirect escritura de reglas → common.load-rules ────────────────

_LOAD_RULES_TRIGGER = re.compile(
    r"\bcat\s+.*(session.capabilities|\.claude/rules|\.opencode/rules)|"
    r"\becho\s+.*session.capabilities|"
    r"\btee\s+.*(rules/.*\.md)|"
    r"\bwrite\s+.*session.capabilities",
    re.IGNORECASE,
)
_RULES_ARG = re.compile(r'--rules\s+["\']?([^"\']+)["\']?')


def check_load_rules(cmd: str, root: Path) -> RuleResult | None:
    if not _LOAD_RULES_TRIGGER.search(cmd):
        return None
    m = _RULES_ARG.search(cmd)
    rules = m.group(1) if m else "all"
    output = _run_higpertext("common.load-rules", {"rules": rules}, root)
    return RuleResult(
        severity="block",
        capability="common.load-rules",
        message=(
            f"⚠️  [HIGPERTEXT HOOK] `{cmd}` interceptado"
            f" → ejecutando `common.load-rules`\n\n{output}"
        ),
    )


# ── Regla 7: Intercepción de exit → cierre limpio de sesión ──────────────────


def check_exit_guard(cmd: str, root: Path) -> RuleResult | None:
    is_exit = cmd.strip() == "exit" or (
        cmd.strip().startswith("exit ") and cmd.strip()[5:].strip().isdigit()
    )
    if not is_exit:
        return None

    session = _read_json(root / WORKSPACE_DIR_NAME / "state" / "session.json")
    env = _read_json(root / WORKSPACE_DIR_NAME / "config" / "environment.json")
    sid = session.get("session_id", "—")
    profile = env.get("active_profile", "global")
    active = session.get("status") == "active"

    if active:
        _close_session(root)

    files = _pending_files(root)
    lines = []
    if files:
        lines.append(f"  ⚠  {len(files)} archivo(s) sin commitear:")
        for f in files:
            lines.append(f"     • {f}")
        lines.append("  → commiteálos antes de salir")
    else:
        lines.append("  ✓  Working tree limpio")
    lines += [
        f"  Sesión cerrada : {sid}",
        f"  Perfil cerrado : {profile}",
        "  ✓  Skills y subagentes eliminados",
    ]
    return RuleResult(severity="continue", message=render_box("HIGPERTEXT  ·  Cierre de sesión", lines))


# ── Regla 8: higpertext enforcer dinámico (desde JSONs de capabilities) ────────────


def check_higpertext_enforcer(cmd: str, root: Path) -> RuleResult | None:
    caps_roots = _find_capabilities_roots(root)
    all_json: list[Path] = []
    for caps_root in caps_roots:
        all_json.extend(sorted(caps_root.rglob("*.json")))
    for json_file in all_json:
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        intercept = data.get("bash_intercept")
        if not intercept:
            continue
        pattern = intercept.get("pattern", "")
        if not pattern or not re.search(pattern, cmd):
            continue
        if intercept.get("has_dedicated_hook", False):
            return None
        cap_id = data.get("id", "")
        reason = intercept.get("reason", intercept.get("description", ""))
        example = intercept.get("example", f"htx task {cap_id}")
        return RuleResult(
            severity="context",
            capability=cap_id,
            message=render_box(
                "HIGPERTEXT  ·  Capacidad sugerida",
                [
                    f"  Comando detectado : {cmd}",
                    f"  Capacidad         : {cap_id}",
                    f"  Motivo            : {reason}",
                    f"  Uso               : {example}",
                ]
            ),
        )
    return None


# ── Regla 9: reglas de perfil externo (desde _rules/profile_rules.json) ──────


def check_profile_rules(cmd: str, root: Path) -> RuleResult | None:
    if not root:
        return None
    rules_file = Path(__file__).parent / "profile_rules.json"
    if not rules_file.exists():
        return None
    try:
        data = json.loads(rules_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for rule in data.get("rules", []):
        pattern = rule.get("pattern", "")
        if not pattern or not re.search(pattern, cmd):
            continue
        severity = rule.get("severity", "context")
        cap_id = rule.get("capability", "")
        reason = rule.get("reason", "")
        example = rule.get("example", f"htx task {cap_id}" if cap_id else "")
        return RuleResult(
            severity=severity,
            capability=cap_id,
            message=render_box(
                "HIGPERTEXT  ·  Regla de perfil",
                [
                    f"  Comando detectado : {cmd}",
                    *([f"  Capacidad         : {cap_id}"] if cap_id else []),
                    f"  Motivo            : {reason}",
                    *([f"  Uso               : {example}"] if example else []),
                ]
            ),
        )
    return None


# ── Helpers internos ──────────────────────────────────────────────────────────


def _get_htx(root: Path) -> list[str]:
    import platform
    try:
        from higpertext.kernel.htx_resolver import get_htx_cmd

        return get_htx_cmd(root)
    except ImportError:
        venv_htx = root / ".venv" / ("Scripts" if platform.system() == "Windows" else "bin") / "htx"
        if venv_htx.exists():
            return [str(venv_htx)]
        if htx := shutil.which("htx"):
            return [htx]
        return [str(root / ".venv" / "bin" / "python"), str(root / "htx.py")]


def _run_higpertext(cap_id: str, params: dict, root: Path) -> str:
    base = _get_htx(root) + ["task", cap_id]
    args = base + [arg for k, v in params.items() for arg in (f"--{k}", str(v))]
    try:
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,  # nosec B603
            cwd=str(root),
            timeout=15,
        )
        return (r.stdout or r.stderr or "").strip()
    except Exception as exc:
        return f"[error] {exc}"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _pending_files(root: Path) -> list[str]:
    import shutil
    git_path = shutil.which("git") or "git"
    try:
        r = subprocess.run(
            [git_path, "status", "--porcelain"],  # nosec B603 B607
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=10,
        )
        return [line[3:] for line in r.stdout.strip().splitlines() if line.strip()][:5]
    except (OSError, subprocess.TimeoutExpired):
        return []


def _find_capabilities_root(root: Path) -> Path:
    candidate = root / "src" / "higpertext" / "capabilities"
    return candidate if candidate.exists() else root


def _find_capabilities_roots(root: Path) -> list[Path]:
    roots: list[Path] = []
    engine = root / "src" / "higpertext" / "capabilities"
    if engine.exists():
        roots.append(engine)
    external = root / WORKSPACE_DIR_NAME / "capabilities"
    if external.exists():
        roots.append(external)
    if not roots:
        roots.append(root)
    return roots


def _close_session(root: Path) -> None:
    try:
        SessionManager(root, root).clean_session()
    except (ImportError, AttributeError, ValueError):
        pass

    env_file = root / WORKSPACE_DIR_NAME / "config" / "environment.json"
    if env_file.exists():
        try:
            env_data = _read_json(env_file)
            env_data["active_profile"] = "git"
            env_data["active_profiles"] = ["git"]
            env_file.write_text(
                json.dumps(env_data, indent=4, ensure_ascii=False), encoding="utf-8"
            )
        except (OSError, json.JSONDecodeError):
            pass
    for assistant_dir in [".gemini", ".agents", ".claude", ".opencode"]:
        for subdir in ["skills", "subagents"]:
            d = root / assistant_dir / subdir
            if d.exists():
                try:
                    shutil.rmtree(d)
                    d.mkdir(parents=True, exist_ok=True)
                except OSError:  # nosec B110
                    pass