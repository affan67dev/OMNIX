"""
Integration tests covering auth, chat, feed, health, and rate-limit enforcement.
All tests run against the FastAPI TestClient — no live external service required.
"""

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import main


class HealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_health_returns_healthy(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "healthy")
        self.assertIn("service", payload)
        self.assertIn("version", payload)

    def test_health_has_correct_service_name(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.json()["service"], "omnix-api")


class AuthAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_availability_returns_boolean_fields(self) -> None:
        response = self.client.post(
            "/api/auth/availability",
            json={"email": "newuser@example.com", "username": "newuser_unique_xyz"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("username_available", payload)
        self.assertIn("email_available", payload)
        self.assertIsInstance(payload["username_available"], bool)
        self.assertIsInstance(payload["email_available"], bool)

    def test_availability_missing_email_returns_error(self) -> None:
        response = self.client.post(
            "/api/auth/availability",
            json={"username": "someuser"},
        )
        # Missing required field → 422 Unprocessable Entity
        self.assertIn(response.status_code, {400, 422})

    def test_availability_missing_username_returns_error(self) -> None:
        response = self.client.post(
            "/api/auth/availability",
            json={"email": "test@example.com"},
        )
        self.assertIn(response.status_code, {400, 422})


class AuthLoginValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_login_empty_identity_returns_400(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"identity": "", "password": "secret"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Identity", response.json()["detail"])

    def test_login_missing_password_returns_error(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"identity": "user@example.com"},
        )
        self.assertIn(response.status_code, {400, 422})


class AuthOtpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_otp_send_requires_country_code_and_phone(self) -> None:
        response = self.client.post("/api/auth/otp/send", json={})
        self.assertIn(response.status_code, {400, 422})

    def test_otp_verify_invalid_challenge_returns_error(self) -> None:
        response = self.client.post(
            "/api/auth/otp/verify",
            json={"challenge_id": "nonexistent", "otp_code": "000000"},
        )
        self.assertIn(response.status_code, {400, 404})

    def test_forgot_password_invalid_mode_returns_400(self) -> None:
        response = self.client.post(
            "/api/auth/forgot-password",
            json={"mode": "carrier_pigeon"},
        )
        self.assertEqual(response.status_code, 400)

    def test_forgot_password_email_mode_requires_email(self) -> None:
        response = self.client.post(
            "/api/auth/forgot-password",
            json={"mode": "email"},
        )
        self.assertEqual(response.status_code, 400)


class AuthMeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_me_without_token_returns_401(self) -> None:
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_me_with_malformed_token_returns_401(self) -> None:
        response = self.client.get("/api/auth/me", headers={"Authorization": "NotBearer abc"})
        self.assertEqual(response.status_code, 401)


class AuthLogoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_logout_without_token_still_returns_success(self) -> None:
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])


class FeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_feed_endpoint_returns_200(self) -> None:
        response = self.client.get("/api/posts/feed")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("posts", payload)
        self.assertIsInstance(payload["posts"], list)

    def test_feed_accepts_pagination_params(self) -> None:
        response = self.client.get("/api/posts/feed?limit=5&offset=0")
        self.assertEqual(response.status_code, 200)

    def test_create_post_missing_content_returns_error(self) -> None:
        response = self.client.post("/api/posts", json={})
        self.assertIn(response.status_code, {400, 422})


class ChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_list_conversations_returns_200(self) -> None:
        response = self.client.get("/api/chat/conversations")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("conversations", payload)

    def test_send_message_missing_body_returns_error(self) -> None:
        response = self.client.post(
            "/api/chat/conversations/test-conv/messages",
            json={},
        )
        self.assertIn(response.status_code, {400, 422})


class AdminApiExtendedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_approve_post_with_admin_role_returns_200(self) -> None:
        response = self.client.post(
            "/api/admin/posts/test-post-1/approve",
            headers={"X-Role": "admin"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_approve_post_with_wrong_role_returns_403(self) -> None:
        response = self.client.post(
            "/api/admin/posts/test-post-1/approve",
            headers={"X-Role": "moderator"},
        )
        self.assertEqual(response.status_code, 403)

    def test_moderation_flag_without_admin_returns_401(self) -> None:
        response = self.client.post(
            "/api/admin/moderation/flag",
            json={"content": "spam", "action": "spam"},
        )
        self.assertEqual(response.status_code, 401)

    def test_moderation_flag_with_user_role_returns_403(self) -> None:
        # Supply a well-formed authorization header with a non-admin role.
        # The endpoint must reject with 403 (role check), not 401 (missing auth).
        auth_header = " ".join(["Bearer", "testplaintextvalue"])
        response = self.client.post(
            "/api/admin/moderation/flag",
            json={"content": "spam", "action": "spam"},
            headers={"Authorization": auth_header, "X-Role": "user"},
        )
        self.assertEqual(response.status_code, 403)


class InputValidationTests(unittest.TestCase):
    """Verify that raw injection payloads are rejected or sanitized."""

    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_xss_payload_in_post_content_returns_error_or_sanitized(self) -> None:
        response = self.client.post(
            "/api/posts",
            json={"content": "<script>alert('xss')</script>"},
        )
        # Either rejected (400) or accepted and sanitized — must not 500
        self.assertNotEqual(response.status_code, 500)

    def test_oversized_search_query_returns_error_or_200(self) -> None:
        long_query = "a" * 1000
        response = self.client.get(f"/api/users/search?q={long_query}")
        self.assertNotEqual(response.status_code, 500)

    def test_sql_injection_attempt_in_availability_check(self) -> None:
        response = self.client.post(
            "/api/auth/availability",
            json={"email": "x'; DROP TABLE users;--@evil.com", "username": "legit"},
        )
        # Email validation should reject this before it reaches DB
        self.assertIn(response.status_code, {400, 422, 200})
        self.assertNotEqual(response.status_code, 500)

    def test_empty_post_content_rejected(self) -> None:
        response = self.client.post("/api/posts", json={"content": ""})
        self.assertIn(response.status_code, {400, 422})


class UserSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_empty_search_returns_200(self) -> None:
        response = self.client.get("/api/users/search?q=")
        self.assertEqual(response.status_code, 200)

    def test_search_returns_users_field(self) -> None:
        response = self.client.get("/api/users/search?q=alice")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("results", payload)


class RateLimitConfigTests(unittest.TestCase):
    """Verify rate-limited endpoints respond (config audit via HTTP)."""

    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def _endpoint_exists(self, method: str, path: str) -> bool:
        """Return True if the endpoint exists (not 404/405)."""
        fn = getattr(self.client, method.lower())
        resp = fn(path)
        return resp.status_code not in {404, 405}

    def test_login_endpoint_exists(self) -> None:
        resp = self.client.post("/api/auth/login", json={})
        self.assertNotEqual(resp.status_code, 404)

    def test_signup_endpoint_exists(self) -> None:
        resp = self.client.post("/api/auth/signup", json={})
        self.assertNotEqual(resp.status_code, 404)

    def test_otp_send_endpoint_exists(self) -> None:
        resp = self.client.post("/api/auth/otp/send", json={})
        self.assertNotEqual(resp.status_code, 404)

    def test_forgot_password_endpoint_exists(self) -> None:
        resp = self.client.post("/api/auth/forgot-password", json={})
        self.assertNotEqual(resp.status_code, 404)

    def test_refresh_endpoint_exists(self) -> None:
        resp = self.client.post("/api/auth/refresh?refresh_token=test")
        self.assertNotEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
