from datetime import datetime, timezone

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Championship,
    ChampionshipStatus,
    JudgeAccessWindow,
)


def judge_has_open_access_window(user_id, now=None):
    current_time = now or datetime.now(timezone.utc)
    return db.session.execute(
        select(JudgeAccessWindow.id)
        .join(
            Championship,
            Championship.id == JudgeAccessWindow.championship_id,
        )
        .where(
            JudgeAccessWindow.judge_user_id == user_id,
            JudgeAccessWindow.starts_at <= current_time,
            JudgeAccessWindow.ends_at > current_time,
            Championship.status == ChampionshipStatus.ACTIVE,
        )
        .limit(1)
    ).scalar_one_or_none() is not None


def judge_assignment_has_open_access(assignment, now=None):
    current_time = now or datetime.now(timezone.utc)
    return db.session.execute(
        select(JudgeAccessWindow.id)
        .join(
            Championship,
            Championship.id == JudgeAccessWindow.championship_id,
        )
        .where(
            JudgeAccessWindow.judge_user_id == assignment.judge_user_id,
            JudgeAccessWindow.championship_id == assignment.championship_id,
            JudgeAccessWindow.competition_day_id
            == assignment.competition_day_id,
            JudgeAccessWindow.starts_at <= current_time,
            JudgeAccessWindow.ends_at > current_time,
            Championship.status == ChampionshipStatus.ACTIVE,
        )
        .limit(1)
    ).scalar_one_or_none() is not None


def next_judge_access_window(user_id, now=None):
    current_time = now or datetime.now(timezone.utc)
    return db.session.execute(
        select(JudgeAccessWindow)
        .join(
            Championship,
            Championship.id == JudgeAccessWindow.championship_id,
        )
        .where(
            JudgeAccessWindow.judge_user_id == user_id,
            JudgeAccessWindow.starts_at > current_time,
            Championship.status == ChampionshipStatus.ACTIVE,
        )
        .order_by(JudgeAccessWindow.starts_at)
        .limit(1)
    ).scalar_one_or_none()
