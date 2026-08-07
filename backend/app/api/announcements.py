"""公告 API（issue 4）：发布（admin）/ 列表 / 详情 / 附件下载 / 删除。

- POST   /api/admin/announcements        admin：发布公告（multipart：title/body/files[]）
- GET    /api/announcements              公开：公告列表（时间倒序）
- GET    /api/announcements/{id}         公开：公告详情（含附件元数据）
- DELETE /api/admin/announcements/{id}   admin：删除公告（含磁盘附件文件）
- GET    /api/announcements/files/{name} 公开：下载附件（stored_name 定位）

附件存储：backend/uploads/announcements/，磁盘名 = uuid + 原扩展名；
支持 pdf / doc / docx / zip，单文件 ≤ 50MB。发布/删除写审计日志。
"""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.rbac import get_current_user, require_admin
from app.db import get_db
from app.models.announcement import Announcement
from app.models.user import User
from app.schemas.announcement import AnnouncementOut

router = APIRouter()

# backend/uploads/announcements/
_UPLOAD_DIR = (
    Path(__file__).resolve().parent.parent.parent / "uploads" / "announcements"
)
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
_ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".zip"}


def _ensure_upload_dir() -> None:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _validate_attachment(file: UploadFile) -> Path:
    """校验扩展名与大小；返回待写入的目标路径（磁盘名 uuid+扩展名）。"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {suffix or '未知'}，仅支持 pdf / doc / docx / zip",
        )
    target = _UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    size = 0
    with target.open("wb") as f:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > _MAX_FILE_SIZE:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="附件超过 50MB 限制")
            f.write(chunk)
    return target


def _announcement_out(announcement: Announcement) -> dict:
    return {
        "id": announcement.id,
        "title": announcement.title,
        "body": announcement.body,
        "attachments": list(announcement.attachments or []),
        "created_by": announcement.created_by,
        "created_at": announcement.created_at,
    }


def _get_or_404(db: Session, announcement_id: int) -> Announcement:
    announcement = db.get(Announcement, announcement_id)
    if announcement is None:
        raise HTTPException(status_code=404, detail="公告不存在")
    return announcement


@router.post("/api/admin/announcements", response_model=AnnouncementOut)
def create_announcement(
    request: Request,
    title: str = Form(..., min_length=1, max_length=200),
    body: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """admin 发布公告：标题/正文 + 0..n 个附件（pdf/word/zip）。"""
    _ensure_upload_dir()
    attachments = []
    for file in files:
        if not (file.filename or "").strip():
            continue
        target = _validate_attachment(file)
        attachments.append(
            {
                "filename": Path(file.filename).name,
                "stored_name": target.name,
                "size": target.stat().st_size,
                "content_type": file.content_type,
            }
        )

    announcement = Announcement(
        title=title.strip(),
        body=(body or "").strip() or None,
        attachments=attachments,
        created_by=admin.id,
    )
    db.add(announcement)
    db.commit()
    db.refresh(announcement)

    ip = request.client.host if request.client else "unknown"
    log_audit(
        db,
        admin.id,
        "announcement_create",
        ip,
        request.headers.get("user-agent"),
        {
            "announcement_id": announcement.id,
            "title": announcement.title,
            "attachments": len(attachments),
        },
    )
    return _announcement_out(announcement)


@router.get("/api/announcements", response_model=list[AnnouncementOut])
def list_announcements(db: Session = Depends(get_db)):
    """公开：全部公告，最新在前。"""
    rows = db.query(Announcement).order_by(Announcement.id.desc()).all()
    return [_announcement_out(a) for a in rows]


@router.get("/api/announcements/{announcement_id}", response_model=AnnouncementOut)
def get_announcement(announcement_id: int, db: Session = Depends(get_db)):
    """公开：公告详情（含附件元数据）。"""
    return _announcement_out(_get_or_404(db, announcement_id))


@router.get("/api/announcements/files/{stored_name}")
def download_attachment(
    stored_name: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """登录用户下载附件：按 stored_name 在公告附件元数据中定位。"""
    # 防路径穿越：stored_name 必须是纯文件名（uuid.扩展名）。
    if Path(stored_name).name != stored_name:
        raise HTTPException(status_code=400, detail="非法的文件名")
    # SQLite 的 JSON contains 语义不稳，公告数量少，直接在 Python 侧定位。
    row = next(
        (
            ann
            for ann in db.query(Announcement).all()
            if any(
                a.get("stored_name") == stored_name for a in (ann.attachments or [])
            )
        ),
        None,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    meta = next(
        (a for a in (row.attachments or []) if a.get("stored_name") == stored_name),
        None,
    )
    path = _UPLOAD_DIR / stored_name
    if meta is None or not path.is_file():
        raise HTTPException(status_code=404, detail="附件文件不存在")
    return FileResponse(
        path,
        filename=meta.get("filename") or stored_name,
        media_type=meta.get("content_type"),
    )


@router.delete("/api/admin/announcements/{announcement_id}")
def delete_announcement(
    announcement_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """admin 删除公告：移除记录并清理磁盘上的附件文件。"""
    announcement = _get_or_404(db, announcement_id)
    for attachment in announcement.attachments or []:
        (Path(_UPLOAD_DIR) / attachment["stored_name"]).unlink(missing_ok=True)
    db.delete(announcement)
    db.commit()

    ip = request.client.host if request.client else "unknown"
    log_audit(
        db,
        admin.id,
        "announcement_delete",
        ip,
        request.headers.get("user-agent"),
        {"announcement_id": announcement_id, "title": announcement.title},
    )
    return {"ok": True}
