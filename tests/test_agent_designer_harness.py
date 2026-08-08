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
