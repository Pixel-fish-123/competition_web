"""对局 API（todo 14）：列表 / 详情 / 开赛 / 记分 / 玩法日志导入。

路由（Metis C7：对局由引擎赛程创建，不提供人工创建端点）：
- GET  /api/competitions/{competition_id}/matches   任意登录用户：赛程列表
- GET  /api/matches/{match_id}                       任意登录用户：单局详情
- POST /api/matches/{match_id}/start                 裁判（须在本场 referee_ids）
- POST /api/matches/{match_id}/result                裁判（须在本场 referee_ids）
- POST /api/matches/{match_id}/gameplay-log          裁判：导入 demo 玩法日志
- GET  /api/matches/{match_id}/gameplay-log          任意登录用户：读取已存日志

玩法插件已从对局流程解耦：开赛不再建玩法会话，对局完全由裁判手工管理
（记分输入红蓝双方得分 + 胜者）。demo 控制器的玩法日志通过
``POST .../gameplay-log`` 上传解析后存入 ``match.gameplay_log`` 供展示。
"""

import csv
import io
import json
import re
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.rbac import get_current_user, require_referee
from app.db import get_db
from app.models.competition import Competition
from app.models.match import Match
from app.models.registration import Registration
from app.models.team import Team
from app.models.user import User
from app.schemas.match import MatchDetailOut, MatchOut, MatchResultIn, MatchStartIn
from app.services import match_service

router = APIRouter()

# demo 导出日志的胜负事件文本 -> 阵营映射。
# 约定（用户确认）：守护者=defender=蓝方=participant_b；掠夺者=attacker=红方
# =participant_a。比赛页面统一标注「掠夺者 / 守护者」。
_VICTORY_WINNER_MAP = {
    "守护者获胜": "defender",
    "掠夺者获胜": "attacker",
    "平局": "draw",
}


def _request_meta(request: Request) -> tuple[str, str | None]:
    ip = request.client.host if request.client else "unknown"
    return ip, request.headers.get("user-agent")


def _get_competition_or_404(db: Session, competition_id: int) -> Competition:
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")
    return competition


def _get_match_or_404(db: Session, match_id: int) -> Match:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    return match


def _resolve_participant_names(
    db: Session,
    competition_id: int,
    participant_a: int | None,
    participant_b: int | None,
) -> tuple[str | None, str | None]:
    """解析两名参赛者的显示名称（队伍=队名，个体=昵称或用户名）。

    批量查询避免 N+1：Registration 一次 in_ 取出，Team/User 再各一次批量查。
    参赛者 id 可能同时是某队的 team_id 或某个人的 user_id，按该报名记录的
    participant_type 决定解析方式；找不到返回 None。
    """
    ids = [pid for pid in (participant_a, participant_b) if pid is not None]
    names: dict[int, str | None] = {}
    if ids:
        regs = (
            db.query(Registration)
            .filter(
                Registration.competition_id == competition_id,
                Registration.status == "approved",
                (Registration.team_id.in_(ids)) | (Registration.user_id.in_(ids)),
            )
            .all()
        )
        team_ids = [r.team_id for r in regs if r.team_id is not None]
        user_ids = [r.user_id for r in regs if r.user_id is not None]
        teams = (
            {t.id: t.name for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
            if team_ids
            else {}
        )
        users = (
            {
                u.id: (u.nickname or u.username)
                for u in db.query(User).filter(User.id.in_(user_ids)).all()
            }
            if user_ids
            else {}
        )
        for pid in ids:
            reg = next((r for r in regs if r.team_id == pid or r.user_id == pid), None)
            if reg is None:
                names[pid] = None
            elif reg.participant_type == "team":
                names[pid] = teams.get(pid)
            else:
                names[pid] = users.get(pid)
    return names.get(participant_a), names.get(participant_b)


def _match_out(db: Session, match: Match) -> MatchOut:
    """序列化单局对局并填充参赛者显示名称。"""
    a_name, b_name = _resolve_participant_names(
        db, match.competition_id, match.participant_a, match.participant_b
    )
    return MatchOut.model_validate(match).model_copy(
        update={
            "participant_a_name": a_name,
            "participant_b_name": b_name,
        }
    )


# ------------------------------------------------------------ gameplay log


def _parse_gameplay_log(content: bytes) -> list[dict]:
    """解析 demo 控制器导出的玩法日志 -> [{time, type, text}, ...]。

    - JSON: ``[{"time": "00:32", "text": "...", "type": "occupy"}, ...]``
      （兼容 ``{"events": [...]}`` 包裹结构）。
    - CSV: BOM + ``time,type,text`` 表头 + 数据行。
    两者都无法识别 / 无任何事件时抛 ValueError（清晰错误，不静默返回空）。
    """
    text = content.decode("utf-8-sig", errors="replace").lstrip("\ufeff \t\r\n")
    if not text.strip():
        raise ValueError("日志文件为空")

    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("events"), list):
        data = data["events"]
    if isinstance(data, list):
        events = [
            {
                "time": str(item.get("time") or ""),
                "type": str(item.get("type") or "system"),
                "text": str(item.get("text") or ""),
            }
            for item in data
            if isinstance(item, dict)
        ]
        if not events:
            raise ValueError("日志文件中没有任何事件")
        return events
    if data is not None:
        raise ValueError("无法识别的 JSON 格式：应为事件数组")

    reader = csv.DictReader(io.StringIO(text))
    fields = [f.strip() for f in (reader.fieldnames or [])]
    if not {"time", "type", "text"}.issubset(fields):
        raise ValueError("无法识别的日志格式：需要 JSON 事件数组或 CSV 表头 time,type,text")
    events = [
        {
            "time": (row.get("time") or "").strip(),
            "type": (row.get("type") or "system").strip(),
            "text": (row.get("text") or "").strip(),
        }
        for row in reader
    ]
    if not events:
        raise ValueError("日志文件中没有任何事件")
    return events


