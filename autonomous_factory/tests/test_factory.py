import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

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

            factory.write_project(project_root, project_name, spec, architecture, backlog)

            expected_files = [
                "README.md",
                "spec/requirements.json",
                "architecture/adr-0001-initial-architecture.md",
                "planning/backlog.json",
                "planning/execution-plan.md",
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

            factory.write_project(
                project_root,
                project_name,
                spec,
                architecture,
                backlog,
                execution_report,
                execution_state,
            )

            self.assertTrue((project_root / "execution/report.json").exists())
            self.assertTrue((project_root / "execution/runbook.md").exists())
            self.assertTrue((project_root / "execution/state.json").exists())
            self.assertTrue((project_root / "execution/state.md").exists())


if __name__ == "__main__":
    unittest.main()
