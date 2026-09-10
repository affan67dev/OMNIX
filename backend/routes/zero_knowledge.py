from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.security import CurrentUser
from backend.services.zero_knowledge import ZeroKnowledgeError, zero_knowledge_service

router = APIRouter(prefix="/api/v1/security", tags=["Zero Knowledge Security"])


def raise_zero_knowledge_error(error: ZeroKnowledgeError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


class PublicKeyBundleRequest(BaseModel):
    algorithm: str = Field(min_length=3, max_length=64)
    identity_public_key: str = Field(min_length=16, max_length=8192)
    prekey_public_key: str = Field(min_length=16, max_length=8192)
    prekey_key_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(default="primary-device", min_length=1, max_length=128)


class EncryptedVaultRequest(BaseModel):
    encrypted_vault: str = Field(min_length=1, max_length=2_000_000)
    vault_nonce: str = Field(min_length=8, max_length=256)
    vault_salt: str = Field(min_length=8, max_length=256)
    vault_version: int = Field(gt=0, le=1000)
    recovery_hint: str = Field(min_length=1, max_length=512)


@router.put("/e2ee/key-bundle")
async def upsert_e2ee_key_bundle(req: PublicKeyBundleRequest, current_user: CurrentUser):
    try:
        bundle = await zero_knowledge_service.upsert_public_key_bundle(current_user["sub"], req.model_dump())
    except ZeroKnowledgeError as error:
        raise_zero_knowledge_error(error)
    return {"success": True, "bundle": bundle}


@router.get("/e2ee/key-bundle/{user_id}")
async def get_e2ee_key_bundle(user_id: str, current_user: CurrentUser):
    # Public key bundles are intentionally readable to authenticated users; private vaults are not.
    try:
        bundle = await zero_knowledge_service.get_public_key_bundle(user_id)
    except ZeroKnowledgeError as error:
        raise_zero_knowledge_error(error)
    return {"success": True, "bundle": bundle}


@router.put("/lock-vault")
async def upsert_lock_vault(req: EncryptedVaultRequest, current_user: CurrentUser):
    try:
        vault = await zero_knowledge_service.upsert_encrypted_vault(current_user["sub"], req.model_dump())
    except ZeroKnowledgeError as error:
        raise_zero_knowledge_error(error)
    return {"success": True, "vault": vault}


@router.get("/lock-vault")
async def get_lock_vault(current_user: CurrentUser):
    try:
        vault = await zero_knowledge_service.get_encrypted_vault(current_user["sub"])
    except ZeroKnowledgeError as error:
        raise_zero_knowledge_error(error)
    return {"success": True, "vault": vault}
