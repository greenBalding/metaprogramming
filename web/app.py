"""
Web backend for the metaprogramming platform.
Integrates the interactive factory with a conversational interface.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Add parent directory to path so we can import factory
sys.path.insert(0, str(Path(__file__).parent.parent))

from autonomous_factory import factory

app = FastAPI(title="Metaprogramming Platform")

# Serve static files (HTML, CSS, JS)
web_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=web_dir), name="static")

# Store conversation state
conversations = {}


class ChatRequest(BaseModel):
    message: str
    conversationId: str
    projectName: Optional[str] = None
    projectData: Optional[dict] = None


class ChatResponse(BaseModel):
    response: str
    projectName: Optional[str] = None
    projectData: Optional[dict] = None
    projectGenerated: bool = False
    projectPath: Optional[str] = None
    systemMessage: Optional[str] = None
    error: Optional[str] = None


def get_or_create_conversation(conv_id: str) -> dict:
    """Get or create a conversation state."""
    if conv_id not in conversations:
        conversations[conv_id] = {
            "messages": [],
            "state": "initial",  # initial, collecting_goal, collecting_constraints, generating, complete
            "goal": None,
            "constraints": {},
            "project_name": None,
            "domain": None,
            "architecture": None,
        }
    return conversations[conv_id]


def extract_goal_and_constraints(message: str) -> tuple:
    """
    Extract goal and constraints from user message.
    Example: "build a support portal for 5000 users on AWS"
    Returns: (goal, constraints)
    """
    import re

    goal = message
    constraints = {}

    # Extract users
    users_match = re.search(r'(\d+)\s*(?:users?|people)', message, re.IGNORECASE)
    if users_match:
        constraints['users'] = int(users_match.group(1))

    # Extract cloud provider
    for cloud in ['aws', 'azure', 'gcp', 'google cloud']:
        if cloud.lower() in message.lower():
            constraints['cloud'] = cloud.split()[0].lower()  # get first word
            break

    # Extract budget
    for budget in ['low', 'medium', 'high']:
        if budget in message.lower():
            constraints['budget'] = budget
            break

    # Extract compliance
    compliance_match = re.search(r'(?:complian[t|ce]|gdpr|hipaa|lgpd|ferpa)[:\s]+([^,.]*)', 
                                 message, re.IGNORECASE)
    if compliance_match:
        compliance_str = compliance_match.group(1).strip()
        constraints['compliance'] = [c.strip() for c in compliance_str.split(',')]

    return goal, constraints


def slugify(value: str) -> str:
    """Convert string to URL-safe slug."""
    import re
    value = re.sub(r'[^\w\s-]', '', value).strip()
    value = re.sub(r'[-\s]+', '-', value)
    return value.lower()


def build_assistant_response(conv: dict, user_message: str) -> dict[str, Any]:
    """Build appropriate assistant response based on conversation state."""

    if conv["state"] == "initial":
        # Extract goal and constraints from initial message
        goal, constraints = extract_goal_and_constraints(user_message)
        conv["goal"] = goal
        conv["constraints"] = constraints

        response_text = f"Great! So you want to: **{goal}**\n\n"

        if constraints:
            response_text += "I detected these constraints:\n"
            for key, value in constraints.items():
                response_text += f"• {key}: {value}\n"
            response_text += "\n"

        # Ask for missing constraints
        response_text += "Let me ask a few clarifying questions:\n\n"

        if "users" not in constraints:
            response_text += "1. **How many users** do you expect? (e.g., 1000, 10000)"
            conv["state"] = "collecting_constraints"
            return {
                "response": response_text,
                "projectName": None,
                "projectData": {},
                "projectGenerated": False,
            }

        if "cloud" not in constraints:
            response_text += "2. **Which cloud provider** (AWS, Azure, GCP, or agnostic)?"
            conv["state"] = "collecting_constraints"
            return {
                "response": response_text,
                "projectName": None,
                "projectData": {},
                "projectGenerated": False,
            }

        # All constraints collected, move to generation
        conv["state"] = "generating"
        return {
            "response": "Perfect! I have all the info. Generating your project...",
            "projectName": None,
            "projectData": {},
            "projectGenerated": False,
        }

    elif conv["state"] == "collecting_constraints":
        # Parse constraint from user message
        if "users" not in conv["constraints"]:
            users_match = None
            import re
            match = re.search(r'(\d+)', user_message)
            if match:
                conv["constraints"]["users"] = int(match.group(1))
                return {
                    "response": "Got it! **What cloud provider** do you prefer? (AWS, Azure, GCP, or agnostic)",
                    "projectName": None,
                    "projectData": {},
                    "projectGenerated": False,
                }

        if "cloud" not in conv["constraints"]:
            for cloud in ['aws', 'azure', 'gcp', 'google cloud', 'agnostic']:
                if cloud.lower() in user_message.lower():
                    conv["constraints"]["cloud"] = cloud.split()[0].lower()
                    conv["state"] = "generating"
                    return {
                        "response": "Perfect! Generating your project scaffold now...",
                        "projectName": None,
                        "projectData": {},
                        "projectGenerated": False,
                    }

        return {
            "response": "Sorry, I didn't understand. Can you clarify?",
            "projectName": None,
            "projectData": {},
            "projectGenerated": False,
        }

    elif conv["state"] == "generating":
        # Actually generate the project
        try:
            goal = conv["goal"]
            constraints = conv["constraints"]

            # Derive project name from goal
                project_name = slugify(goal)
            conv["project_name"] = project_name

            # Build the project
                spec = factory.build_spec(goal, "generic_web_application", constraints)
            architecture = factory.choose_architecture(constraints, spec.get("domain", "generic_web_application"))
            backlog = factory.build_backlog(spec, architecture)
                decision_log = factory.build_decision_log(project_name, goal, constraints, spec, architecture, backlog)

            # Create project directory
            output_dir = Path("generated") / project_name
            output_dir.mkdir(parents=True, exist_ok=True)

            # Write all artifacts
            factory.write_project(
                project_path=str(output_dir),
                goal=goal,
                constraints=constraints,
                spec=spec,
                architecture=architecture,
                backlog=backlog,
                decision_log=decision_log,
            )

            conv["state"] = "complete"
            conv["domain"] = spec.get("domain")
            conv["architecture"] = architecture.get("style")

            response_text = f"""✅ **Project Generated Successfully!**

