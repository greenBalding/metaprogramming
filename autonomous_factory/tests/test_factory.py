import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import config.local_llm_client as local_llm_client

from autonomous_factory import factory


class FactoryTests(unittest.TestCase):
    def test_infer_domain_for_sga_goal(self):
        domain = factory.infer_domain("build a SGA for a university")
        self.assertEqual(domain, "academic_management")

    def test_parse_constraints_coercion(self):
        constraints = factory.parse_constraints(
            [
                "users=15000",
                "cloud=aws",
                "compliance=LGPD,FERPA",
            ]
        )
        self.assertEqual(constraints["users"], 15000)
        self.assertEqual(constraints["cloud"], "aws")
        self.assertEqual(constraints["compliance"], ["LGPD", "FERPA"])

    def test_choose_architecture_thresholds(self):
        small = factory.choose_architecture({"users": 2000}, "academic_management")
        medium = factory.choose_architecture({"users": 12000}, "academic_management")
        large = factory.choose_architecture({"users": 90000}, "academic_management")

        self.assertEqual(small["style"], "modular monolith")
        self.assertEqual(medium["style"], "modular monolith + async workers")
        self.assertEqual(large["style"], "microservices + event-driven")

    def test_collect_constraints_interactively_defaults(self):
        with patch("builtins.input", side_effect=["", "", "", "", ""]), patch(
            "builtins.print"
        ):
            constraints = factory.collect_constraints_interactively(
                {}, "academic_management"
            )

        self.assertEqual(constraints["users"], 3000)
        self.assertEqual(constraints["cloud"], "agnostic")
        self.assertEqual(constraints["budget"], "medium")
        self.assertEqual(constraints["compliance"], ["LGPD"])
        self.assertEqual(constraints["delivery"], "web")

    def test_collect_constraints_interactively_respects_existing_values(self):
        initial = {
            "users": 22000,
            "cloud": "aws",
            "budget": "high",
            "compliance": ["LGPD"],
            "delivery": "hybrid",
        }
        with patch("builtins.print"):
            constraints = factory.collect_constraints_interactively(
                initial, "academic_management"
            )
        self.assertEqual(constraints, initial)

    def test_ensure_local_llm_config_writes_file(self):
        with TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            created = factory.ensure_local_llm_config(
                repo_root,
                {
                    "provider": "ollama",
                    "model": "qwen2.5-coder:7b",
                },
            )
            self.assertTrue(created)
            config_path = repo_root / "config/local_llm.json"
            self.assertTrue(config_path.exists())

    def test_ensure_local_llm_config_is_idempotent(self):
        with TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            first = factory.ensure_local_llm_config(
                repo_root,
                {
                    "provider": "ollama",
                    "model": "qwen2.5-coder:7b",
                },
            )
            second = factory.ensure_local_llm_config(
                repo_root,
                {
                    "provider": "ollama",
                    "model": "qwen2.5-coder:14b",
                },
            )
            self.assertTrue(first)
            self.assertFalse(second)

            config_path = repo_root / "config/local_llm.json"
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["model"], "qwen2.5-coder:7b")

    def test_generate_local_llm_advice_falls_back_without_config(self):
        with TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            advice = local_llm_client.generate_local_llm_advice(
                repo_root,
                goal="build a SGA",
                domain="academic_management",
                project_name="sga-ci",
                architecture={"style": "modular monolith"},
                spec={"modules": ["authentication"], "entities": ["Student"]},
                decision_log={"entries": []},
            )

            self.assertEqual(advice["source"], "deterministic-fallback")
            self.assertIn("authentication", advice["next_step"])

    def test_generate_local_llm_advice_uses_mocked_ollama_response(self):
        with TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            config_path = repo_root / "config/local_llm.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps({"provider": "ollama", "model": "qwen2.5-coder:7b"}),
                encoding="utf-8",
            )

            with patch(
                "config.local_llm_client._run_ollama_prompt",
                return_value=json.dumps(
                    {
                        "summary": "Use qwen2.5-coder:7b for the first bounded step.",
                        "risk_level": "low",
                        "next_step": "Generate the first module stub.",
                        "reason": "Model is a good fit for local code tasks.",
                    }
                ),
            ):
                advice = local_llm_client.generate_local_llm_advice(
                    repo_root,
                    goal="build a SGA",
                    domain="academic_management",
                    project_name="sga-ci",
                    architecture={"style": "modular monolith"},
                    spec={"modules": ["authentication"], "entities": ["Student"]},
                    decision_log={"entries": []},
                )

        self.assertEqual(advice["source"], "ollama")
        self.assertEqual(advice["model"], "qwen2.5-coder:7b")
        self.assertEqual(advice["risk_level"], "low")

    def test_write_project_creates_expected_artifacts(self):
        with TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir)
            project_name = "sga-ci"
            project_root = output_root / project_name

            constraints = {
                "users": 12000,
                "cloud": "aws",
                "budget": "medium",
                "compliance": ["LGPD"],
            }
            spec = factory.build_spec("build a SGA", "academic_management", constraints)
            architecture = factory.choose_architecture(constraints, "academic_management")
            backlog = factory.build_backlog(spec, architecture)
            decision_log = factory.build_decision_log(
                "build a SGA",
                "academic_management",
                project_name,
                constraints,
                [
                    {"key": "goal", "value": "build a SGA", "source": "input"},
                ],
            )
            decision_log_hash = factory.compute_decision_log_hash(decision_log)
            decision_log["integrity"] = {
                "algorithm": "sha256",
                "hash": decision_log_hash,
                "artifact": "planning/decision-log.json",
            }

            factory.write_project(
                project_root,
                project_name,
                spec,
                architecture,
                backlog,
                decision_log,
            )

            expected_files = [
                "README.md",
                "spec/requirements.json",
                "architecture/adr-0001-initial-architecture.md",
                "planning/backlog.json",
                "planning/execution-plan.md",
                "planning/decision-log.json",
                "planning/decision-log.md",
                "governance/release-gates.md",
                "scaffold/backend/app/main.py",
                "scaffold/database/schema.sql",
                "scaffold/frontend/index.html",
            ]
            for relative_path in expected_files:
                self.assertTrue(
                    (project_root / relative_path).exists(),
                    msg=f"Missing generated artifact: {relative_path}",
                )

    def test_execution_report_includes_phase_statuses(self):
        constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
        spec = factory.build_spec("build a SGA", "academic_management", constraints)
        architecture = factory.choose_architecture(constraints, "academic_management")
        backlog = factory.build_backlog(spec, architecture)

        execution_report = factory.build_execution_report(spec, architecture, backlog)

        self.assertEqual(execution_report["goal"], "build a SGA")
        self.assertEqual(execution_report["domain"], "academic_management")
        self.assertEqual(len(execution_report["phase_summary"]), len(backlog))
        self.assertEqual(
            execution_report["phase_summary"][0]["status"], "ready"
        )
        self.assertIn("planned_modules", execution_report["module_coverage"])

    def test_build_decision_log_contains_expected_entries(self):
        decision_entries = [
            {"key": "goal", "value": "build a SGA", "source": "input"},
            {"key": "domain", "value": "academic_management", "source": "inference"},
            {"key": "users", "value": 15000, "source": "cli"},
        ]
        decision_log = factory.build_decision_log(
            "build a SGA",
            "academic_management",
            "sga-ci",
            {"users": 15000},
            decision_entries,
        )

        self.assertEqual(decision_log["project_name"], "sga-ci")
        self.assertEqual(len(decision_log["entries"]), 3)
        self.assertEqual(decision_log["entries"][1]["key"], "domain")
        self.assertEqual(decision_log["entries"][1]["source"], "inference")

    def test_compute_decision_log_hash_is_deterministic(self):
        decision_entries = [
            {"key": "goal", "value": "build a SGA", "source": "input"},
            {"key": "domain", "value": "academic_management", "source": "inference"},
        ]
        decision_log = factory.build_decision_log(
            "build a SGA",
            "academic_management",
            "sga-ci",
            {"users": 15000},
            decision_entries,
        )
        first_hash = factory.compute_decision_log_hash(decision_log)
        second_hash = factory.compute_decision_log_hash(decision_log)
        self.assertEqual(first_hash, second_hash)
        self.assertEqual(len(first_hash), 64)

    def test_verify_decision_log_integrity_success(self):
        with TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sga-ci"
            decision_log = factory.build_decision_log(
                "build a SGA",
                "academic_management",
                "sga-ci",
                {"users": 15000},
                [{"key": "goal", "value": "build a SGA", "source": "input"}],
            )
            decision_hash = factory.compute_decision_log_hash(decision_log)
            decision_log["integrity"] = {
                "algorithm": "sha256",
                "hash": decision_hash,
                "artifact": "planning/decision-log.json",
            }
            factory.write_file(
                project_root / "planning/decision-log.json",
                json.dumps(decision_log, indent=2, ensure_ascii=True),
            )
            factory.write_file(
                project_root / "planning/decision-log.sha256",
                f"{decision_hash}  decision-log.json",
            )

            verified, message = factory.verify_decision_log_integrity(project_root)
            self.assertTrue(verified)
            self.assertIn("verified", message)

    def test_verify_decision_log_integrity_detects_tampering(self):
        with TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sga-ci"
            decision_log = factory.build_decision_log(
                "build a SGA",
                "academic_management",
                "sga-ci",
                {"users": 15000},
                [{"key": "goal", "value": "build a SGA", "source": "input"}],
            )
            decision_hash = factory.compute_decision_log_hash(decision_log)
            decision_log["integrity"] = {
                "algorithm": "sha256",
                "hash": decision_hash,
                "artifact": "planning/decision-log.json",
            }

            tampered_log = dict(decision_log)
            tampered_log["constraints"] = {"users": 99999}
            factory.write_file(
                project_root / "planning/decision-log.json",
                json.dumps(tampered_log, indent=2, ensure_ascii=True),
            )
            factory.write_file(
                project_root / "planning/decision-log.sha256",
                f"{decision_hash}  decision-log.json",
            )

            verified, message = factory.verify_decision_log_integrity(project_root)
            self.assertFalse(verified)
            self.assertIn("mismatch", message)

    def test_execution_state_advances_progressively(self):
        constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
        spec = factory.build_spec("build a SGA", "academic_management", constraints)
        architecture = factory.choose_architecture(constraints, "academic_management")
        backlog = factory.build_backlog(spec, architecture)

        state = factory.build_execution_state(spec, architecture, backlog)
        self.assertEqual(state["phase_summary"][0]["status"], "ready")

        state = factory.advance_execution_state(state)
        self.assertEqual(state["phase_summary"][0]["status"], "in_progress")

        state = factory.advance_execution_state(state)
        self.assertEqual(state["phase_summary"][0]["status"], "completed")
        self.assertEqual(state["phase_summary"][1]["status"], "ready")

    def test_write_project_persists_execution_artifacts(self):
        with TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir)
            project_name = "sga-execution"
            project_root = output_root / project_name

            constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
            spec = factory.build_spec("build a SGA", "academic_management", constraints)
            architecture = factory.choose_architecture(constraints, "academic_management")
            backlog = factory.build_backlog(spec, architecture)
            execution_report = factory.build_execution_report(spec, architecture, backlog)
            execution_state = factory.build_execution_state(spec, architecture, backlog)
            decision_log = factory.build_decision_log(
                "build a SGA",
                "academic_management",
                project_name,
                constraints,
                [
                    {"key": "goal", "value": "build a SGA", "source": "input"},
                ],
            )
            decision_log_hash = factory.compute_decision_log_hash(decision_log)
            decision_log["integrity"] = {
                "algorithm": "sha256",
                "hash": decision_log_hash,
                "artifact": "planning/decision-log.json",
            }
            local_llm_advice = local_llm_client.generate_local_llm_advice(
                output_root,
                goal="build a SGA",
                domain="academic_management",
                project_name=project_name,
                architecture=architecture,
                spec=spec,
                decision_log=decision_log,
            )

            factory.write_project(
                project_root,
                project_name,
                spec,
                architecture,
                backlog,
                decision_log,
                local_llm_advice,
                execution_report,
                execution_state,
            )

            self.assertTrue((project_root / "execution/report.json").exists())
            self.assertTrue((project_root / "execution/runbook.md").exists())
            self.assertTrue((project_root / "execution/state.json").exists())
            self.assertTrue((project_root / "execution/state.md").exists())
            self.assertTrue((project_root / "execution/audit-trail.json").exists())
            self.assertTrue((project_root / "planning/decision-log.json").exists())
            self.assertTrue((project_root / "planning/decision-log.sha256").exists())
            self.assertTrue((project_root / "analysis/local-llm-advice.json").exists())
            self.assertTrue((project_root / "analysis/local-llm-advice.md").exists())

    def test_execute_phase_actions_writes_evidence_and_advances_phase(self):
        with TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sga-exec"
            constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
            spec = factory.build_spec("build a SGA", "academic_management", constraints)
            architecture = factory.choose_architecture(constraints, "academic_management")
            backlog = factory.build_backlog(spec, architecture)
            state = factory.build_execution_state(spec, architecture, backlog)

            updated_state = factory.execute_phase_actions(project_root, state)

            self.assertEqual(updated_state["phase_summary"][0]["status"], "completed")
            self.assertEqual(updated_state["phase_summary"][1]["status"], "ready")
            evidence_files = list((project_root / "execution" / "evidence" / "p01").glob("*.md"))
            self.assertEqual(len(evidence_files), 3)
            self.assertGreaterEqual(len(updated_state["audit_trail"]), 4)

    def test_execute_phase_actions_dry_run_keeps_tasks_pending(self):
        with TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sga-exec"
            constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
            spec = factory.build_spec("build a SGA", "academic_management", constraints)
            architecture = factory.choose_architecture(constraints, "academic_management")
            backlog = factory.build_backlog(spec, architecture)
            state = factory.build_execution_state(spec, architecture, backlog)

            updated_state = factory.execute_phase_actions(
                project_root,
                state,
                dry_run_actions=True,
            )

            self.assertEqual(updated_state["phase_summary"][0]["status"], "in_progress")
            pending_tasks = [
                task["status"]
                for task in updated_state["phase_summary"][0]["task_status"]
            ]
            self.assertTrue(all(status == "pending" for status in pending_tasks))
            self.assertFalse((project_root / "execution" / "evidence").exists())

    def test_execute_phase_actions_skips_already_completed_tasks(self):
        with TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sga-exec"
            constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
            spec = factory.build_spec("build a SGA", "academic_management", constraints)
            architecture = factory.choose_architecture(constraints, "academic_management")
            backlog = factory.build_backlog(spec, architecture)
            state = factory.build_execution_state(spec, architecture, backlog)

            phase = state["phase_summary"][0]
            phase["status"] = "in_progress"
            phase["task_status"][0]["status"] = "completed"

            updated_state = factory.execute_phase_actions(project_root, state)
            task_events = [
                event
                for event in updated_state["audit_trail"]
                if event["event_type"] == "task_execution"
            ]
            skipped = [event for event in task_events if event["status"] == "skipped_already_completed"]
            self.assertEqual(len(skipped), 1)

    def test_execute_phase_actions_generates_handler_artifacts(self):
        with TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sga-exec"
            constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
            spec = factory.build_spec("build a SGA", "academic_management", constraints)
            architecture = factory.choose_architecture(constraints, "academic_management")
            backlog = factory.build_backlog(spec, architecture)
            state = factory.build_execution_state(spec, architecture, backlog)

            state = factory.execute_phase_actions(project_root, state)

            self.assertTrue((project_root / "execution/validation/domain-check.json").exists())
            self.assertTrue((project_root / "planning/constraint-resolution.md").exists())
            self.assertTrue((project_root / "spec/requirements.lock.json").exists())

            state = factory.execute_phase_actions(project_root, state)

            self.assertTrue((project_root / "architecture/implementation-notes.md").exists())
            self.assertTrue((project_root / "planning/api-contract.md").exists())
            self.assertTrue((project_root / ".github/workflows/ci-generated.yml").exists())

    def test_execute_phase_actions_generates_module_stubs_in_p2(self):
        with TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sga-exec"
            constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
            spec = factory.build_spec("build a SGA", "academic_management", constraints)
            architecture = factory.choose_architecture(constraints, "academic_management")
            backlog = factory.build_backlog(spec, architecture)
            state = factory.build_execution_state(spec, architecture, backlog)

            state = factory.execute_phase_actions(project_root, state)
            state = factory.execute_phase_actions(project_root, state)
            state = factory.execute_phase_actions(project_root, state)

            modules_dir = project_root / "scaffold/backend/app/modules"
            self.assertTrue(modules_dir.exists())
            generated_modules = sorted(path.stem for path in modules_dir.glob("*.py"))
            self.assertEqual(generated_modules, sorted(spec["modules"]))
            self.assertEqual(state["phase_summary"][2]["status"], "completed")

    def test_rollback_last_task_reverts_created_files_and_task_status(self):
        with TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sga-exec"
            constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
            spec = factory.build_spec("build a SGA", "academic_management", constraints)
            architecture = factory.choose_architecture(constraints, "academic_management")
            backlog = factory.build_backlog(spec, architecture)
            state = factory.build_execution_state(spec, architecture, backlog)

            state = factory.execute_phase_actions(project_root, state)
            self.assertTrue((project_root / "spec/requirements.lock.json").exists())

            rolled_back = factory.rollback_last_task(project_root, state)

            self.assertFalse((project_root / "spec/requirements.lock.json").exists())
            p0_tasks = rolled_back["phase_summary"][0]["task_status"]
            freeze_task = [task for task in p0_tasks if task["title"] == "Freeze machine-readable specification"][0]
            self.assertEqual(freeze_task["status"], "pending")
            self.assertEqual(rolled_back["phase_summary"][0]["status"], "in_progress")
            rollback_events = [
                event for event in rolled_back["audit_trail"] if event["event_type"] == "rollback"
            ]
            self.assertEqual(len(rollback_events), 1)
            self.assertEqual(rollback_events[0]["status"], "completed")

    def test_rollback_last_task_without_completed_event_is_noop(self):
        constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
        spec = factory.build_spec("build a SGA", "academic_management", constraints)
        architecture = factory.choose_architecture(constraints, "academic_management")
        backlog = factory.build_backlog(spec, architecture)
        state = factory.build_execution_state(spec, architecture, backlog)

        with TemporaryDirectory() as tmp_dir:
            rolled_back = factory.rollback_last_task(Path(tmp_dir) / "sga-exec", state)

        self.assertIn("no-op", rolled_back["last_action"])
        rollback_events = [
            event for event in rolled_back["audit_trail"] if event["event_type"] == "rollback"
        ]
        self.assertEqual(len(rollback_events), 1)
        self.assertEqual(rollback_events[0]["status"], "no-op")

    def test_rollback_last_task_restores_updated_file_content(self):
        with TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sga-exec"
            constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
            spec = factory.build_spec("build a SGA", "academic_management", constraints)
            architecture = factory.choose_architecture(constraints, "academic_management")
            backlog = factory.build_backlog(spec, architecture)
            state = factory.build_execution_state(spec, architecture, backlog)

            phase = state["phase_summary"][1]
            task = [
                item
                for item in phase["task_status"]
                if item["title"] == "Define API contract and database schema"
            ][0]
            phase["status"] = "ready"
            state["phase_summary"] = [
                {
                    "order": 1,
                    "name": phase["name"],
                    "status": "ready",
                    "tasks": [task["title"]],
                    "task_status": [task],
                    "exit_criteria": phase["exit_criteria"],
                    "modules": [],
                }
            ]

            previous_content = "# Previous contract\n"
            factory.write_file(project_root / "planning/api-contract.md", previous_content)

            executed = factory.execute_phase_actions(project_root, state)
            self.assertNotEqual(
                (project_root / "planning/api-contract.md").read_text(encoding="utf-8"),
                previous_content,
            )

            rolled_back = factory.rollback_last_task(project_root, executed)
            self.assertEqual(
                (project_root / "planning/api-contract.md").read_text(encoding="utf-8"),
                previous_content,
            )
            rollback_event = [
                event
                for event in rolled_back["audit_trail"]
                if event["event_type"] == "rollback"
            ][0]
            self.assertIn("planning/api-contract.md", rollback_event["details"]["reverted_files"])

    def test_rollback_twice_targets_previous_completed_tasks(self):
        with TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sga-exec"
            constraints = {"users": 15000, "cloud": "aws", "budget": "medium"}
            spec = factory.build_spec("build a SGA", "academic_management", constraints)
            architecture = factory.choose_architecture(constraints, "academic_management")
            backlog = factory.build_backlog(spec, architecture)
            state = factory.build_execution_state(spec, architecture, backlog)

            executed = factory.execute_phase_actions(project_root, state)
            self.assertTrue((project_root / "spec/requirements.lock.json").exists())
            self.assertTrue((project_root / "planning/constraint-resolution.md").exists())

            rolled_once = factory.rollback_last_task(project_root, executed)
            self.assertFalse((project_root / "spec/requirements.lock.json").exists())
            self.assertTrue((project_root / "planning/constraint-resolution.md").exists())

            rolled_twice = factory.rollback_last_task(project_root, rolled_once)
            self.assertFalse((project_root / "planning/constraint-resolution.md").exists())
            self.assertEqual(len(rolled_twice["rolled_back_event_ids"]), 2)


if __name__ == "__main__":
    unittest.main()
