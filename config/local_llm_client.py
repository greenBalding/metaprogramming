#!/usr/bin/env python3
"""Cliente local para LLM com fallback deterministico.

Este modulo usa uma configuracao local do projeto para tentar rodar um modelo via
Ollama em um caso pequeno e controlado. Se o runtime nao estiver disponivel ou a
resposta nao puder ser validada, cai para uma recomendacao deterministica.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_local_llm_config(repo_root: Path) -> dict[str, Any] | None:
    config_path = repo_root / "config" / "local_llm.json"
    if not config_path.exists():
        return None
    return json.loads(config_path.read_text(encoding="utf-8"))


def _render_fallback_advice(
    *,
    goal: str,
    domain: str,
    project_name: str,
    architecture: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    primary_module = spec.get("modules", ["core_domain"])[0]
    return {
        "source": "deterministic-fallback",
        "model": None,
        "summary": (
            f"Para '{project_name}', siga com a arquitetura {architecture.get('style', 'desconhecida')} "
            f"e inicie pelo modulo '{primary_module}'."
        ),
        "risk_level": "low",
        "next_step": f"Implementar e validar o primeiro modulo '{primary_module}' com testes locais.",
        "reason": (
            "Fallback deterministico usado porque o runtime local nao foi encontrado, "
            "a resposta nao era JSON valida ou a chamada falhou."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_snapshot": {
            "goal": goal,
            "domain": domain,
            "project_name": project_name,
        },
    }


def _build_prompt(
    *,
    goal: str,
    domain: str,
    project_name: str,
    architecture: dict[str, Any],
    spec: dict[str, Any],
    decision_log: dict[str, Any],
) -> str:
    payload = {
        "goal": goal,
        "domain": domain,
        "project_name": project_name,
        "architecture": {
            "style": architecture.get("style"),
            "backend": architecture.get("backend"),
            "database": architecture.get("database"),
            "deployment": architecture.get("deployment"),
        },
        "modules": spec.get("modules", []),
        "entities": spec.get("entities", []),
        "decision_log_entries": decision_log.get("entries", [])[:5],
    }
    return (
        "Voce e um assistente local, especializado em codigo e arquitetura. "
        "Retorne apenas JSON valido, sem markdown, com as chaves: summary, risk_level, next_step, reason. "
        "Use linguagem objetiva e considere a arquitetura, os modulos e o contexto abaixo.\n\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=True)}"
    )


def _parse_json_response(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = candidate.replace("json\n", "", 1)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    required_keys = {"summary", "risk_level", "next_step", "reason"}
    if not required_keys.issubset(parsed.keys()):
        return None
    return parsed


def _run_ollama_prompt(model: str, prompt: str, timeout_seconds: int = 45) -> str | None:
    if shutil.which("ollama") is None:
        return None

    try:
        completed = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None

    stdout = completed.stdout.strip()
    return stdout or None


def generate_local_llm_advice(
    repo_root: Path,
    *,
    goal: str,
    domain: str,
    project_name: str,
    architecture: dict[str, Any],
    spec: dict[str, Any],
    decision_log: dict[str, Any],
) -> dict[str, Any]:
    config = load_local_llm_config(repo_root)
    if not config or config.get("provider") != "ollama":
        return _render_fallback_advice(
            goal=goal,
            domain=domain,
            project_name=project_name,
            architecture=architecture,
            spec=spec,
        )

    model = config.get("model")
    if not isinstance(model, str) or not model.strip():
        return _render_fallback_advice(
            goal=goal,
            domain=domain,
            project_name=project_name,
            architecture=architecture,
            spec=spec,
        )

    prompt = _build_prompt(
        goal=goal,
        domain=domain,
        project_name=project_name,
        architecture=architecture,
        spec=spec,
        decision_log=decision_log,
    )
    response = _run_ollama_prompt(model.strip(), prompt)
    if response is None:
        return _render_fallback_advice(
            goal=goal,
            domain=domain,
            project_name=project_name,
            architecture=architecture,
            spec=spec,
        )

    parsed = _parse_json_response(response)
    if parsed is None:
        return _render_fallback_advice(
            goal=goal,
            domain=domain,
            project_name=project_name,
            architecture=architecture,
            spec=spec,
        )

    return {
        "source": "ollama",
        "model": model,
        "summary": str(parsed["summary"]),
        "risk_level": str(parsed["risk_level"]),
        "next_step": str(parsed["next_step"]),
        "reason": str(parsed["reason"]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_snapshot": {
            "goal": goal,
            "domain": domain,
            "project_name": project_name,
        },
    }


def render_local_llm_advice(advice: dict[str, Any]) -> str:
    lines = ["# Local LLM Advice", ""]
    lines.append(f"Source: {advice.get('source', 'unknown')}")
    if advice.get("model"):
        lines.append(f"Model: {advice['model']}")
    lines.append(f"Risk level: {advice.get('risk_level', 'unknown')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(str(advice.get("summary", "-")))
    lines.append("")
    lines.append("## Next Step")
    lines.append("")
    lines.append(str(advice.get("next_step", "-")))
    lines.append("")
    lines.append("## Reason")
    lines.append("")
    lines.append(str(advice.get("reason", "-")))
    lines.append("")
    lines.append("## Generated At")
    lines.append("")
    lines.append(str(advice.get("generated_at", "-")))
    return "\n".join(lines)
