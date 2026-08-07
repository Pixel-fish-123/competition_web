"""TDD tests for the announcement API（issue 4）.

覆盖：
- admin 发布公告（multipart：title/body + pdf 附件）→ 200，列表/详情可见。
- 非 admin 发布 → 403；游客读取列表/详情 → 200（公开）。
- 附件下载 → 200 + 正确 Content-Disposition；非法扩展名 → 400。
- 删除公告 → 200，磁盘附件文件一并清理。

上传目录通过 monkeypatch ``_UPLOAD_DIR`` 指向临时目录，避免污染仓库。
"""

import io

from app.db import SessionLocal
from app.models.announcement import Announcement

# 上传目录由 fixture 指向 tmp_path；这里仅导入模块供 monkeypatch 用。
from app.api import announcements as announcements_api

PASSWORD = "secret123"

PDF_BYTES = b"%PDF-1.4 test fake pdf content"


def _register(client, username="player1", email="p1@example.com"):
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _post_announcement(admin_client, *, title="测试公告", body="正文", files=None, **extra):
    data = {"title": title, "body": body}
    data.update(extra)
    uploads = files or []
    return admin_client.post(
        "/api/admin/announcements",
        data=data,
        files=uploads,
    )


def _make_pdf_upload(filename="rule.pdf"):
    return (
        "files",
        (filename, io.BytesIO(PDF_BYTES), "application/pdf"),
    )


def test_admin_create_list_and_detail(admin_client, tmp_path, monkeypatch):
    monkeypatch.setattr(announcements_api, "_UPLOAD_DIR", tmp_path)
    resp = _post_announcement(
        admin_client,
        title="赛程须知",
        body="请于赛前查看赛程",
        files=[_make_pdf_upload("赛程.pdf")],
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["title"] == "赛程须知"
    assert data["body"] == "请于赛前查看赛程"
    assert len(data["attachments"]) == 1
    att = data["attachments"][0]
    assert att["filename"] == "赛程.pdf"
    assert att["size"] == len(PDF_BYTES)

    ann_id = data["id"]
    # 公开列表/详情。
    rows = admin_client.get("/api/announcements")
    assert rows.status_code == 200
    assert rows.json()[0]["id"] == ann_id
    detail = admin_client.get(f"/api/announcements/{ann_id}")
    assert detail.status_code == 200
    assert detail.json()["attachments"][0]["stored_name"] == att["stored_name"]
    # 文件真实落盘。
    assert (tmp_path / att["stored_name"]).read_bytes() == PDF_BYTES


def test_announcement_download_attachment(admin_client, tmp_path, monkeypatch):
    monkeypatch.setattr(announcements_api, "_UPLOAD_DIR", tmp_path)
    created = _post_announcement(
        admin_client, files=[_make_pdf_upload("rule.pdf")]
    ).json()
    stored = created["attachments"][0]["stored_name"]

    resp = admin_client.get(f"/api/announcements/files/{stored}")
    assert resp.status_code == 200
    assert resp.content == PDF_BYTES
    assert "rule.pdf" in resp.headers.get("content-disposition", "")


def test_announcement_public_read_without_login(client, tmp_path, monkeypatch):
    """列表/详情是公开端点（无需登录）；下载需要登录。"""
    monkeypatch.setattr(announcements_api, "_UPLOAD_DIR", tmp_path)
    with SessionLocal() as db:
        ann = Announcement(title="公开公告", body="公开正文", created_by=1, attachments=[])
        db.add(ann)
        db.commit()
        ann_id = ann.id

    assert client.get("/api/announcements").status_code == 200
    assert client.get(f"/api/announcements/{ann_id}").status_code == 200


def test_non_admin_cannot_publish(admin_client, tmp_path, monkeypatch):
    monkeypatch.setattr(announcements_api, "_UPLOAD_DIR", tmp_path)
    _register(admin_client)
    resp = _post_announcement(admin_client, title="越权")
    assert resp.status_code == 403


def test_publish_rejects_unsupported_extension(admin_client, tmp_path, monkeypatch):
    monkeypatch.setattr(announcements_api, "_UPLOAD_DIR", tmp_path)
    bad = ("files", ("evil.exe", io.BytesIO(b"MZ..."), "application/octet-stream"))
    resp = _post_announcement(admin_client, files=[bad])
    assert resp.status_code == 400
    assert "仅支持" in resp.json()["detail"]


def test_delete_announcement_removes_file(admin_client, tmp_path, monkeypatch):
    monkeypatch.setattr(announcements_api, "_UPLOAD_DIR", tmp_path)
    created = _post_announcement(
        admin_client, files=[_make_pdf_upload("rule.pdf")]
    ).json()
    ann_id = created["id"]
    stored = created["attachments"][0]["stored_name"]
    assert (tmp_path / stored).exists()

    resp = admin_client.delete(f"/api/admin/announcements/{ann_id}")
    assert resp.status_code == 200, resp.text
    assert not (tmp_path / stored).exists()
    assert admin_client.get(f"/api/announcements/{ann_id}").status_code == 404


def test_delete_announcement_requires_admin(admin_client, tmp_path, monkeypatch):
    monkeypatch.setattr(announcements_api, "_UPLOAD_DIR", tmp_path)
    created = _post_announcement(admin_client).json()
    _register(admin_client, username="lurker", email="lurker@example.com")
    resp = admin_client.delete(f"/api/admin/announcements/{created['id']}")
    assert resp.status_code == 403