def _extract_scores_and_winner(
    events: list[dict],
    score_a: float | None,
    score_b: float | None,
    winner: str | None,
) -> tuple[dict[str, float | None], str | None]:
    """比分/胜者：显式表单字段优先；缺失项按 demo 导出格式从事件文本解析。

    demo 控制器（D:\\myproject1\\demo，见 demo/docs/AGENTS.md）导出格式：
    - 正常结束（超时）：``type="system"``，文本形如
      ``游戏结束 - 守护者获胜 (守85 : 掠72)`` / ``游戏结束 - 掠夺者获胜 …``
      / ``游戏结束 - 平局 (守80 : 掠80)`` —— 胜者关键字 + 「守x : 掠y」比分。
      阵营约定（用户确认）：守护者=defender=蓝方=participant_b，
      掠夺者=attacker=红方=participant_a。
    - 顶端直胜：``type="victory"``，文本 ``进攻方顶端直胜！直接获胜`` ——
      进攻方（掠夺者/attacker）获胜，事件文本不含比分。

    返回 ({"defender": float|None, "attacker": float|None}, winner)，
    winner 为 "defender" | "attacker" | "draw" | None。
    """
    scores: dict[str, float | None] = {"defender": score_a, "attacker": score_b}
    win = winner.strip() if winner else None
    if win is not None and win not in ("defender", "attacker", "draw"):
        raise ValueError("winner 字段仅接受 defender / attacker / draw")

    # 反向扫描全部事件（不再限定 type）：优先找「游戏结束」事件。
    end_event = next(
        (ev for ev in reversed(events) if "游戏结束" in ev.get("text", "")),
        None,
    )
    if end_event is not None:
        text = end_event["text"]
        if win is None:
            m = re.search(r"(守护者获胜|掠夺者获胜|平局)", text)
            if m:
                win = _VICTORY_WINNER_MAP[m.group(1)]
        if scores["defender"] is None or scores["attacker"] is None:
            m = re.search(r"守\s*(\d+(?:\.\d+)?)\s*[:：]\s*掠\s*(\d+(?:\.\d+)?)", text)
            if m is None:
                m = re.search(r"(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)", text)
            if m:
                if scores["defender"] is None:
                    scores["defender"] = float(m.group(1))
                if scores["attacker"] is None:
                    scores["attacker"] = float(m.group(2))

    # 顶端直胜：victory 事件文本「顶端直胜/直接获胜」→ 进攻方获胜（无比分）。
    if win is None:
        vict = next(
            (ev for ev in reversed(events) if ev.get("type") == "victory"),
            None,
        )
        if vict is not None and (
            "顶端直胜" in vict.get("text", "") or "直接获胜" in vict.get("text", "")
        ):
            win = "attacker"
    return scores, win


def _apply_sync_result(match: Match, scores: dict, win: str | None) -> None:
    """sync=true：把解析出的比分/胜者预填进 match.result。

    阵营映射（用户确认）：守护者=defender=participant_b（蓝方），
    掠夺者=attacker=participant_a（红方）；页面统一标注掠夺者/守护者。

    仅做结果预填（供前端展示/人工微调），不结束对局、不触碰赛制引擎 ——
    赛程推进仍由裁判 POST /result 完成（避免绕开引擎导致淘汰晋级漂移）。
    """
    result = dict(match.result or {})
    changed = False
    # score_a 属于 participant_a（掠夺者/attacker），score_b 属于
    # participant_b（守护者/defender）。
    if scores["attacker"] is not None:
        result["score_a"] = scores["attacker"]
        changed = True
    if scores["defender"] is not None:
        result["score_b"] = scores["defender"]
        changed = True
    if win is not None:
        if win == "draw":
            result["winner"] = None
            result["is_draw"] = True
        else:
            result["winner"] = (
                match.participant_b if win == "defender" else match.participant_a
            )
            result["is_draw"] = False
        result.setdefault("score_a", 0.0)
        result.setdefault("score_b", 0.0)
        changed = True
    if changed:
        match.result = result
        if win is not None:
            match.result_type = "draw" if win == "draw" else "win"


