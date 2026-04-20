#!/usr/bin/env python3
"""Sugere o melhor modelo local de acordo com o hardware do usuario.

Foco dos criterios:
- updated (atualizacao)
- estabilidade
- fluidez
- raciocinio
- habilidades de codigo

O script foi pensado para uso local, sem custo por token, com Ollama.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelProfile:
    name: str
    family: str
    params_b: float
    quantization: str
    updated: float
    estabilidade: float
    fluidez: float
    raciocinio: float
    codigo: float


MODEL_CATALOG = [
    ModelProfile(
        name="qwen2.5-coder:7b",
        family="Qwen2.5 Coder",
        params_b=7,
        quantization="Q4_K_M",
        updated=8.8,
        estabilidade=8.4,
        fluidez=9.1,
        raciocinio=8.2,
        codigo=8.7,
    ),
    ModelProfile(
        name="qwen2.5-coder:14b",
        family="Qwen2.5 Coder",
        params_b=14,
        quantization="Q4_K_M",
        updated=8.8,
        estabilidade=8.7,
        fluidez=8.1,
        raciocinio=9.0,
        codigo=9.2,
    ),
    ModelProfile(
        name="qwen2.5-coder:32b",
        family="Qwen2.5 Coder",
        params_b=32,
        quantization="Q4_K_M",
        updated=8.8,
        estabilidade=8.9,
        fluidez=6.7,
        raciocinio=9.5,
        codigo=9.6,
    ),
    ModelProfile(
        name="deepseek-coder-v2:16b",
        family="DeepSeek Coder V2",
        params_b=16,
        quantization="Q4_K_M",
        updated=8.4,
        estabilidade=8.5,
        fluidez=7.8,
        raciocinio=8.8,
        codigo=9.0,
    ),
    ModelProfile(
        name="llama3.1:8b",
        family="Llama 3.1",
        params_b=8,
        quantization="Q4_K_M",
        updated=9.0,
        estabilidade=8.9,
        fluidez=9.2,
        raciocinio=8.0,
        codigo=7.3,
    ),
    ModelProfile(
        name="codellama:13b",
        family="CodeLlama",
        params_b=13,
        quantization="Q4_K_M",
        updated=6.8,
        estabilidade=7.6,
        fluidez=7.2,
        raciocinio=7.5,
        codigo=8.1,
    ),
]


def _run_command(command: list[str]) -> str | None:
    try:
        output = subprocess.check_output(command, stderr=subprocess.DEVNULL, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return output.strip()


def _detect_ram_gb() -> float:
    system = platform.system().lower()

    if system == "darwin":
        mem_bytes = _run_command(["sysctl", "-n", "hw.memsize"])
        if mem_bytes and mem_bytes.isdigit():
            return int(mem_bytes) / (1024**3)

    if system == "linux":
        mem_kb = _run_command(["grep", "MemTotal", "/proc/meminfo"])
        if mem_kb:
            parts = mem_kb.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) / (1024**2)

    return 16.0


def _detect_chip_name() -> str:
    system = platform.system().lower()
    machine = platform.machine()

    if system == "darwin":
        chip = _run_command(["sysctl", "-n", "machdep.cpu.brand_string"])
        if chip:
            return chip
        model = _run_command(["sysctl", "-n", "hw.model"])
        if model:
            return model

    return machine


def detect_hardware() -> dict[str, Any]:
    system = platform.system()
    machine = platform.machine()
    ram_gb = round(_detect_ram_gb(), 1)
    chip_name = _detect_chip_name()

    cpu_count = os.cpu_count() or 0

    is_apple_silicon = system.lower() == "darwin" and machine in {"arm64", "aarch64"}

    return {
        "system": system,
        "machine": machine,
        "chip": chip_name,
        "ram_gb": ram_gb,
        "cpu_threads": cpu_count,
        "is_apple_silicon": is_apple_silicon,
    }


def estimate_required_ram_gb(params_b: float) -> float:
    # Aproximacao para modelos quantizados em Q4 localmente.
    return max(4.0, params_b * 0.95 + 3.0)


def max_recommended_params(hardware: dict[str, Any]) -> float:
    ram = hardware["ram_gb"]
    apple = hardware["is_apple_silicon"]

    if apple:
        if ram >= 32:
            return 32
        if ram >= 24:
            return 16
        if ram >= 16:
            return 8
        return 7

    if ram >= 48:
        return 32
    if ram >= 32:
        return 16
    if ram >= 16:
        return 8
    return 7


def fit_score(hardware: dict[str, Any], model: ModelProfile) -> float:
    available = hardware["ram_gb"]
    needed = estimate_required_ram_gb(model.params_b)
    headroom = available - needed

    if headroom >= 8:
        return 10.0
    if headroom >= 4:
        return 8.5
    if headroom >= 2:
        return 7.0
    if headroom >= 0:
        return 5.5
    return 2.0


def rank_models(hardware: dict[str, Any]) -> list[dict[str, Any]]:
    cap = max_recommended_params(hardware)
    weights = {
        "updated": 0.16,
        "estabilidade": 0.24,
        "fluidez": 0.20,
        "raciocinio": 0.20,
        "codigo": 0.20,
    }

    ranked: list[dict[str, Any]] = []
    for model in MODEL_CATALOG:
        if model.params_b > cap:
            continue

        base_score = (
            model.updated * weights["updated"]
            + model.estabilidade * weights["estabilidade"]
            + model.fluidez * weights["fluidez"]
            + model.raciocinio * weights["raciocinio"]
            + model.codigo * weights["codigo"]
        )
        hardware_fit = fit_score(hardware, model)
        final_score = round(base_score * 0.85 + hardware_fit * 0.15, 3)

        ranked.append(
            {
                "model": model,
                "required_ram_gb": round(estimate_required_ram_gb(model.params_b), 1),
                "hardware_fit": round(hardware_fit, 2),
                "score": final_score,
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def format_recommendation(hardware: dict[str, Any], ranked: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("=== Hardware Detectado ===")
    lines.append(f"Sistema: {hardware['system']} ({hardware['machine']})")
    lines.append(f"Chip/CPU: {hardware['chip']}")
    lines.append(f"Memoria unificada/RAM: {hardware['ram_gb']} GB")
    lines.append("")

    if not ranked:
        lines.append("Nenhum modelo do catalogo se encaixa no hardware detectado.")
        lines.append("Sugestao: use um modelo 3B/7B quantizado no Ollama.")
        return "\n".join(lines)

    best = ranked[0]
    model: ModelProfile = best["model"]
    lines.append("=== Melhor Recomendacao ===")
    lines.append(f"Modelo: {model.name}")
    lines.append(f"Familia: {model.family}")
    lines.append(f"Memoria estimada: {best['required_ram_gb']} GB")
    lines.append(f"Score final: {best['score']}")
    lines.append("")
    lines.append("Motivo:")
    lines.append(f"- Atualizacao: {model.updated}/10")
    lines.append(f"- Estabilidade: {model.estabilidade}/10")
    lines.append(f"- Fluidez: {model.fluidez}/10")
    lines.append(f"- Raciocinio: {model.raciocinio}/10")
    lines.append(f"- Codigo: {model.codigo}/10")
    lines.append(f"- Fit no hardware: {best['hardware_fit']}/10")
    lines.append("")

    lines.append("=== Top 3 Alternativas ===")
    for index, item in enumerate(ranked[:3], start=1):
        entry_model: ModelProfile = item["model"]
        lines.append(
            f"{index}. {entry_model.name} | score={item['score']} | ram~{item['required_ram_gb']}GB"
        )

    lines.append("")
    lines.append("Comando sugerido:")
    lines.append(f"ollama pull {model.name}")
    lines.append(f"ollama run {model.name}")

    return "\n".join(lines)


def to_json_payload(hardware: dict[str, Any], ranked: list[dict[str, Any]]) -> dict[str, Any]:
    payload_ranked: list[dict[str, Any]] = []
    for item in ranked:
        model: ModelProfile = item["model"]
        payload_ranked.append(
            {
                "name": model.name,
                "family": model.family,
                "params_b": model.params_b,
                "quantization": model.quantization,
                "updated": model.updated,
                "estabilidade": model.estabilidade,
                "fluidez": model.fluidez,
                "raciocinio": model.raciocinio,
                "codigo": model.codigo,
                "required_ram_gb": item["required_ram_gb"],
                "hardware_fit": item["hardware_fit"],
                "score": item["score"],
            }
        )

    return {
        "hardware": hardware,
        "recommended": payload_ranked[0] if payload_ranked else None,
        "ranked": payload_ranked,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recomenda modelo local gratuito baseado no hardware detectado."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Retorna resultado em JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    hardware = detect_hardware()
    ranked = rank_models(hardware)

    if args.json:
        print(json.dumps(to_json_payload(hardware, ranked), indent=2, ensure_ascii=True))
        return 0

    print(format_recommendation(hardware, ranked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
