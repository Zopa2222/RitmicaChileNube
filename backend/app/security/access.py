from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Championship,
    ChampionshipStatus,
    JudgeAccessWindow,
    JudgeAssignment,
    CompetitionDay,
    Session,
)


def judge_has_championship_access(user_id, now=None):
    """Whether a judge may use the cabin while a championship is operating.

    A current assignment grants access only during its local shift,
    including pauses. Manual account disabling is checked by authentication.
    """
    current_time = now or datetime.now(timezone.utc)
    assignments = db.session.execute(
        select(JudgeAssignment, Championship, CompetitionDay)
        .join(
            Championship,
            Championship.id == JudgeAssignment.championship_id,
        )
        .join(CompetitionDay, CompetitionDay.id == JudgeAssignment.competition_day_id)
        .where(
            JudgeAssignment.judge_user_id == user_id,
            JudgeAssignment.superseded_at.is_(None),
            Championship.status.in_([
                ChampionshipStatus.ACTIVE,
                ChampionshipStatus.PAUSED,
            ]),
        )
    ).all()
    for assignment, championship, day in assignments:
        start = datetime.combine(
            day.competition_date,
            time(hour=8 if assignment.session == Session.AM else 12),
            tzinfo=ZoneInfo(championship.timezone),
        )
        duration = 8 if assignment.session == Session.AM else 12
        if start <= current_time < start + timedelta(hours=duration):
            return True
    return False


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
