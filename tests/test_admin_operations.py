from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_admin_moderation_requires_authentication():
    response = client.post("/api/admin/moderation/flag", json={"content": "spam", "action": "spam"})

    assert response.status_code == 401


def test_trigger_signup_notification_webhook_returns_pending_payload():
    result = main.trigger_signup_notification_webhook({"username": "ops", "email": "ops@example.com"})

    assert result["status"] == "queued"
    assert result["channel"] == "phone"
