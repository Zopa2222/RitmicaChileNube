from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    AccountType,
    Bench,
    BenchActivation,
    Category,
    Championship,
    ChampionshipStatus,
    CompetitionDay,
    Gymnast,
    JudgeAccessWindow,
    JudgeAssignment,
    JudgeRole,
    ScoreEntry,
    Session,
    User,
    UserStatus,
)


class ChampionshipOperationError(ValueError):
    def __init__(self, message, code='VALIDATION_ERROR', status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def ensure_configurable_championship(championship):
    if championship.status in {
        ChampionshipStatus.CLOSED,
        ChampionshipStatus.PENDING_DELETION,
        ChampionshipStatus.DELETED,
    }:
        raise ChampionshipOperationError(
            'El campeonato ya no admite cambios de configuración',
            code='CHAMPIONSHIP_NOT_CONFIGURABLE',
            status=409,
        )


def get_competition_day(championship, day_id):
    competition_day = db.session.get(CompetitionDay, day_id)
    if (
        competition_day is None
        or competition_day.championship_id != championship.id
    ):
        raise ChampionshipOperationError(
            'Día de competencia no encontrado',
            code='COMPETITION_DAY_NOT_FOUND',
            status=404,
        )
    return competition_day


def categories_for_scope(competition_day_id, bench, session):
    return db.session.execute(
        select(Category)
        .where(
            Category.competition_day_id == competition_day_id,
            Category.bench == bench,
            Category.session == session,
            Category.deleted_at.is_(None),
        )
        .order_by(Category.passing_order, Category.id)
    ).scalars().all()


def validate_judge(judge_id):
    judge = db.session.get(User, judge_id)
    if (
        judge is None
        or judge.account_type != AccountType.JUDGE
        or judge.status != UserStatus.ACTIVE
    ):
        raise ChampionshipOperationError(
            'Juez no encontrado o no habilitado',
            code='JUDGE_NOT_AVAILABLE',
            status=404,
        )
    return judge


def _validate_assignment_slot(
    championship,
    competition_day,
    judge,
    bench,
    session,
    role,
    exclude_assignment_id=None,
):
    judge_conflict = select(JudgeAssignment.id).where(
        JudgeAssignment.championship_id == championship.id,
        JudgeAssignment.judge_user_id == judge.id,
        JudgeAssignment.competition_day_id == competition_day.id,
        JudgeAssignment.bench == bench,
        JudgeAssignment.session == session,
        JudgeAssignment.superseded_at.is_(None),
    )
    if exclude_assignment_id is not None:
        judge_conflict = judge_conflict.where(
            JudgeAssignment.id != exclude_assignment_id
        )
    if db.session.execute(judge_conflict.limit(1)).scalar_one_or_none():
        raise ChampionshipOperationError(
            'El juez ya tiene un rol vigente en esa banca y jornada',
            code='JUDGE_SCOPE_CONFLICT',
            status=409,
        )

    if role in {JudgeRole.DA, JudgeRole.DB}:
        role_count = select(func.count(JudgeAssignment.id)).where(
            JudgeAssignment.championship_id == championship.id,
            JudgeAssignment.competition_day_id == competition_day.id,
            JudgeAssignment.bench == bench,
            JudgeAssignment.session == session,
            JudgeAssignment.role == role,
            JudgeAssignment.superseded_at.is_(None),
        )
        if exclude_assignment_id is not None:
            role_count = role_count.where(
                JudgeAssignment.id != exclude_assignment_id
            )
        if db.session.execute(role_count).scalar_one() >= 4:
            raise ChampionshipOperationError(
                f'La banca y jornada ya tienen cuatro jueces {role.value}',
                code='JUDGE_ROLE_LIMIT',
                status=409,
            )


def recalculate_judge_access_window(
    judge_id,
    championship,
    competition_day,
):
    sessions = set(
        db.session.execute(
            select(JudgeAssignment.session).where(
                JudgeAssignment.judge_user_id == judge_id,
                JudgeAssignment.championship_id == championship.id,
                JudgeAssignment.competition_day_id == competition_day.id,
                JudgeAssignment.superseded_at.is_(None),
            )
        ).scalars()
    )
    access_window = db.session.execute(
        select(JudgeAccessWindow).where(
            JudgeAccessWindow.judge_user_id == judge_id,
            JudgeAccessWindow.championship_id == championship.id,
            JudgeAccessWindow.competition_day_id == competition_day.id,
        )
    ).scalar_one_or_none()

    if not sessions:
        if access_window is not None:
            db.session.delete(access_window)
        return None

    local_timezone = ZoneInfo(championship.timezone)
    starts_at = datetime.combine(
        competition_day.competition_date,
        time(hour=8),
        tzinfo=local_timezone,
    )
    duration_hours = 16 if sessions == {Session.AM, Session.PM} else 8
    ends_at = starts_at + timedelta(hours=duration_hours)

    if access_window is None:
        access_window = JudgeAccessWindow(
            judge_user_id=judge_id,
            championship_id=championship.id,
            competition_day_id=competition_day.id,
        )
        db.session.add(access_window)
    access_window.starts_at = starts_at.astimezone(timezone.utc)
    access_window.ends_at = ends_at.astimezone(timezone.utc)
    return access_window


def create_judge_assignment(
    championship,
    competition_day,
    judge,
    bench,
    session,
    role,
    assigned_by_user_id,
    effective_from_category_id=None,
):
    ensure_configurable_championship(championship)
    if championship.status != ChampionshipStatus.DRAFT:
        raise ChampionshipOperationError(
            'Las asignaciones iniciales solo se configuran en borrador; '
            'use la reasignación durante el campeonato',
            code='INITIAL_ASSIGNMENTS_DRAFT_ONLY',
            status=409,
        )
    categories = categories_for_scope(
        competition_day.id,
        bench,
        session,
    )
    if not categories:
        raise ChampionshipOperationError(
            'No existen categorías para esa banca y jornada',
            code='ASSIGNMENT_SCOPE_EMPTY',
            status=409,
        )

    categories_by_id = {category.id: category for category in categories}
    if effective_from_category_id is None:
        effective_from = categories[0]
    else:
        effective_from = categories_by_id.get(effective_from_category_id)
        if effective_from is None:
            raise ChampionshipOperationError(
                'La categoría inicial no pertenece a la banca y jornada',
                code='INVALID_EFFECTIVE_CATEGORY',
            )

    _validate_assignment_slot(
        championship,
        competition_day,
        judge,
        bench,
        session,
        role,
    )
    assignment = JudgeAssignment(
        championship_id=championship.id,
        judge_user_id=judge.id,
        competition_day_id=competition_day.id,
        bench=bench,
        session=session,
        role=role,
        effective_from_category_id=effective_from.id,
        assigned_by_user_id=assigned_by_user_id,
    )
    db.session.add(assignment)
    db.session.flush()
    initialize_score_entries_for_assignment(assignment, categories)
    recalculate_judge_access_window(
        judge.id,
        championship,
        competition_day,
    )
    return assignment


def next_category_for_reassignment(assignment):
    categories = categories_for_scope(
        assignment.competition_day_id,
        assignment.bench,
        assignment.session,
    )
    if not categories:
        return None, None

    current_activation = db.session.execute(
        select(BenchActivation).where(
            BenchActivation.championship_id == assignment.championship_id,
            BenchActivation.competition_day_id == assignment.competition_day_id,
            BenchActivation.bench == assignment.bench,
            BenchActivation.deactivated_at.is_(None),
        )
    ).scalar_one_or_none()
    if current_activation is None:
        return categories[0], None

    active_category = db.session.execute(
        select(Category)
        .join(Gymnast, Gymnast.category_id == Category.id)
        .where(Gymnast.id == current_activation.gymnast_id)
    ).scalar_one()
    if active_category.session == assignment.session:
        for index, category in enumerate(categories):
            if category.id == active_category.id:
                return (
                    categories[index + 1]
                    if index + 1 < len(categories)
                    else None,
                    category,
                )
    if (
        active_category.session == Session.AM
        and assignment.session == Session.PM
    ):
        return categories[0], None
    return None, categories[-1]


def reassign_judge(
    assignment,
    championship,
    competition_day,
    new_judge,
    assigned_by_user_id,
):
    ensure_configurable_championship(championship)
    if assignment.superseded_at is not None:
        raise ChampionshipOperationError(
            'La asignación ya fue reemplazada',
            code='ASSIGNMENT_ALREADY_SUPERSEDED',
            status=409,
        )
    if new_judge.id == assignment.judge_user_id:
        raise ChampionshipOperationError(
            'Seleccione un juez distinto para la reasignación',
            code='SAME_JUDGE_REASSIGNMENT',
            status=409,
        )

    effective_from, previous_category = next_category_for_reassignment(
        assignment
    )
    if effective_from is None:
        raise ChampionshipOperationError(
            'No existe una categoría siguiente para iniciar la reasignación',
            code='NO_NEXT_CATEGORY',
            status=409,
        )
    _validate_assignment_slot(
        championship,
        competition_day,
        new_judge,
        assignment.bench,
        assignment.session,
        assignment.role,
        exclude_assignment_id=assignment.id,
    )

    now = datetime.now(timezone.utc)
    assignment.superseded_at = now
    assignment.effective_to_category_id = (
        previous_category.id if previous_category else None
    )
    db.session.flush()

    new_assignment = JudgeAssignment(
        championship_id=championship.id,
        judge_user_id=new_judge.id,
        competition_day_id=competition_day.id,
        bench=assignment.bench,
        session=assignment.session,
        role=assignment.role,
        effective_from_category_id=effective_from.id,
        assigned_by_user_id=assigned_by_user_id,
    )
    db.session.add(new_assignment)
    db.session.flush()
    initialize_score_entries_for_assignment(
        new_assignment,
        categories_for_scope(
            competition_day.id,
            new_assignment.bench,
            new_assignment.session,
        ),
    )
    db.session.flush()
    if new_assignment.role not in {JudgeRole.L, JudgeRole.P}:
        from app.services.cloud_scoring_service import (
            refresh_role_resolution,
            refresh_score_summary,
        )

        affected_gymnast_ids = db.session.execute(
            select(ScoreEntry.gymnast_id).where(
                ScoreEntry.judge_assignment_id == new_assignment.id
            )
        ).scalars().all()
        for gymnast_id in affected_gymnast_ids:
            if new_assignment.role in {JudgeRole.DA, JudgeRole.DB}:
                refresh_role_resolution(
                    gymnast_id,
                    new_assignment.role,
                )
            refresh_score_summary(gymnast_id)
    recalculate_judge_access_window(
        assignment.judge_user_id,
        championship,
        competition_day,
    )
    recalculate_judge_access_window(
        new_judge.id,
        championship,
        competition_day,
    )
    return new_assignment, effective_from


def initialize_score_entries_for_assignment(assignment, scope_categories):
    if assignment.role in {JudgeRole.L, JudgeRole.P}:
        return
    order_by_id = {
        category.id: category.passing_order
        for category in scope_categories
    }
    start_order = order_by_id.get(assignment.effective_from_category_id)
    end_order = order_by_id.get(assignment.effective_to_category_id)
    if start_order is None:
        return
    eligible_category_ids = [
        category.id
        for category in scope_categories
        if category.passing_order >= start_order
        and (end_order is None or category.passing_order <= end_order)
    ]
    if not eligible_category_ids:
        return
    gymnasts = db.session.execute(
        select(Gymnast).where(
            Gymnast.category_id.in_(eligible_category_ids),
            Gymnast.deleted_at.is_(None),
        )
    ).scalars().all()
    existing_gymnast_ids = set(
        db.session.execute(
            select(ScoreEntry.gymnast_id).where(
                ScoreEntry.judge_assignment_id == assignment.id,
                ScoreEntry.gymnast_id.in_(
                    [gymnast.id for gymnast in gymnasts]
                ),
            )
        ).scalars()
    ) if gymnasts else set()
    for gymnast in gymnasts:
        if gymnast.id not in existing_gymnast_ids:
            db.session.add(
                ScoreEntry(
                    gymnast_id=gymnast.id,
                    judge_assignment_id=assignment.id,
                )
            )


def assignments_effective_for_category(
    category,
    include_superseded=False,
):
    query = select(JudgeAssignment).where(
        JudgeAssignment.championship_id == category.championship_id,
        JudgeAssignment.competition_day_id == category.competition_day_id,
        JudgeAssignment.bench == category.bench,
        JudgeAssignment.session == category.session,
    )
    if not include_superseded:
        query = query.where(JudgeAssignment.superseded_at.is_(None))
    assignments = db.session.execute(query).scalars().all()
    if not assignments:
        return []

    scope_categories = categories_for_scope(
        category.competition_day_id,
        category.bench,
        category.session,
    )
    order_by_id = {
        scope_category.id: scope_category.passing_order
        for scope_category in scope_categories
    }
    effective = []
    for assignment in assignments:
        if (
            assignment.superseded_at is not None
            and assignment.effective_to_category_id is None
        ):
            continue
        start_order = order_by_id.get(assignment.effective_from_category_id)
        end_order = order_by_id.get(assignment.effective_to_category_id)
        if start_order is None or category.passing_order < start_order:
            continue
        if end_order is not None and category.passing_order > end_order:
            continue
        effective.append(assignment)
    return effective


def activate_gymnast(
    championship,
    competition_day,
    bench,
    gymnast,
    activated_by_user_id,
):
    if championship.status != ChampionshipStatus.ACTIVE:
        raise ChampionshipOperationError(
            'El campeonato debe estar activo para seleccionar gimnastas',
            code='CHAMPIONSHIP_NOT_ACTIVE',
            status=409,
        )
    category = db.session.execute(
        select(Category).where(Category.id == gymnast.category_id)
    ).scalar_one()
    if (
        category.championship_id != championship.id
        or category.competition_day_id != competition_day.id
        or category.bench != bench
        or category.deleted_at is not None
        or gymnast.deleted_at is not None
    ):
        raise ChampionshipOperationError(
            'La gimnasta no pertenece a la banca y día seleccionados',
            code='GYMNAST_SCOPE_MISMATCH',
        )

    current_activation = db.session.execute(
        select(BenchActivation)
        .where(
            BenchActivation.championship_id == championship.id,
            BenchActivation.competition_day_id == competition_day.id,
            BenchActivation.bench == bench,
            BenchActivation.deactivated_at.is_(None),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if (
        current_activation is not None
        and current_activation.gymnast_id == gymnast.id
    ):
        return current_activation, False, category

    now = datetime.now(timezone.utc)
    if current_activation is not None:
        current_activation.deactivated_at = now
        db.session.flush()

    activation = BenchActivation(
        championship_id=championship.id,
        competition_day_id=competition_day.id,
        bench=bench,
        gymnast_id=gymnast.id,
        activated_by_user_id=activated_by_user_id,
        activated_at=now,
    )
    db.session.add(activation)
    db.session.flush()

    for assignment in assignments_effective_for_category(category):
        if assignment.role in {JudgeRole.L, JudgeRole.P}:
            continue
        score_entry = db.session.execute(
            select(ScoreEntry).where(
                ScoreEntry.gymnast_id == gymnast.id,
                ScoreEntry.judge_assignment_id == assignment.id,
            )
        ).scalar_one_or_none()
        if score_entry is None:
            score_entry = ScoreEntry(
                gymnast_id=gymnast.id,
                judge_assignment_id=assignment.id,
            )
            db.session.add(score_entry)
        score_entry.activation_id = activation.id

    return activation, True, category
