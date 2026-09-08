from pathlib import Path

from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


async def _fake_authenticate_local(*_args, **_kwargs):
    return "local-user"


async def _fake_authenticate_nova(*_args, **_kwargs):
    return "user-nova"


def test_delete_post_requires_authentication():
    response = client.delete("/api/posts/seed-post-1")

    assert response.status_code == 401


def test_delete_post_rejects_non_owner(monkeypatch):
    monkeypatch.setattr(main, "require_authenticated_user_id", _fake_authenticate_nova)

    response = client.delete("/api/posts/seed-post-1", headers={"Authorization": "******"})

    assert response.status_code == 403


def test_chat_stream_requires_authentication():
    response = client.get("/api/chat/conversations/shadow-node/stream")

    assert response.status_code == 401


def test_signup_otp_hidden_by_default(monkeypatch):
    monkeypatch.delenv("EXPOSE_DEV_OTP", raising=False)

    response = client.post("/api/auth/otp/send", json={"country_code": "+1", "phone_number": "2025550199"})

    assert response.status_code == 200
    assert "otp_code" not in response.json()


def test_auth_me_uses_bearer_token(monkeypatch):
    captured = {}

    async def fake_fetch_authenticated_user(authorization, access_token=None):
        captured["authorization"] = authorization
        captured["access_token"] = access_token
        return {"id": "user-1", "email": "user@example.com"}

    monkeypatch.setattr(main, "fetch_authenticated_user", fake_fetch_authenticated_user)

    response = client.get("/api/auth/me", headers={"Authorization": "******"})

    assert response.status_code == 200
    assert captured == {"authorization": "******", "access_token": None}
    assert response.json()["user"]["id"] == "user-1"


def test_admin_oob_endpoints_require_authentication():
    response = client.post("/api/admin-auth/phone/respond", json={"challenge_id": "missing", "decision": "yes"})

    assert response.status_code == 401


def test_forgot_password_template_no_embedded_supabase_credentials():
    template = Path("/home/runner/work/OMNIX/OMNIX/templates/forgot-password.html").read_text()

    assert "createClient(" not in template
    assert "supabase.co" not in template
