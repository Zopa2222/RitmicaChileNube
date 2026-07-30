from datetime import datetime, timezone

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    BenchActivation,
    Gymnast,
    JudgeRole,
    ScoreEntry,
)
from app.services.championship_operations_service import (
    assignments_effective_for_category,
)
from app.services.cloud_scoring_service import refresh_score_summary


SCORING_ROLES = {
    JudgeRole.DA,
    JudgeRole.DB,
    JudgeRole.A,
    JudgeRole.E,
}


class GymnastManagementError(ValueError):
    def __init__(self, message, code='GYMNAST_VALIDATION_ERROR', status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def active_gymnasts_for_update(category_id):
    return db.session.execute(
        select(Gymnast)
        .where(
            Gymnast.category_id == category_id,
            Gymnast.deleted_at.is_(None),
        )
        .order_by(Gymnast.passing_order, Gymnast.id)
        .with_for_update(of=Gymnast)
    ).scalars().all()


def resequence_gymnasts(gymnasts):
    """Assign contiguous order values without colliding during swaps."""
    if not gymnasts:
        return

    category_id = gymnasts[0].category_id
    if any(gymnast.category_id != category_id for gymnast in gymnasts):
        raise GymnastManagementError(
            'Todas las gimnastas deben pertenecer a la misma categoría'
        )

    maximum_order = db.session.scalar(
        select(func.max(Gymnast.passing_order)).where(
            Gymnast.category_id == category_id
        )
    )
    temporary_base = (maximum_order or 0) + len(gymnasts) + 1
    for index, gymnast in enumerate(gymnasts):
        gymnast.passing_order = temporary_base + index
    db.session.flush()

    for index, gymnast in enumerate(gymnasts):
        gymnast.passing_order = index
    db.session.flush()


def create_gymnast(category, full_name, club_name, position=None):
    gymnasts = active_gymnasts_for_update(category.id)
    if position is None:
        position = len(gymnasts)
    if isinstance(position, bool) or not isinstance(position, int):
        raise GymnastManagementError(
            'La posición debe ser un número entero',
            code='INVALID_PASSING_ORDER',
        )
    if position < 0 or position > len(gymnasts):
        raise GymnastManagementError(
            'La posición está fuera del orden de la categoría',
            code='INVALID_PASSING_ORDER',
        )

    gymnast = Gymnast(
        category_id=category.id,
        full_name=full_name,
        club_name=club_name,
        passing_order=(
            max(
                candidate.passing_order
                for candidate in gymnasts
            ) + 1
            if gymnasts else 0
        ),
    )
    db.session.add(gymnast)
    db.session.flush()

    ordered = [*gymnasts]
    ordered.insert(position, gymnast)
    resequence_gymnasts(ordered)

    initialized_scores = 0
    for assignment in assignments_effective_for_category(
        category,
        include_superseded=True,
    ):
        if assignment.role not in SCORING_ROLES:
            continue
        db.session.add(
            ScoreEntry(
                gymnast_id=gymnast.id,
                judge_assignment_id=assignment.id,
            )
        )
        initialized_scores += 1
    db.session.flush()
    refresh_score_summary(gymnast.id)
    return gymnast, initialized_scores


def delete_gymnast(championship, gymnast, deleted_by_user_id):
    gymnasts = active_gymnasts_for_update(gymnast.category_id)
    locked_gymnast = next(
        (
            candidate
            for candidate in gymnasts
            if candidate.id == gymnast.id
        ),
        None,
    )
    if locked_gymnast is None:
        raise GymnastManagementError(
            'Gimnasta no encontrada',
            code='GYMNAST_NOT_FOUND',
            status=404,
        )

    timestamp = datetime.now(timezone.utc)
    activation = db.session.execute(
        select(BenchActivation)
        .where(
            BenchActivation.championship_id == championship.id,
            BenchActivation.gymnast_id == locked_gymnast.id,
            BenchActivation.deactivated_at.is_(None),
        )
        .with_for_update(of=BenchActivation)
    ).scalar_one_or_none()
    if activation is not None:
        activation.deactivated_at = timestamp

    previous_order = locked_gymnast.passing_order
    locked_gymnast.deleted_at = timestamp
    locked_gymnast.deleted_by_user_id = deleted_by_user_id
    db.session.flush()
    resequence_gymnasts([
        candidate
        for candidate in gymnasts
        if candidate.id != locked_gymnast.id
    ])
    return locked_gymnast, activation, previous_order


def reorder_gymnasts(category, gymnast_ids):
    gymnasts = active_gymnasts_for_update(category.id)
    current_ids = [gymnast.id for gymnast in gymnasts]
    if (
        len(gymnast_ids) != len(set(gymnast_ids))
        or set(gymnast_ids) != set(current_ids)
    ):
        raise GymnastManagementError(
            'Debe enviar exactamente todas las gimnastas activas '
            'de la categoría, sin duplicados',
            code='GYMNAST_ORDER_MISMATCH',
        )

    by_id = {gymnast.id: gymnast for gymnast in gymnasts}
    ordered = [by_id[gymnast_id] for gymnast_id in gymnast_ids]
    changed = current_ids != gymnast_ids
    if changed:
        resequence_gymnasts(ordered)
    return ordered, changed


def order_gymnasts_by_score(category):
    gymnasts = active_gymnasts_for_update(category.id)
    current_ids = [gymnast.id for gymnast in gymnasts]
    summaries = {
        gymnast.id: refresh_score_summary(gymnast.id)
        for gymnast in gymnasts
    }
    ordered = sorted(
        gymnasts,
        key=lambda gymnast: (
            -summaries[gymnast.id].total_score,
            -summaries[gymnast.id].e_score,
            -summaries[gymnast.id].a_score,
            gymnast.passing_order,
            str(gymnast.id),
        ),
    )
    changed = current_ids != [gymnast.id for gymnast in ordered]
    if changed:
        resequence_gymnasts(ordered)
    return ordered, summaries, changed
