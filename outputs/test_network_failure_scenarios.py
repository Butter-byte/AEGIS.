"""Regression tests for the twenty Aegis network-failure scenarios."""

import unittest

from network_failure_scenarios import scenarios
from aegis_pipeline import run_pipeline


class NetworkFailureScenarioTests(unittest.TestCase):
    def test_twenty_scenarios_match_expected_root_causes(self):
        catalog = scenarios()
        self.assertEqual(len(catalog), 20)
        for scenario in catalog:
            with self.subTest(scenario=scenario.scenario_id):
                result = run_pipeline(scenario.telemetry_input)
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["diagnoses"]["most_likely_root_cause"]["root_cause"], scenario.expected_root_cause)
                actual = {item["anomaly_type"] for item in result["anomalies"]["findings"]}
                self.assertTrue(set(scenario.expected_anomalies).issubset(actual))
                self.assertTrue(result["final_output"]["digital_twin_handoff"]["plans_to_simulate"])


if __name__ == "__main__":
    unittest.main()
