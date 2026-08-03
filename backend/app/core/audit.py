"""审计日志写入辅助（todo 16）。

``log_audit`` 接受一个已打开的 SQLAlchemy 会话（复用请求的 db，例如
``Depends(get_db)`` 注入的那个），也接受 ``None``（此时自动开一个独立
会话写库并关闭）。detail 为可空 dict，原样存入 JSON 列。
"""

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.audit_log import AuditLog


def log_audit(
    db: Session | None,
    user_id: int | None,
    action: str,
    ip: str | None = None,
    user_agent: str | None = None,
    detail: dict | None = None,
) -> None:
    """写入一条审计日志。失败场景 user_id 传 None（未知用户或匿名动作）。"""
    own_session = db is None
    session: Session = db if db is not None else SessionLocal()
    try:
        session.add(
            AuditLog(
                user_id=user_id,
                action=action,
                ip=ip,
                user_agent=user_agent,
                detail=detail,
            )
        )
        session.commit()
    finally:
        if own_session:
            session.close()
