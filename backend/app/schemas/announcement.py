"""Pydantic v2 schemas for the announcement API (issue 4)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentOut(BaseModel):
    """附件元数据（下载经 /api/announcements/files/{stored_name}）。"""

    filename: str
    stored_name: str
    size: int
    content_type: str | None


class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str | None
    attachments: list[AttachmentOut]
    created_by: int
    created_at: datetime
