#!/usr/bin/env python3
"""Autonomous software factory MVP.

This script converts a high-level goal (for example, "build a SGA") into:
1) A structured requirements specification
2) An architecture decision record
3) A phased execution plan/backlog
4) A starter project scaffold

The implementation is intentionally deterministic and lightweight so it can be
used as a practical first step toward a larger agentic system.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SGA_ENTITIES = [
    "Student",
    "Professor",
    "Course",
    "Enrollment",
    "Grade",
    "Attendance",
    "AcademicPeriod",
]

DEFAULT_SGA_MODULES = [
    "authentication",
    "student_management",
    "course_catalog",
    "enrollment",
    "grading",
    "attendance",
    "reports",
]

DEFAULT_SGA_WORKFLOWS = [
    "Student enrollment lifecycle",
    "Course assignment by professor",
    "Grade publishing and transcript generation",
    "Attendance tracking and alerts",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic autonomous-build blueprint and scaffold."
    )
    parser.add_argument(
        "--goal",
        required=True,
        help="High-level command (example: 'build a SGA').",
    )
    parser.add_argument(
        "--project-name",
        help="Optional project slug. If omitted, it is derived from goal.",
    )
    parser.add_argument(
        "--output",
        default="generated",
        help="Output root folder (default: generated).",
    )
    parser.add_argument(
        "--constraint",
        action="append",
        default=[],
        help=(
            "Constraint key=value pair. Repeat this flag for multiple constraints. "
            "Examples: --constraint users=15000 --constraint cloud=aws"
        ),
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Ask guided questions to fill missing constraints before generation.",
    )
    parser.add_argument(
        "--dry-run-execution",
        action="store_true",
        help="Generate a phase-by-phase execution report without performing destructive actions.",
    )
    parser.add_argument(
        "--advance-phase",
        action="store_true",
        help="Advance the execution state by one step and persist the updated state.",
    )
    parser.add_argument(
        "--state-file",
        help="Optional execution state file path. Defaults to execution/state.json inside the project.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite if destination already exists.",
    )
    return parser.parse_args()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "autonomous-project"


def infer_domain(goal: str) -> str:
    normalized = goal.lower()
    sga_keywords = [
        "sga",
        "academic",
        "gerenciamento academico",
        "sistema academico",
        "school",
        "university",
    ]
    if any(keyword in normalized for keyword in sga_keywords):
        return "academic_management"
    return "generic_web_application"


def parse_constraints(raw_constraints: list[str]) -> dict[str, Any]:
    constraints: dict[str, Any] = {}
    for item in raw_constraints:
        if "=" not in item:
            raise ValueError(
                f"Invalid constraint '{item}'. Expected key=value format."
            )
        key, value = item.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key:
            raise ValueError(f"Invalid constraint '{item}'. Empty key is not allowed.")
        constraints[key] = coerce_constraint_value(key, value)
    return constraints


def read_input(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default or ""
    if value:
        return value
    return default or ""


def read_int(prompt: str, default: int) -> int:
    while True:
        value = read_input(prompt, str(default))
        try:
            return int(value)
        except ValueError:
            print("Please enter a valid integer value.", file=sys.stderr)


def read_choice(prompt: str, options: list[str], default: str) -> str:
    normalized = [option.lower() for option in options]
    while True:
        value = read_input(f"{prompt} ({'/'.join(options)})", default).lower()
        if value in normalized:
            return value
        print(f"Please choose one of: {', '.join(options)}", file=sys.stderr)


def read_csv(prompt: str, default: list[str] | None = None) -> list[str]:
    default_text = ",".join(default or [])
    value = read_input(prompt, default_text)
    return [item.strip() for item in value.split(",") if item.strip()]


def prompt_project_name_interactively(project_name: str) -> str:
    suggested = project_name or "autonomous-project"
    chosen_name = read_input("Project name", suggested)
    return slugify(chosen_name)


def collect_constraints_interactively(
    constraints: dict[str, Any], domain: str
) -> dict[str, Any]:
    interactive_constraints = dict(constraints)
    print("Interactive mode enabled. Press Enter to accept defaults.")

    if "users" not in interactive_constraints and "max_users" not in interactive_constraints:
        interactive_constraints["users"] = read_int("Estimated users", 3000)

    if "cloud" not in interactive_constraints:
        interactive_constraints["cloud"] = read_input("Cloud provider", "agnostic")

    if "budget" not in interactive_constraints:
        interactive_constraints["budget"] = read_choice(
            "Budget profile", ["low", "medium", "high"], "medium"
        )

    if "compliance" not in interactive_constraints and "regulations" not in interactive_constraints:
        default_compliance = ["LGPD"] if domain == "academic_management" else []
        compliance = read_csv(
            "Compliance regulations (comma separated)", default_compliance
        )
        if compliance:
            interactive_constraints["compliance"] = compliance

    if domain == "academic_management" and "delivery" not in interactive_constraints:
        interactive_constraints["delivery"] = read_choice(
            "Primary delivery channel", ["web", "mobile", "hybrid"], "web"
        )

    return interactive_constraints


def coerce_constraint_value(key: str, value: str) -> Any:
    if key in {"users", "max_users"}:
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"Constraint '{key}' expects an integer value.") from exc
    if key in {"compliance", "regulations"}:
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


def choose_architecture(constraints: dict[str, Any], domain: str) -> dict[str, Any]:
    users = int(constraints.get("users", constraints.get("max_users", 3000)))
    cloud = str(constraints.get("cloud", "agnostic"))
    budget = str(constraints.get("budget", "medium")).lower()

    if users >= 50000:
        style = "microservices + event-driven"
        rationale = [
            "High user volume favors independent scaling and fault isolation.",
            "Event-driven workflows reduce coupling between core modules.",
        ]
    elif users >= 10000:
        style = "modular monolith + async workers"
        rationale = [
            "Large but manageable volume balances simplicity and scalability.",
            "Modules can be extracted into services later with low migration risk.",
        ]
    else:
        style = "modular monolith"
        rationale = [
            "Fastest path to value for small and medium institutions.",
            "Operational complexity stays low while keeping clear module boundaries.",
        ]

    database = "PostgreSQL"
    if budget == "low":
        deployment = "single region, container-based deployment"
    else:
        deployment = "multi-environment deployment with staging and production"

    if domain == "academic_management":
        backend = "Python API with role-based access control"
    else:
        backend = "Python API"

    return {
        "style": style,
        "backend": backend,
        "frontend": "Web dashboard",
        "database": database,
        "deployment": deployment,
        "cloud": cloud,
        "rationale": rationale,
    }


def build_spec(goal: str, domain: str, constraints: dict[str, Any]) -> dict[str, Any]:
    if domain == "academic_management":
        entities = DEFAULT_SGA_ENTITIES
        modules = DEFAULT_SGA_MODULES
        workflows = DEFAULT_SGA_WORKFLOWS
        assumptions = [
            "Primary interface is web.",
            "Role model includes admin, professor, and student.",
            "System must support auditability for academic records.",
        ]
        non_functional = {
            "availability": "99.9%",
            "api_p95_latency": "< 300ms",
            "security": [
                "RBAC",
                "input validation",
                "audit logs",
            ],
        }
    else:
        entities = ["User", "Resource", "AuditEvent"]
        modules = ["authentication", "core_domain", "reporting"]
        workflows = ["Create and manage resources", "Track user actions"]
        assumptions = [
            "Web-based delivery.",
            "Relational persistence.",
        ]
        non_functional = {
            "availability": "99.5%",
            "api_p95_latency": "< 400ms",
            "security": ["RBAC", "audit logs"],
        }

    governance = {
        "approval_gates": [
            "Production deployment",
            "Destructive database migrations",
            "Permission model changes",
        ],
        "mandatory_checks": [
            "Unit tests",
            "Static analysis",
            "Dependency vulnerability scan",
        ],
    }

    return {
        "goal": goal,
        "domain": domain,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "constraints": constraints,
        "assumptions": assumptions,
        "entities": entities,
        "modules": modules,
        "workflows": workflows,
        "non_functional": non_functional,
        "governance": governance,
    }


def build_backlog(spec: dict[str, Any], architecture: dict[str, Any]) -> list[dict[str, Any]]:
    modules = spec["modules"]
    module_tasks = [f"Implement module: {module}" for module in modules]

    return [
        {
            "phase": "P0 - Formalize requirements",
            "tasks": [
                "Validate goal against domain ontology",
                "Resolve missing constraints and assumptions",
                "Freeze machine-readable specification",
            ],
            "exit_criteria": [
                "requirements.json approved",
                "Risk list reviewed",
            ],
        },
        {
            "phase": "P1 - Architecture baseline",
            "tasks": [
                f"Adopt architecture style: {architecture['style']}",
                "Define API contract and database schema",
                "Set CI quality gates",
            ],
            "exit_criteria": [
                "ADR accepted",
                "Schema reviewed",
            ],
        },
        {
            "phase": "P2 - Build core modules",
            "tasks": module_tasks,
            "exit_criteria": [
                "Smoke tests passing",
                "No high-severity static analysis issues",
            ],
        },
        {
            "phase": "P3 - Validation and hardening",
            "tasks": [
                "Run integration scenarios",
                "Validate security controls",
                "Execute rollback drill in staging",
            ],
            "exit_criteria": [
                "All critical scenarios pass",
                "Release gate approved",
            ],
        },
    ]


def build_execution_report(
    spec: dict[str, Any], architecture: dict[str, Any], backlog: list[dict[str, Any]]
) -> dict[str, Any]:
    phases = []
    completed_modules = []

    for phase_index, phase in enumerate(backlog, start=1):
        if phase["phase"].startswith("P0"):
            status = "ready"
        elif phase["phase"].startswith("P1"):
            status = "blocked-until-spec-approved"
        elif phase["phase"].startswith("P2"):
            status = "blocked-until-architecture-baselined"
        else:
            status = "blocked-until-tests-pass"

        phase_modules = [
            task.removeprefix("Implement module: ")
            for task in phase["tasks"]
            if task.startswith("Implement module: ")
        ]
        completed_modules.extend(phase_modules)

        phases.append(
            {
                "order": phase_index,
                "name": phase["phase"],
                "status": status,
                "tasks": phase["tasks"],
                "exit_criteria": phase["exit_criteria"],
                "modules": phase_modules,
            }
        )

    return {
        "goal": spec["goal"],
        "domain": spec["domain"],
        "selected_architecture": architecture,
        "phase_summary": phases,
        "module_coverage": {
            "planned_modules": spec["modules"],
            "included_in_phases": completed_modules,
        },
        "next_action": "Approve requirements, then implement P2 modules in order.",
    }


def build_execution_state(
    spec: dict[str, Any], architecture: dict[str, Any], backlog: list[dict[str, Any]]
) -> dict[str, Any]:
    phases = []
    for phase_index, phase in enumerate(backlog, start=1):
        phase_modules = [
            task.removeprefix("Implement module: ")
            for task in phase["tasks"]
            if task.startswith("Implement module: ")
        ]
        phases.append(
            {
                "order": phase_index,
                "name": phase["phase"],
                "status": "ready" if phase_index == 1 else "pending",
                "tasks": phase["tasks"],
                "exit_criteria": phase["exit_criteria"],
                "modules": phase_modules,
            }
        )

    return {
        "goal": spec["goal"],
        "domain": spec["domain"],
        "selected_architecture": architecture,
        "phase_summary": phases,
        "history": [],
        "last_action": "initialized",
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def advance_execution_state(state: dict[str, Any]) -> dict[str, Any]:
    updated_state = json.loads(json.dumps(state))
    phases = updated_state.get("phase_summary", [])
    current_time = datetime.now(timezone.utc).isoformat()

    in_progress_index = next(
        (index for index, phase in enumerate(phases) if phase.get("status") == "in_progress"),
        None,
    )

    if in_progress_index is not None:
        phases[in_progress_index]["status"] = "completed"
        updated_state["history"].append(
            {
                "phase": phases[in_progress_index]["name"],
                "action": "completed",
                "timestamp": current_time,
            }
        )
        next_index = in_progress_index + 1
        if next_index < len(phases):
            phases[next_index]["status"] = "ready"
            updated_state["history"].append(
                {
                    "phase": phases[next_index]["name"],
                    "action": "unblocked",
                    "timestamp": current_time,
                }
            )
        updated_state["last_action"] = f"completed {phases[in_progress_index]['name']}"
    else:
        ready_index = next(
            (index for index, phase in enumerate(phases) if phase.get("status") == "ready"),
            None,
        )
        if ready_index is None:
            updated_state["last_action"] = "no-op"
        else:
            phases[ready_index]["status"] = "in_progress"
            updated_state["history"].append(
                {
                    "phase": phases[ready_index]["name"],
                    "action": "started",
                    "timestamp": current_time,
                }
            )
            updated_state["last_action"] = f"started {phases[ready_index]['name']}"

    updated_state["last_updated"] = current_time
    return updated_state


def render_execution_state(state: dict[str, Any]) -> str:
    lines: list[str] = ["# Execution State", ""]
    lines.append(f"Goal: {state['goal']}")
    lines.append(f"Domain: {state['domain']}")
    lines.append(f"Last action: {state['last_action']}")
    lines.append("")
    lines.append("## Phases")
    lines.append("")
    for phase in state.get("phase_summary", []):
        lines.append(f"### {phase['order']}. {phase['name']}")
        lines.append(f"- Status: {phase['status']}")
        lines.append("")
    return "\n".join(lines)


def load_execution_state(state_path: Path) -> dict[str, Any] | None:
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text(encoding="utf-8"))


def render_execution_runbook(execution_report: dict[str, Any]) -> str:
    lines: list[str] = ["# Execution Runbook", ""]
    lines.append(f"Goal: {execution_report['goal']}")
    lines.append(f"Domain: {execution_report['domain']}")
    lines.append("")
    lines.append("## Phase Status")
    lines.append("")
    for phase in execution_report["phase_summary"]:
        lines.append(f"### {phase['order']}. {phase['name']}")
        lines.append(f"- Status: {phase['status']}")
        lines.append("- Tasks:")
        for task in phase["tasks"]:
            lines.append(f"  - {task}")
        lines.append("- Exit criteria:")
        for criterion in phase["exit_criteria"]:
            lines.append(f"  - {criterion}")
        lines.append("")
    lines.append("## Next Action")
    lines.append("")
    lines.append(execution_report["next_action"])
    return "\n".join(lines)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def render_adr(architecture: dict[str, Any]) -> str:
    rationale = "\n".join(f"- {item}" for item in architecture["rationale"])
    return f"""# ADR-0001 Initial Architecture

