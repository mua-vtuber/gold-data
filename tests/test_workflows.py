import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTest(unittest.TestCase):
    def test_update_mode_uses_schedule_expression_not_runtime_clock(self):
        workflow = (ROOT / ".github/workflows/update-gold-price.yml").read_text(encoding="utf-8")

        self.assertIn("github.event.schedule", workflow)
        self.assertNotIn("date -u +%H", workflow)

    def test_realtime_workflow_passes_api_key_secret(self):
        workflow = (ROOT / ".github/workflows/fetch-realtime.yml").read_text(encoding="utf-8")

        self.assertIn("KOREADATA_API_KEY: ${{ secrets.KOREADATA_API_KEY }}", workflow)

    def test_data_workflows_run_regression_tests_before_updating_files(self):
        for workflow_name in ("update-gold-price.yml", "fetch-realtime.yml"):
            workflow = (ROOT / ".github/workflows" / workflow_name).read_text(
                encoding="utf-8"
            )
            test_position = workflow.index("python -m unittest discover -s tests")
            update_position = workflow.index("python scripts/")
            self.assertLess(test_position, update_position, workflow_name)

    def test_workflows_use_node24_actions(self):
        for workflow_path in (ROOT / ".github" / "workflows").glob("*.yml"):
            workflow = workflow_path.read_text(encoding="utf-8")
            if "actions/checkout@" in workflow:
                self.assertIn("actions/checkout@v5", workflow, workflow_path.name)
                self.assertNotIn("actions/checkout@v4", workflow, workflow_path.name)
            if "actions/setup-python@" in workflow:
                self.assertIn("actions/setup-python@v6", workflow, workflow_path.name)
                self.assertNotIn("actions/setup-python@v5", workflow, workflow_path.name)


if __name__ == "__main__":
    unittest.main()