**Project:** {project_name}
**Domain:** {spec.get("domain", "generic")}
**Architecture:** {architecture.get("style", "unknown")}

📁 **Location:** `generated/{project_name}`

**Generated Artifacts:**
• Specification (`spec/requirements.json`)
• Architecture Decision Record (`architecture/adr-0001-initial-architecture.md`)
• Intent Contract (`planning/intent-contract.json`)
• Execution Plan (`planning/execution-plan.md`)
• Backlog (`planning/backlog.json`)
• Project Scaffold (`scaffold/backend`, `scaffold/frontend`, `scaffold/database`)

**Next Steps:**
1. Review the execution plan: `planning/execution-plan.md`
2. Start the backend: `cd generated/{project_name}/scaffold/backend/app && python3 main.py`
3. Open the frontend: `generated/{project_name}/scaffold/frontend/index.html`

What would you like to do next?"""

            return {
                "response": response_text,
                "projectName": project_name,
                "projectData": {
                    "domain": spec.get("domain"),
                    "architecture": architecture.get("style"),
                    "entities": spec.get("entities", []),
                    "modules": spec.get("modules", []),
                },
                "projectGenerated": True,
                "projectPath": str(output_dir),
                "systemMessage": f"Project {project_name} is ready to use!",
            }

        except Exception as e:
            conv["state"] = "complete"
            return {
                "error": f"Failed to generate project: {str(e)}",
                "projectName": None,
                "projectData": {},
                "projectGenerated": False,
            }

    elif conv["state"] == "complete":
        # Handle post-generation interactions
        response_text = f"""Your project **{conv['project_name']}** is ready!

You can:
• Review the generated code in `generated/{conv['project_name']}`
• Run the backend: `cd generated/{conv['project_name']}/scaffold/backend/app && python3 main.py`
• Customize any files you need
• Or describe a new project to build another one

What would you like to do?"""

        return {
            "response": response_text,
            "projectName": conv["project_name"],
            "projectData": conv.get("projectData", {}),
            "projectGenerated": False,
        }

    return {
        "error": "Unknown state",
        "projectName": None,
        "projectData": {},
        "projectGenerated": False,
    }


@app.get("/")
async def get_root():
    """Serve the main HTML page."""
    return FileResponse(web_dir / "index.html")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat messages and coordinate with the factory."""
    try:
        conv = get_or_create_conversation(request.conversationId)
        conv["messages"].append({"role": "user", "content": request.message})

        result = build_assistant_response(conv, request.message)
        conv["messages"].append({"role": "assistant", "content": result["response"]})

        return ChatResponse(**result)

    except Exception as e:
        return ChatResponse(
            response="",
            error=f"Server error: {str(e)}",
            projectName=None,
            projectData={},
            projectGenerated=False,
        )


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "metaprogramming-web"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