@router.get(
    "/api/competitions/{competition_id}/matches", response_model=list[MatchOut]
)
def list_matches(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """赛程列表（任意登录用户），按轮次/创建顺序排列。"""
    _get_competition_or_404(db, competition_id)
    matches = (
        db.query(Match)
        .filter(Match.competition_id == competition_id)
        .order_by(Match.round_id, Match.id)
        .all()
    )
    return [_match_out(db, m) for m in matches]


@router.get("/api/matches/{match_id}", response_model=MatchDetailOut)
def get_match_detail(
    match_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """单局详情（任意登录用户）：对局信息 + 已导入的玩法日志。"""
    match = _get_match_or_404(db, match_id)
    return MatchDetailOut(match=_match_out(db, match))


@router.post("/api/matches/{match_id}/start")
def start_match(
    match_id: int,
    payload: MatchStartIn,
    request: Request,
    db: Session = Depends(get_db),
    staff: User = Depends(require_referee),
):
    """裁判开赛（须在本场 referee_ids 内）。轮空对局自动完结；正常对局
    置为 in_progress（不再创建玩法会话 —— 对局由裁判手工管理）。"""
    match = match_service.start_match(
        db, match_id, staff, scheduled_at=payload.scheduled_at
    )
    ip, user_agent = _request_meta(request)
    log_audit(
        db,
        staff.id,
        "match_start",
        ip,
        user_agent,
        {"match_id": match_id, "referee": staff.username},
    )
    return {"match_id": match_id, "status": match.status}


@router.post("/api/matches/{match_id}/result", response_model=MatchOut)
def record_result(
    match_id: int,
    payload: MatchResultIn,
    request: Request,
    db: Session = Depends(get_db),
    staff: User = Depends(require_referee),
):
    """裁判记分（须在本场 referee_ids 内）；单败淘汰禁平局。"""
    result = match_service.record_match_result(db, match_id, payload, staff)
    ip, user_agent = _request_meta(request)
    log_audit(
        db,
        staff.id,
        "match_result",
        ip,
        user_agent,
        {
            "match_id": match_id,
            "referee": staff.username,
            "winner": payload.winner,
            "is_draw": payload.is_draw,
        },
    )
    return _match_out(db, result)


@router.post("/api/matches/{match_id}/gameplay-log")
def import_gameplay_log(
    match_id: int,
    request: Request,
    file: UploadFile = File(...),
    score_a: float | None = Form(default=None),
    score_b: float | None = Form(default=None),
    winner: str | None = Form(default=None),
    sync: bool = Query(default=False),
    db: Session = Depends(get_db),
    staff: User = Depends(require_referee),
):
    """导入 demo 控制器导出的玩法日志（JSON/CSV，multipart 上传）。

    - 解析事件数组存入 ``match.gameplay_log``；比分/胜者可经表单字段
      ``score_a`` / ``score_b`` / ``winner`` 显式提供，缺省时从最后一条
      victory 事件文本解析（如 "积分 85:72" / "守护者获胜"），解析不到则
      留空。
    - ``?sync=true`` 时把解析出的比分/胜者预填进 ``match.result``
      （不结束对局、不触碰赛制引擎，供前端展示后人工微调再走 /result）。
    - 重新导入覆盖旧日志（幂等）。
    """
    match = _get_match_or_404(db, match_id)
    competition = _get_competition_or_404(db, match.competition_id)
    match_service._require_assigned_referee(competition, staff)

    try:
        events = _parse_gameplay_log(file.file.read())
        scores, win = _extract_scores_and_winner(events, score_a, score_b, winner)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    log_data = {
        "events": events,
        "scores": {"defender": scores["defender"], "attacker": scores["attacker"]},
        "winner": win,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    match.gameplay_log = log_data
    if sync:
        _apply_sync_result(match, scores, win)
    db.commit()
    db.refresh(match)

    ip, user_agent = _request_meta(request)
    log_audit(
        db,
        staff.id,
        "match_gameplay_log_import",
        ip,
        user_agent,
        {"match_id": match_id, "sync": sync},
    )
    return {"match_id": match_id, "gameplay_log": match.gameplay_log}


@router.get("/api/matches/{match_id}/gameplay-log")
def get_gameplay_log(
    match_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """读取已导入的玩法日志（任意登录用户；未导入返回 gameplay_log=None）。"""
    match = _get_match_or_404(db, match_id)
    return {"match_id": match_id, "gameplay_log": match.gameplay_log}
