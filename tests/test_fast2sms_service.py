import asyncio
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.services.fast2sms_service import normalize_indian_mobile, send_otp


def test_normalize_indian_mobile():
    assert normalize_indian_mobile("+919876543210") == "9876543210"


@pytest.mark.parametrize("value", ["+911234567890", "+91876543210x", "+14155552671"])
def test_normalize_indian_mobile_rejects_invalid(value):
    with pytest.raises(ValueError):
        normalize_indian_mobile(value)


def test_send_otp_is_mocked():
    os.environ["FAST2SMS_API_KEY"] = "dummy"
    os.environ["FAST2SMS_OTP_ID"] = "template"
    os.environ["FAST2SMS_BASE_URL"] = "https://example.invalid/dev"
    response = httpx.Response(200, json={"return": True, "request_id": "REQ-1"})
    client = AsyncMock()
    client.__aenter__.return_value.post = AsyncMock(return_value=response)

    async def run():
        with patch("backend.services.fast2sms_service.httpx.AsyncClient", return_value=client):
            result = await send_otp("+919876543210", "123456", challenge_id="challenge-1")
            call = client.__aenter__.return_value.post.await_args
            assert result.success is True
            assert call.kwargs["json"]["mobile"] == "9876543210"
            assert call.kwargs["json"]["otp"] == "123456"
            assert call.kwargs["json"]["otp_id"] == "template"

    asyncio.run(run())


def test_send_otp_failure_is_safe():
    os.environ["FAST2SMS_API_KEY"] = "dummy"
    os.environ["FAST2SMS_OTP_ID"] = "template"
    response = httpx.Response(401, json={"message": "provider error"})
    client = AsyncMock()
    client.__aenter__.return_value.post = AsyncMock(return_value=response)

    async def run():
        with patch("backend.services.fast2sms_service.httpx.AsyncClient", return_value=client):
            with pytest.raises(RuntimeError, match="authentication failed"):
                await send_otp("+919876543210", "123456", challenge_id="challenge-1")

    asyncio.run(run())
