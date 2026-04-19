import unittest
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
        with patch("builtins.input", side_effect=["", "", "", "", ""]):
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
        constraints = factory.collect_constraints_interactively(
            initial, "academic_management"
        )
        self.assertEqual(constraints, initial)


if __name__ == "__main__":
    unittest.main()
