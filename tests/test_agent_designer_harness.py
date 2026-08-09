"""Arnés de contrato para el único objetivo de agent-designer."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTX = Path(os.environ.get("HTX_BIN", ROOT / ".venv" / "bin" / "htx"))
EXPECTED_CAPABILITIES = {
    "agent_designer.verify-delivery",
    "common.agent-builder",
    "common.agent-bootstrap",
    "common.agent-sync",
    "common.file-map",
    "common.grep-search",
    "common.higpertext-tester",
    "common.hook-health",
    "common.list-rules",
    "common.load-rules",
    "common.session-clean",
    "common.session-start",
    "common.smart-read",
}


def run_htx(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    assert HTX.exists(), f"No se encontró htx: {HTX}"
    return subprocess.run(
        [str(HTX), *args], cwd=cwd, text=True, capture_output=True, check=False
    )


def test_profile_has_one_creation_and_validation_scope() -> None:
    profile = json.loads(
        (ROOT / "src/config/profiles/agent_designer.json").read_text(encoding="utf-8")
    )

    assert set(profile["capabilities"]) == EXPECTED_CAPABILITIES
    assert profile["governance_access"] is False
    assert profile["session_subagents"] == []
    assert "único objetivo" in profile["system_prompt"]
    assert not list((ROOT / "src/workflows").glob("*.json"))


def test_profile_and_local_hook_are_valid() -> None:
    result = run_htx("profile", "validate", "agent_designer", "--source", str(ROOT), cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr

    hook = json.loads(
        (ROOT / "src/config/hooks/profiles/agent_designer/delivery_validation.json").read_text(
            encoding="utf-8"
        )
    )
    assert hook["event"] == "PostToolUse"
    assert (ROOT / hook["script"]).is_file()


def test_engine_scaffolds_a_new_agent_in_an_isolated_directory(tmp_path: Path) -> None:
    target = tmp_path / "support_agent"
    result = run_htx(
        "agent", "init", "--profile", "support_agent", "--target", str(target), cwd=ROOT
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "[SUCCESS] Agente listo en:" in result.stdout
    profile_path = target / "src/config/profiles/support_agent.json"
    assert profile_path.is_file()
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["name"] == "support_agent"
    assert profile["governance_access"] is False
    assert (target / "src/capabilities").is_dir()
    assert (target / "htx.py").is_file()
    assert (target / ".higpertext/config/hooks_config.json").is_file()
    assert (target / ".higpertext/state/semantic_graph.md").is_file()


def test_engine_rejects_reserved_profile_with_a_nonzero_exit_code(tmp_path: Path) -> None:
    target = tmp_path / "reserved_agent"
    result = run_htx(
        "agent", "init", "--profile", "agent_designer", "--target", str(target), cwd=ROOT
    )

    assert result.returncode != 0
    assert "perfil reservado" in result.stdout + result.stderr
    assert not target.exists()


def test_local_hook_emits_a_delivery_reminder() -> None:
    script = ROOT / "src/hooks/profiles/agent_designer/delivery_validation.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps({"tool_input": "htx task common.agent-builder"}),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Antes de entregar" in json.loads(result.stdout)["additionalContext"]


def test_delivery_verifier_writes_approved_evidence_and_unlocks_stop_hook(tmp_path: Path) -> None:
    target = tmp_path / "verified_agent"
    init = run_htx("agent", "init", "--profile", "verified_agent", "--target", str(target), cwd=ROOT)
    assert init.returncode == 0, init.stdout + init.stderr

    verifier = ROOT / "src/capabilities/agent_designer/scripts/verify_delivery.py"
    verification = subprocess.run(
        [sys.executable, str(verifier), "--target", str(target), "--profile", "verified_agent"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert verification.returncode == 0, verification.stdout + verification.stderr
    evidence = target / ".higpertext/reports/agent_delivery.json"
    assert json.loads(evidence.read_text(encoding="utf-8"))["passed"] is True

    hook = ROOT / "src/hooks/profiles/agent_designer/require_delivery_evidence.py"
    allowed = subprocess.run(
        [sys.executable, str(hook)],
        env={**os.environ, "HIGPERTEXT_DELIVERY_TARGET": str(target)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert allowed.returncode == 0, allowed.stderr


def test_stop_hook_blocks_declared_delivery_without_evidence(tmp_path: Path) -> None:
    hook = ROOT / "src/hooks/profiles/agent_designer/require_delivery_evidence.py"
    blocked = subprocess.run(
        [sys.executable, str(hook)],
        env={**os.environ, "HIGPERTEXT_DELIVERY_TARGET": str(tmp_path / "missing")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert blocked.returncode == 1
    assert "Falta evidencia" in blocked.stderr
