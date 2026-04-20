"""Web backend for the metaprogramming platform chat interface."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add parent directory to path so we can import the factory module.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from autonomous_factory import factory  # noqa: E402

app = FastAPI(title="Metaprogramming Platform")
web_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=web_dir), name="static")

SCHEMA_PATH = REPO_ROOT / "config" / "chat_constraints.json"

conversations: dict[str, dict[str, Any]] = {}


class ChatRequest(BaseModel):
    message: str
    conversationId: str
    projectName: Optional[str] = None
    projectData: Optional[dict[str, Any]] = None


class ChatResponse(BaseModel):
    response: str
    projectName: Optional[str] = None
    projectData: Optional[dict[str, Any]] = None
    projectGenerated: bool = False
    projectPath: Optional[str] = None
    systemMessage: Optional[str] = None
    error: Optional[str] = None


def load_constraint_schema() -> list[dict[str, Any]]:
    payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("chat_constraints.json must be a list")
    return payload


def field_applies_to_domain(field: dict[str, Any], domain: str) -> bool:
    domains = field.get("domains")
    if domains is None:
        return True
    if not isinstance(domains, list):
        return True
    return domain in domains


def pending_required_fields(
    constraints: dict[str, Any],
    domain: str,
    schema: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for field in schema:
        if not field_applies_to_domain(field, domain):
            continue
        if not field.get("required", False):
            continue
        key = field.get("key")
        if not isinstance(key, str):
            continue
        if key not in constraints:
            pending.append(field)
    return pending


def format_question(field: dict[str, Any]) -> str:
    question = field.get("question")
    if isinstance(question, str) and question.strip():
        if field.get("type") == "enum" and isinstance(field.get("options"), list):
            options = ", ".join(str(opt) for opt in field["options"])
            return f"{question.strip()} ({options})"
        return question.strip()

    key = field.get("key", "constraint")
    return f"Informe valor para: {key}"


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned) or "autonomous-project"


def parse_int_from_message(message: str, aliases: list[str], contextual: bool) -> Optional[int]:
    text = message.strip().lower()
    if contextual and re.fullmatch(r"\d+", text):
        return int(text)

    alias_pattern = "|".join(re.escape(alias) for alias in aliases) if aliases else ""
    if alias_pattern:
        match = re.search(rf"(\d+)\s*(?:{alias_pattern})", text, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None


def parse_enum_from_message(message: str, options: list[str], contextual: bool) -> Optional[str]:
    text = message.strip().lower()
    if contextual and text in options:
        return text

    for option in options:
        if re.search(rf"\b{re.escape(option)}\b", text):
            return option
    return None


def parse_csv_from_message(message: str) -> Optional[list[str]]:
    if "," not in message:
        return None
    items = [part.strip() for part in message.split(",") if part.strip()]
    return items or None


def parse_constraints_from_message(
    message: str,
    constraints: dict[str, Any],
    domain: str,
    schema: list[dict[str, Any]],
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    pending = pending_required_fields(constraints, domain, schema)
    contextual_key = pending[0]["key"] if pending else None

    for field in schema:
        if not field_applies_to_domain(field, domain):
            continue

        key = field.get("key")
        if not isinstance(key, str):
            continue
        if key in constraints or key in updates:
            continue

        field_type = str(field.get("type", "string")).lower()
        contextual = key == contextual_key

        if field_type == "int":
            aliases = field.get("aliases") if isinstance(field.get("aliases"), list) else []
            value = parse_int_from_message(message, [str(a) for a in aliases], contextual)
            if value is not None:
                updates[key] = value

        elif field_type == "enum":
            options_raw = field.get("options") if isinstance(field.get("options"), list) else []
            options = [str(opt).lower() for opt in options_raw]
            value = parse_enum_from_message(message, options, contextual)
            if value is not None:
                updates[key] = value

        elif field_type == "csv":
            value = parse_csv_from_message(message)
            if value is not None:
                updates[key] = value

        elif message.strip():
            updates[key] = message.strip()

    return updates


def next_missing_question(
    constraints: dict[str, Any],
    domain: str,
    schema: list[dict[str, Any]],
) -> Optional[str]:
    pending = pending_required_fields(constraints, domain, schema)
    if not pending:
        return None
    return format_question(pending[0])


def get_or_create_conversation(conv_id: str) -> dict[str, Any]:
    if conv_id not in conversations:
        conversations[conv_id] = {
            "state": "initial",
            "goal": "",
            "constraints": {},
            "project_name": "",
            "domain": "",
            "architecture": "",
        }
    return conversations[conv_id]


def build_project(goal: str, constraints: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    domain = factory.infer_domain(goal)
    project_name = slugify(goal)

    decision_entries: list[dict[str, Any]] = []
    factory.append_decision(decision_entries, key="goal", value=goal, source="input")
    factory.append_decision(
        decision_entries,
        key="domain",
        value=domain,
        source="inference",
        note="Inferred from goal keywords.",
    )
    factory.append_decision(
        decision_entries,
        key="project_name",
        value=project_name,
        source="derived",
    )
    for key, value in sorted(constraints.items()):
        factory.append_decision(decision_entries, key=key, value=value, source="chat")

    spec = factory.build_spec(goal, domain, constraints)
    architecture = factory.choose_architecture(constraints, domain)
    backlog = factory.build_backlog(spec, architecture)

    decision_log = factory.build_decision_log(
        goal,
        domain,
        project_name,
        constraints,
        decision_entries,
    )
    decision_hash = factory.compute_decision_log_hash(decision_log)
    decision_log["integrity"] = {
        "algorithm": "sha256",
        "hash": decision_hash,
        "artifact": "planning/decision-log.json",
    }

    output_root = Path("generated").resolve()
    destination = output_root / project_name
    destination.mkdir(parents=True, exist_ok=True)

    execution_state = factory.build_execution_state(spec, architecture, backlog)

    factory.write_project(
        root=destination,
        project_name=project_name,
        spec=spec,
        architecture=architecture,
        backlog=backlog,
        decision_log=decision_log,
        execution_state=execution_state,
    )

    return project_name, {
        "domain": domain,
        "architecture": architecture.get("style", "unknown"),
        "projectPath": str(destination),
        "entities": spec.get("entities", []),
        "modules": spec.get("modules", []),
    }


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(web_dir / "index.html")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    conv = get_or_create_conversation(request.conversationId)
    message = request.message.strip()

    try:
        schema = load_constraint_schema()

        if conv["state"] == "initial":
            conv["goal"] = message
            conv["domain"] = factory.infer_domain(message)
            conv["constraints"] = parse_constraints_from_message(
                message,
                conv["constraints"],
                conv["domain"],
                schema,
            )
            next_q = next_missing_question(conv["constraints"], conv["domain"], schema)
            if next_q:
                conv["state"] = "collecting_constraints"
                return ChatResponse(
                    response=(
                        f"Entendi. Objetivo: {conv['goal']}\n\n"
                        f"Pergunta rapida: {next_q}"
                    ),
                    projectName=None,
                    projectData=conv["constraints"],
                )

            conv["state"] = "generating"

        if conv["state"] == "collecting_constraints":
            parsed = parse_constraints_from_message(
                message,
                conv["constraints"],
                conv["domain"],
                schema,
            )
            conv["constraints"].update(parsed)
            next_q = next_missing_question(conv["constraints"], conv["domain"], schema)
            if next_q:
                return ChatResponse(
                    response=f"Perfeito. Agora: {next_q}",
                    projectName=None,
                    projectData=conv["constraints"],
                )
            conv["state"] = "generating"

        if conv["state"] == "generating":
            project_name, details = build_project(conv["goal"], conv["constraints"])
            conv["state"] = "complete"
            conv["project_name"] = project_name
            conv["domain"] = details["domain"]
            conv["architecture"] = details["architecture"]

            response = (
                "Projeto gerado com sucesso.\n\n"
                f"Projeto: {project_name}\n"
                f"Dominio: {details['domain']}\n"
                f"Arquitetura: {details['architecture']}\n"
                f"Pasta: {details['projectPath']}\n\n"
                "Proximo passo: abra planning/execution-plan.md no projeto gerado."
            )
            return ChatResponse(
                response=response,
                projectName=project_name,
                projectData=details,
                projectGenerated=True,
                projectPath=details["projectPath"],
                systemMessage="Projeto pronto.",
            )

        return ChatResponse(
            response=(
                f"Seu projeto {conv.get('project_name', '')} ja foi criado. "
                "Se quiser, descreva um novo projeto para iniciar outra geracao."
            ),
            projectName=conv.get("project_name") or None,
            projectData={
                "domain": conv.get("domain", ""),
                "architecture": conv.get("architecture", ""),
            },
        )

    except Exception as exc:
        return ChatResponse(
            response="",
            error=f"Falha ao processar requisicao: {exc}",
            projectName=None,
            projectData=None,
            projectGenerated=False,
        )


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "metaprogramming-web"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
