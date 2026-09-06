import unittest

from aegis_diagnosis import AegisPipeline


class PipelineTests(unittest.TestCase):
    def test_overload_pipeline(self):
        payload = {"schema_version": "1.0", "generated_at": "2026-09-06T14:00:00Z", "incident": {"incident_id": "TEST-1", "severity": "high", "status": "active"}, "nodes": [{"node_id": "r3", "node_type": "router", "telemetry": {"cpu": {"usage_percent": 96}, "memory": {"usage_percent": 50, "available_mb": 1024}, "network": {"latency_ms": {"average": 180}, "packet_loss_percent": {"value": 3}}}, "interfaces": [{"interface_id": "r3:eth0", "admin_status": "up", "oper_status": "up", "utilization_percent": {"inbound": 95, "outbound": 30}, "drop_count": 100}]}]}
        result = AegisPipeline().run(payload)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["diagnosis"]["most_likely_root_cause"]["root_cause"], "network_device_overload")
        self.assertTrue(result["digital_twin_handoff"]["plans_to_simulate"])

    def test_invalid_input(self): self.assertEqual(AegisPipeline().run({})["status"], "invalid_input")
