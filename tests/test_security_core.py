import os

os.environ["JWT_SECRET"] = "x" * 64
os.environ["OTP_PEPPER"] = "y" * 64

from backend.core.security import create_access_token, decode_access_token, generate_otp, hash_otp, verify_otp_hash


def test_otp_is_six_digits_and_hash_is_not_plaintext():
    otp = generate_otp()
    assert len(otp) == 6 and otp.isdigit()
    digest = hash_otp("challenge-1", otp)
    assert digest != otp
    assert verify_otp_hash("challenge-1", otp, digest)
    assert not verify_otp_hash("challenge-1", "000000", digest)


def test_access_token_contains_revocation_id():
    token, jti, expires_at = create_access_token("user-1", "+911234567890", "tester")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["jti"] == jti
    assert expires_at is not None