## Context
Initial autonomous planning run.

## Decision
- Style: {architecture['style']}
- Backend: {architecture['backend']}
- Frontend: {architecture['frontend']}
- Database: {architecture['database']}
- Deployment: {architecture['deployment']}
- Cloud target: {architecture['cloud']}

## Rationale
{rationale}

## Consequences
- Enables deterministic phased delivery.
- Keeps decision records explicit for later autonomous revisions.
"""


def render_execution_plan(backlog: list[dict[str, Any]]) -> str:
    lines: list[str] = ["# Execution Plan", ""]
    for index, phase in enumerate(backlog, start=1):
        lines.append(f"## {index}. {phase['phase']}")
        lines.append("")
        lines.append("### Tasks")
        for task in phase["tasks"]:
            lines.append(f"- {task}")
        lines.append("")
        lines.append("### Exit Criteria")
        for item in phase["exit_criteria"]:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def render_scaffold_readme(project_name: str) -> str:
    return f"""# {project_name} Scaffold

This scaffold is generated by autonomous_factory/factory.py.

## Included
- Minimal backend health endpoint
- Initial SQL schema for SGA entities
- Basic Bootstrap frontend placeholder

## Run backend
```bash
cd scaffold/backend/app
python3 main.py
```

Backend health check:
```bash
curl http://127.0.0.1:8000/health
```
"""


def render_backend_main() -> str:
    return """from http.server import BaseHTTPRequestHandler, HTTPServer
