import unittest

from fastapi.testclient import TestClient

import main


class AdminApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_admin_metrics_require_authentication(self) -> None:
        response = self.client.get('/api/admin/metrics')
        self.assertEqual(response.status_code, 403)

    def test_moderation_actions_require_authentication(self) -> None:
        response = self.client.post('/api/admin/posts/seed-post-2/approve')
        self.assertEqual(response.status_code, 403)


if __name__ == '__main__':
    unittest.main()
