import unittest

from scripts.native_surface_map import (
    build_review,
    help_observations,
)


class NativeSurfaceMapTests(unittest.TestCase):
    def test_observes_verbatim_help_surface(self) -> None:
        outputs = {
            (): "Usage: claude\n\nOptions:\n  --test  Display test output\n",
            ("config",): "Usage: claude config\n\nDisplay config values\n",
        }
        observations = help_observations(
            outputs,
            {"Display test output", "Display config values", "Not visible"},
        )
        self.assertEqual(
            observations["Display test output"],
            ["claude --help"],
        )
        self.assertEqual(
            observations["Display config values"],
            ["claude config --help"],
        )
        self.assertNotIn("Not visible", observations)

    def test_approves_only_observed_validated_records(self) -> None:
        reference = {
            "units": [
                {
                    "id": "one",
                    "source": "Observed help",
                    "risk": "SAFE",
                    "surface": "cli.help",
                },
                {
                    "id": "two",
                    "source": "Only binary",
                    "risk": "SAFE",
                    "surface": "cli.visible",
                },
                {
                    "id": "three",
                    "source": "Unsafe",
                    "risk": "DANGER",
                    "surface": "cli.ast.literal",
                },
            ]
        }
        review = build_review(
            reference,
            {"Observed help": [100], "Only binary": [200]},
            {"Observed help": ["claude --help"]},
            "2.1.220",
            "abc",
            1,
        )
        self.assertEqual([item["id"] for item in review["approved"]], ["one"])
        self.assertEqual([item["id"] for item in review["pending"]], ["two"])
        self.assertEqual(review["approved"][0]["surface"], "cli.help")


if __name__ == "__main__":
    unittest.main()