import json


class Handler(BaseHTTPRequestHandler):
    def _write_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._write_json(200, {"status": "ok", "service": "sga-backend"})
            return
        self._write_json(404, {"error": "not_found"})


def main():
    server = HTTPServer(("127.0.0.1", 8000), Handler)
    print("Serving on http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
"""


def render_schema_sql() -> str:
    return """CREATE TABLE students (
    id SERIAL PRIMARY KEY,
    registration_number VARCHAR(32) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE professors (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    code VARCHAR(32) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    workload_hours INTEGER NOT NULL CHECK (workload_hours > 0)
);

CREATE TABLE enrollments (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    status VARCHAR(32) NOT NULL,
    enrolled_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (student_id, course_id)
);
"""


def render_frontend_html(project_name: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{project_name} - SGA Bootstrap</title>
    <link
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
        rel="stylesheet"
        integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH"
        crossorigin="anonymous"
    />
</head>
<body class="bg-light">
    <main class="container py-5">
        <div class="row justify-content-center">
            <div class="col-lg-8">
                <div class="card shadow-sm border-0">
                    <div class="card-body p-4 p-md-5">
                        <h1 class="h3 mb-3">{project_name}</h1>
                        <p class="text-secondary mb-4">
                            Initial dashboard placeholder generated by the autonomous factory MVP.
                        </p>
                        <div class="d-flex gap-2 flex-wrap">
                            <span class="badge text-bg-primary">Students</span>
                            <span class="badge text-bg-success">Courses</span>
                            <span class="badge text-bg-warning">Enrollments</span>
                            <span class="badge text-bg-info">Reports</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </main>
</body>
</html>
"""


def render_root_readme(project_name: str, spec: dict[str, Any]) -> str:
    constraints = spec.get("constraints", {})
    pretty_constraints = json.dumps(constraints, indent=2, ensure_ascii=True)
    return f"""# {project_name}

Generated by `autonomous_factory/factory.py`.

## Goal
{spec['goal']}

## Domain
{spec['domain']}

## Constraints
```json
{pretty_constraints}
```

## Generated Artifacts
- `spec/requirements.json`
- `architecture/adr-0001-initial-architecture.md`
- `planning/backlog.json`
- `planning/execution-plan.md`
- `governance/release-gates.md`
- `scaffold/`
"""


def write_project(
    root: Path,
    project_name: str,
    spec: dict[str, Any],
    architecture: dict[str, Any],
    backlog: list[dict[str, Any]],
    execution_report: dict[str, Any] | None = None,
    execution_state: dict[str, Any] | None = None,
) -> None:
    write_file(root / "README.md", render_root_readme(project_name, spec))
    write_file(root / "spec/requirements.json", json.dumps(spec, indent=2, ensure_ascii=True))
    write_file(
        root / "architecture/adr-0001-initial-architecture.md",
        render_adr(architecture),
    )
    write_file(root / "planning/backlog.json", json.dumps(backlog, indent=2, ensure_ascii=True))
    write_file(root / "planning/execution-plan.md", render_execution_plan(backlog))

    release_gates = spec["governance"]["approval_gates"]
    gates_markdown = "\n".join(f"- {gate}" for gate in release_gates)
    write_file(
        root / "governance/release-gates.md",
        "# Release Gates\n\n" + gates_markdown,
    )

    write_file(root / "scaffold/README.md", render_scaffold_readme(project_name))
    write_file(root / "scaffold/backend/app/main.py", render_backend_main())
    write_file(root / "scaffold/database/schema.sql", render_schema_sql())
    write_file(root / "scaffold/frontend/index.html", render_frontend_html(project_name))

    if execution_report is not None:
        write_file(
            root / "execution/report.json",
            json.dumps(execution_report, indent=2, ensure_ascii=True),
        )
        write_file(
            root / "execution/runbook.md",
            render_execution_runbook(execution_report),
        )

    if execution_state is not None:
        write_file(
            root / "execution/state.json",
            json.dumps(execution_state, indent=2, ensure_ascii=True),
        )
        write_file(
            root / "execution/state.md",
            render_execution_state(execution_state),
        )


def main() -> int:
    args = parse_args()
    try:
        constraints = parse_constraints(args.constraint)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    domain = infer_domain(args.goal)
    project_name = args.project_name or slugify(args.goal)

    if args.interactive:
        project_name = prompt_project_name_interactively(project_name)
        constraints = collect_constraints_interactively(constraints, domain)
        print("Resolved constraints:")
        print(json.dumps(constraints, indent=2, ensure_ascii=True))

    output_root = Path(args.output).expanduser().resolve()
    destination = output_root / project_name

    if destination.exists() and any(destination.iterdir()) and not args.force:
        print(
            f"error: destination '{destination}' already exists and is not empty. "
            "Use --force to overwrite.",
            file=sys.stderr,
        )
        return 2

    destination.mkdir(parents=True, exist_ok=True)

    spec = build_spec(args.goal, domain, constraints)
    architecture = choose_architecture(constraints, domain)
    backlog = build_backlog(spec, architecture)
    execution_report = (
        build_execution_report(spec, architecture, backlog)
        if args.dry_run_execution
        else None
    )
    execution_state = None
    state_path = (
        Path(args.state_file).expanduser().resolve()
        if args.state_file
        else destination / "execution" / "state.json"
    )

    if args.dry_run_execution or args.advance_phase or state_path.exists():
        existing_state = load_execution_state(state_path)
        if existing_state is None:
            execution_state = build_execution_state(spec, architecture, backlog)
        else:
            execution_state = existing_state

        if args.advance_phase:
            execution_state = advance_execution_state(execution_state)
        else:
            execution_state["last_action"] = execution_state.get("last_action", "initialized")

        if not args.state_file:
            state_path = destination / "execution" / "state.json"

    write_project(
        destination,
        project_name,
        spec,
        architecture,
        backlog,
        execution_report,
        execution_state,
    )

    print(f"Project generated at: {destination}")
    if execution_report is not None:
        print("Dry-run execution report generated at: execution/report.json")
    if execution_state is not None:
        print("Execution state written at: execution/state.json")
    print("Next step: inspect planning/execution-plan.md and start implementing phase P2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
