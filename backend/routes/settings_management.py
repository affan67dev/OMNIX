from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr

from backend.core.security import CurrentUser
from backend.services.settings_management import SettingsError, settings_management

router = APIRouter(prefix="/api/settings", tags=["Settings Management"])


def user_id(current_user: CurrentUser) -> str:
    return str(current_user["sub"])


def raise_settings_error(error: SettingsError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


class PersonalInformationRequest(BaseModel):
    phone_number: str
    email: EmailStr
    gender: str
    date_of_birth: str

class DataExportRequest(BaseModel):
    include_messages: bool = True
    include_posts: bool = True
    include_profile: bool = True

class AccountActionRequest(BaseModel):
    reason: str = ""

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class PasswordResetRequest(BaseModel):
    channel: str
    destination: str

class PasswordResetVerifyRequest(BaseModel):
    challenge_id: str
    otp_code: str
    new_password: str

class TwoFactorSetupRequest(BaseModel):
    method: str

class TwoFactorVerifyRequest(BaseModel):
    setup_id: str
    code: str

class AlertPreferencesRequest(BaseModel):
    login_alerts_enabled: bool
    unrecognized_device_alerts: bool

class ContentPreferencesRequest(BaseModel):
    sensitive_content_control: str
    hide_like_view_counts: bool
    mention_policy: str
    tag_policy: str

class StorySettingsRequest(BaseModel):
    auto_save_to_archive: bool
    save_to_phone_gallery: bool

class StorageSettingsRequest(BaseModel):
    cellular_data_saver: bool
    photo_auto_download: str
    video_auto_download: str

class NotificationPreferencesRequest(BaseModel):
    push_likes: bool
    push_comments: bool
    push_new_followers: bool
    push_direct_messages: bool
    push_calls: bool
    push_app_updates: bool

class PauseNotificationsRequest(BaseModel):
    duration: str


@router.get("/overview")
async def get_settings_overview(current_user: CurrentUser):
    return {"success": True, **settings_management.get_overview(user_id(current_user))}

@router.get("/account")
async def get_account_settings(current_user: CurrentUser):
    return {"success": True, "account": settings_management.get_overview(user_id(current_user))["account"]}

@router.patch("/account/personal-information")
async def update_personal_information(req: PersonalInformationRequest, current_user: CurrentUser):
    account = settings_management.update_personal_information(user_id(current_user), req.phone_number, req.email, req.gender, req.date_of_birth)
    return {"success": True, "account": account}

@router.post("/account/export")
async def request_account_export(req: DataExportRequest, current_user: CurrentUser):
    export_request = settings_management.request_data_export(user_id(current_user), req.include_messages, req.include_posts, req.include_profile)
    return {"success": True, "export": export_request}

@router.get("/exports/{export_id}/download")
async def download_account_export(export_id: str, current_user: CurrentUser):
    try:
        payload = settings_management.build_export_payload(user_id(current_user), export_id)
    except SettingsError as error:
        raise_settings_error(error)
    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, mode="w", compression=ZIP_DEFLATED) as zip_file:
        zip_file.writestr("account-export.json", json.dumps(payload, indent=2))
    archive_buffer.seek(0)
    return StreamingResponse(archive_buffer, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{export_id}.zip"'})

@router.post("/account/deactivate")
async def deactivate_account(req: AccountActionRequest, current_user: CurrentUser):
    result = settings_management.deactivate_account(user_id(current_user), req.reason)
    return {"success": True, **result}

@router.post("/account/delete")
async def schedule_account_delete(req: AccountActionRequest, current_user: CurrentUser):
    account = settings_management.schedule_account_deletion(user_id(current_user), req.reason)
    return {"success": True, "account": account}

@router.post("/account/restore")
async def restore_deleted_account(current_user: CurrentUser):
    try:
        account = settings_management.restore_account(user_id(current_user))
    except SettingsError as error:
        raise_settings_error(error)
    return {"success": True, "account": account}

@router.post("/security/change-password")
async def change_password(req: ChangePasswordRequest, current_user: CurrentUser):
    try:
        security = settings_management.change_password(user_id(current_user), req.current_password, req.new_password)
    except SettingsError as error:
        raise_settings_error(error)
    return {"success": True, "security": security}

@router.post("/security/password-reset/request")
async def request_password_reset(req: PasswordResetRequest, current_user: CurrentUser):
    try:
        challenge = settings_management.request_password_reset(user_id(current_user), req.channel, req.destination)
    except SettingsError as error:
        raise_settings_error(error)
    return {"success": True, "challenge": challenge}

@router.post("/security/password-reset/verify")
async def verify_password_reset(req: PasswordResetVerifyRequest):
    try:
        result = settings_management.verify_password_reset(req.challenge_id, req.otp_code, req.new_password)
    except SettingsError as error:
        raise_settings_error(error)
    return result

@router.post("/security/2fa/setup")
async def setup_two_factor(req: TwoFactorSetupRequest, current_user: CurrentUser):
    try:
        setup = settings_management.setup_2fa(user_id(current_user), req.method)
    except SettingsError as error:
        raise_settings_error(error)
    return {"success": True, "setup": setup}

@router.post("/security/2fa/verify")
async def verify_two_factor(req: TwoFactorVerifyRequest, current_user: CurrentUser):
    try:
        security = settings_management.verify_2fa_setup(user_id(current_user), req.setup_id, req.code)
    except SettingsError as error:
        raise_settings_error(error)
    return {"success": True, "security": security}

@router.post("/security/2fa/disable")
async def disable_two_factor(current_user: CurrentUser):
    security = settings_management.disable_2fa(user_id(current_user))
    return {"success": True, "security": security}

@router.patch("/security/alerts")
async def update_security_alerts(req: AlertPreferencesRequest, current_user: CurrentUser):
    security = settings_management.update_alert_preferences(user_id(current_user), req.login_alerts_enabled, req.unrecognized_device_alerts)
    return {"success": True, "security": security}

@router.get("/security/sessions")
async def list_active_sessions(current_user: CurrentUser):
    return {"success": True, "sessions": settings_management.list_sessions(user_id(current_user))}

@router.delete("/security/sessions/{session_id}")
async def logout_session(session_id: str, current_user: CurrentUser):
    try:
        settings_management.logout_session(user_id(current_user), session_id)
    except SettingsError as error:
        raise_settings_error(error)
    return {"success": True, "message": "Session ended"}

@router.post("/security/sessions/logout-all-other-devices")
async def logout_all_other_devices(current_user: CurrentUser):
    result = settings_management.logout_all_other_sessions(user_id(current_user), keep_current_session=True)
    return {"success": True, **result}

@router.get("/privacy/blocked")
async def list_blocked_accounts(current_user: CurrentUser):
    return {"success": True, "blocked_accounts": settings_management.list_blocked_accounts(user_id(current_user))}

@router.get("/privacy/muted")
async def list_muted_accounts(current_user: CurrentUser):
    return {"success": True, "muted_accounts": settings_management.list_muted_accounts(user_id(current_user))}

@router.patch("/privacy/content-preferences")
async def update_content_preferences(req: ContentPreferencesRequest, current_user: CurrentUser):
    try:
        settings = settings_management.update_content_preferences(user_id(current_user), req.sensitive_content_control, req.hide_like_view_counts, req.mention_policy, req.tag_policy)
    except SettingsError as error:
        raise_settings_error(error)
    return {"success": True, "content_preferences": settings}

@router.get("/archive")
async def get_archive_content(current_user: CurrentUser):
    return {"success": True, "archives": settings_management.get_archives(user_id(current_user))}

@router.patch("/archive/story-settings")
async def update_story_settings(req: StorySettingsRequest, current_user: CurrentUser):
    settings = settings_management.update_story_settings(user_id(current_user), req.auto_save_to_archive, req.save_to_phone_gallery)
    return {"success": True, "story_settings": settings}

@router.get("/storage")
async def get_storage_settings(current_user: CurrentUser):
    return {"success": True, "storage_settings": settings_management.get_overview(user_id(current_user))["storage_settings"]}

@router.post("/storage/clear-cache")
async def clear_local_cache(current_user: CurrentUser):
    result = settings_management.clear_cache(user_id(current_user))
    return {"success": True, **result}

@router.patch("/storage/preferences")
async def update_storage_preferences(req: StorageSettingsRequest, current_user: CurrentUser):
    try:
        settings = settings_management.update_storage_settings(user_id(current_user), req.cellular_data_saver, req.photo_auto_download, req.video_auto_download)
    except SettingsError as error:
        raise_settings_error(error)
    return {"success": True, "storage_settings": settings}

@router.get("/notifications")
async def get_notification_preferences(current_user: CurrentUser):
    return {"success": True, "notification_settings": settings_management.get_overview(user_id(current_user))["notification_settings"]}

@router.patch("/notifications")
async def update_notification_preferences(req: NotificationPreferencesRequest, current_user: CurrentUser):
    settings = settings_management.update_notification_preferences(user_id(current_user), req.push_likes, req.push_comments, req.push_new_followers, req.push_direct_messages, req.push_calls, req.push_app_updates)
    return {"success": True, "notification_settings": settings}

@router.post("/notifications/pause-all")
async def pause_all_notifications(req: PauseNotificationsRequest, current_user: CurrentUser):
    try:
        settings = settings_management.pause_notifications(user_id(current_user), req.duration)
    except SettingsError as error:
        raise_settings_error(error)
    return {"success": True, "notification_settings": settings}
