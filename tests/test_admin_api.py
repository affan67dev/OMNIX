import unittest

from fastapi.testclient import TestClient

import main


class AdminApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_health_endpoint_exposes_basic_service_metadata(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "healthy")
        self.assertEqual(payload["service"], "omnix-api")

    def test_moderation_actions_require_admin_headers(self) -> None:
        response = self.client.post("/api/admin/moderation/flag", json={"content": "spam", "action": "spam"})
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
