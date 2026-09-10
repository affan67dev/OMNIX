from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from backend.services.supabase_db import select_one, upsert_one


class ZeroKnowledgeError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ZeroKnowledgeService:
    async def upsert_public_key_bundle(self, user_id: str, bundle: Dict[str, Any]) -> Dict[str, Any]:
        required = {"algorithm", "identity_public_key", "prekey_public_key", "prekey_key_id", "device_id"}
        missing = required.difference(bundle.keys())
        if missing:
            raise ZeroKnowledgeError(400, f"Missing public key bundle fields: {', '.join(sorted(missing))}")
        try:
            row = await upsert_one("zk_key_bundles", {"user_id": user_id, **bundle}, "user_id,device_id")
            return deepcopy(row)
        except Exception as exc:
            raise ZeroKnowledgeError(503, "Unable to persist key bundle") from exc

    async def get_public_key_bundle(self, user_id: str) -> Dict[str, Any]:
        try:
            row = await select_one("zk_key_bundles", filters={"user_id": user_id}, columns="user_id,device_id,algorithm,identity_public_key,prekey_public_key,prekey_key_id,updated_at")
        except Exception as exc:
            raise ZeroKnowledgeError(503, "Unable to read key bundle") from exc
        if row is None:
            raise ZeroKnowledgeError(404, "Public key bundle not found")
        return deepcopy(row)

    async def upsert_encrypted_vault(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        required = {"encrypted_vault", "vault_nonce", "vault_salt", "vault_version", "recovery_hint"}
        missing = required.difference(payload.keys())
        if missing:
            raise ZeroKnowledgeError(400, f"Missing encrypted vault fields: {', '.join(sorted(missing))}")
        try:
            row = await upsert_one("encrypted_vaults", {"user_id": user_id, **payload}, "user_id")
            return deepcopy(row)
        except Exception as exc:
            raise ZeroKnowledgeError(503, "Unable to persist encrypted vault") from exc

    async def get_encrypted_vault(self, user_id: str) -> Dict[str, Any]:
        try:
            row = await select_one("encrypted_vaults", filters={"user_id": user_id}, columns="user_id,encrypted_vault,vault_nonce,vault_salt,vault_version,recovery_hint,updated_at")
        except Exception as exc:
            raise ZeroKnowledgeError(503, "Unable to read encrypted vault") from exc
        if row is None:
            raise ZeroKnowledgeError(404, "Encrypted vault not found")
        return deepcopy(row)


zero_knowledge_service = ZeroKnowledgeService()
