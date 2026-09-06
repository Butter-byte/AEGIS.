"""Dependency-free integration tests for the Aegis demo pipeline."""

import json
from pathlib import Path
import unittest

from aegis_pipeline import run_pipeline


class AegisPipelineTests(unittest.TestCase):
    def setUp(self):
        sample = Path(__file__).with_name("sample_telemetry.json")
        self.payload = json.loads(sample.read_text(encoding="utf-8"))

    def test_overload_is_diagnosed_and_plans_are_ranked(self):
        result = run_pipeline(self.payload)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["diagnoses"]["most_likely_root_cause"]["root_cause"], "network_device_overload")
        self.assertGreaterEqual(len(result["recovery_plans"]["plan_groups"][0]["plans"]), 2)
        first_plan = result["recovery_plans"]["plan_groups"][0]["plans"][0]
        self.assertIn("This plan is recommended", first_plan["explanation"])
        self.assertIn("llm_grounding_data", first_plan)
        self.assertGreater(result["ranked_recovery_plans"][0]["final_score"], 0)
        final_output = result["final_output"]
        self.assertEqual(final_output["schema_version"], "1.0")
        self.assertIn("digital_twin_handoff", final_output)
        self.assertGreater(len(final_output["digital_twin_handoff"]["plans_to_simulate"]), 0)

    def test_invalid_payload_is_rejected(self):
        self.assertEqual(run_pipeline({})["status"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
