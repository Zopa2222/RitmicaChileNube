import hashlib
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy import select

from app.extensions import db
from app.models import (
    BenchActivation,
    CalculationStatus,
    Category,
    Gymnast,
    JudgeAssignment,
    JudgeRole,
    ResolutionSource,
    RoleScoreResolution,
    ScoreEntry,
    ScoreSummary,
    SubmissionStatus,
)
from app.services.championship_operations_service import (
    assignments_effective_for_category,
)


SCORE_MIN = Decimal('0.00')
SCORE_MAX = Decimal('20.00')
AREA_BASE = Decimal('10.00')
TWO_DECIMALS = Decimal('0.01')


class ScoreValidationError(ValueError):
    pass


class ScoreSubmissionError(ValueError):
    def __init__(self, message, code='SCORE_SUBMISSION_REJECTED', status=409):
        super().__init__(message)
        self.code = code
        self.status = status


def parse_score_value(raw_value):
    """Parse a score exactly, accepting comma or point as decimal separator."""
    if isinstance(raw_value, bool) or raw_value is None:
        raise ScoreValidationError('La nota debe ser un número entre 0 y 20')

    normalized = (
        str(raw_value).strip().replace(',', '.')
        if isinstance(raw_value, str)
        else str(raw_value)
    )

    try:
        value = Decimal(normalized)
    except (InvalidOperation, ValueError):
        raise ScoreValidationError(
            'La nota debe ser un número entre 0 y 20'
        ) from None

    if not value.is_finite():
        raise ScoreValidationError('La nota debe ser un número finito')

    quantized = value.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)
    if value != quantized:
        raise ScoreValidationError('La nota admite como máximo dos decimales')
    if quantized < SCORE_MIN or quantized > SCORE_MAX:
        raise ScoreValidationError('La nota debe estar entre 0 y 20')

    return quantized


def calculate_area_score(values):
    """Calculate an A/E score from deductions, including pending zero values."""
    scores = [parse_score_value(value) for value in values]
    if not scores:
        return Decimal('0.00')

    if len(scores) == 1:
        deduction = scores[0]
    elif len(scores) in (2, 3):
        deduction = sum(scores, Decimal('0.00')) / Decimal(len(scores))
    else:
        ordered = sorted(scores)
        middle = ordered[1:-1]
        deduction = sum(middle, Decimal('0.00')) / Decimal(len(middle))

    return (AREA_BASE - deduction).quantize(
        TWO_DECIMALS,
        rounding=ROUND_HALF_UP,
    )


def calculate_total_score(da, db_score, a_values, e_values, discount):
    """Calculate the authoritative total with exact decimal arithmetic."""
    total = (
        parse_score_value(da)
        + parse_score_value(db_score)
        + calculate_area_score(a_values)
        + calculate_area_score(e_values)
        - parse_score_value(discount)
    )
    return max(Decimal('0.00'), total).quantize(
        TWO_DECIMALS,
        rounding=ROUND_HALF_UP,
    )


def has_area_difference(values):
    """Apply the canonical >0.6 warning rule used by A and E."""
    scores = sorted(parse_score_value(value) for value in values)
    if len(scores) < 2:
        return False

    threshold = Decimal('0.60')
    if len(scores) == 2:
        return scores[1] - scores[0] > threshold
    if len(scores) == 3:
        return any(
            right - left > threshold
            for left, right in zip(scores, scores[1:])
        )

    middle = scores[1:-1]
    return middle[-1] - middle[0] > threshold


def effective_assignment_ids_for_gymnast(gymnast_id):
    """Return the historical/current assignments that own this category."""
    category = db.session.execute(
        select(Category)
        .join(Gymnast, Gymnast.category_id == Category.id)
        .where(Gymnast.id == gymnast_id)
    ).scalar_one_or_none()
    if category is None:
        return set()
    return {
        assignment.id
        for assignment in assignments_effective_for_category(
            category,
            include_superseded=True,
        )
    }


def ensure_score_entry_is_effective(score_entry):
    if (
        score_entry.judge_assignment_id
        not in effective_assignment_ids_for_gymnast(score_entry.gymnast_id)
    ):
        raise ScoreSubmissionError(
            'La nota ya no corresponde a la asignación vigente '
            'para esta categoría',
            code='ASSIGNMENT_NOT_EFFECTIVE',
        )


def submit_judge_score(
    score_entry,
    raw_value,
    judge_user_id,
    activation_id,
    submitted_at=None,
):
    """Submit one judge-owned score only for the currently active routine."""
    assignment = score_entry.assignment
    if assignment.judge_user_id != judge_user_id:
        raise ScoreSubmissionError(
            'El juez solo puede modificar su propia nota',
            code='SCORE_ENTRY_NOT_FOUND',
            status=404,
        )
    if assignment.role in (JudgeRole.L, JudgeRole.P):
        raise ScoreSubmissionError(
            'El rol asignado no registra puntaje',
            code='NON_SCORING_ROLE',
        )
    if assignment.superseded_at is not None:
        raise ScoreSubmissionError(
            'La asignación ya no está vigente',
            code='ASSIGNMENT_SUPERSEDED',
        )
    ensure_score_entry_is_effective(score_entry)

    activation = db.session.execute(
        select(BenchActivation)
        .where(BenchActivation.id == activation_id)
        .with_for_update()
    ).scalar_one_or_none()
    if activation is None or activation.deactivated_at is not None:
        raise ScoreSubmissionError(
            'La activación de la gimnasta ya no está vigente',
            code='STALE_ACTIVATION',
        )
    if activation.gymnast_id != score_entry.gymnast_id:
        raise ScoreSubmissionError(
            'La activación no corresponde a la gimnasta',
            code='ACTIVATION_SCOPE_MISMATCH',
        )
    if (
        activation.championship_id != assignment.championship_id
        or activation.competition_day_id != assignment.competition_day_id
        or activation.bench != assignment.bench
    ):
        raise ScoreSubmissionError(
            'La activación no corresponde a la asignación',
            code='ACTIVATION_SCOPE_MISMATCH',
        )

    timestamp = submitted_at or datetime.now(timezone.utc)
    parsed_value = parse_score_value(raw_value)
    if (
        score_entry.value == parsed_value
        and score_entry.submission_status == SubmissionStatus.SUBMITTED
        and score_entry.activation_id == activation.id
    ):
        return score_entry, False

    score_entry.value = parsed_value
    score_entry.submission_status = SubmissionStatus.SUBMITTED
    score_entry.submitted_at = timestamp
    score_entry.activation_id = activation.id
    score_entry.last_modified_by_user_id = judge_user_id
    db.session.flush()

    if assignment.role in (JudgeRole.DA, JudgeRole.DB):
        refresh_role_resolution(score_entry.gymnast_id, assignment.role)

    refresh_score_summary(score_entry.gymnast_id, timestamp)
    return score_entry, True


def submit_administrator_score(
    score_entry,
    raw_value,
    administrator_user_id,
    submitted_at=None,
):
    """Submit or correct any scoring entry without requiring an activation."""
    assignment = score_entry.assignment
    if assignment.role in (JudgeRole.L, JudgeRole.P):
        raise ScoreSubmissionError(
            'El rol asignado no registra puntaje',
            code='NON_SCORING_ROLE',
        )
    ensure_score_entry_is_effective(score_entry)

    parsed_value = parse_score_value(raw_value)
    if (
        score_entry.value == parsed_value
        and score_entry.submission_status == SubmissionStatus.SUBMITTED
    ):
        return score_entry, False

    timestamp = submitted_at or datetime.now(timezone.utc)
    score_entry.value = parsed_value
    score_entry.submission_status = SubmissionStatus.SUBMITTED
    score_entry.submitted_at = timestamp
    score_entry.last_modified_by_user_id = administrator_user_id
    db.session.flush()

    if assignment.role in (JudgeRole.DA, JudgeRole.DB):
        refresh_role_resolution(score_entry.gymnast_id, assignment.role)
    refresh_score_summary(score_entry.gymnast_id, timestamp)
    return score_entry, True


def refresh_score_summary(gymnast_id, calculated_at=None):
    """Recalculate the authoritative provisional or complete score summary."""
    effective_assignment_ids = effective_assignment_ids_for_gymnast(
        gymnast_id
    )
    rows = db.session.execute(
        select(ScoreEntry, JudgeAssignment.role)
        .join(
            JudgeAssignment,
            JudgeAssignment.id == ScoreEntry.judge_assignment_id,
        )
        .where(
            ScoreEntry.gymnast_id == gymnast_id,
            JudgeAssignment.id.in_(effective_assignment_ids),
            JudgeAssignment.role.in_(
                (
                    JudgeRole.DA,
                    JudgeRole.DB,
                    JudgeRole.A,
                    JudgeRole.E,
                )
            ),
        )
    ).all()

    values_by_role = {
        JudgeRole.DA: [],
        JudgeRole.DB: [],
        JudgeRole.A: [],
        JudgeRole.E: [],
    }
    all_submitted = bool(rows)
    for score_entry, role in rows:
        if role not in values_by_role:
            continue
        values_by_role[role].append(score_entry.value)
        if score_entry.submission_status != SubmissionStatus.SUBMITTED:
            all_submitted = False

    summary = db.session.get(ScoreSummary, gymnast_id)
    if summary is None:
        summary = ScoreSummary(
            gymnast_id=gymnast_id,
            discount=Decimal('0.00'),
        )
        db.session.add(summary)

    da_resolution = db.session.get(
        RoleScoreResolution,
        (gymnast_id, JudgeRole.DA),
    )
    db_resolution = db.session.get(
        RoleScoreResolution,
        (gymnast_id, JudgeRole.DB),
    )
    summary.da_score = (
        da_resolution.effective_value
        if da_resolution else Decimal('0.00')
    )
    summary.db_score = (
        db_resolution.effective_value
        if db_resolution else Decimal('0.00')
    )
    summary.a_score = calculate_area_score(values_by_role[JudgeRole.A])
    summary.e_score = calculate_area_score(values_by_role[JudgeRole.E])
    summary.total_score = calculate_total_score(
        summary.da_score,
        summary.db_score,
        values_by_role[JudgeRole.A],
        values_by_role[JudgeRole.E],
        summary.discount,
    )
    summary.calculation_status = (
        CalculationStatus.COMPLETE
        if all_submitted
        else CalculationStatus.PROVISIONAL
    )
    summary.calculated_at = calculated_at or datetime.now(timezone.utc)
    db.session.flush()
    return summary


def refresh_role_resolution(gymnast_id, role):
    """Refresh the effective DA/DB value and discrepancy revision."""
    if role not in (JudgeRole.DA, JudgeRole.DB):
        raise ScoreSubmissionError('Solo DA y DB usan resolución compartida')

    effective_assignment_ids = effective_assignment_ids_for_gymnast(
        gymnast_id
    )
    rows = db.session.execute(
        select(
            ScoreEntry.id,
            ScoreEntry.value,
            ScoreEntry.submitted_at,
        )
        .join(
            JudgeAssignment,
            JudgeAssignment.id == ScoreEntry.judge_assignment_id,
        )
        .where(
            ScoreEntry.gymnast_id == gymnast_id,
            ScoreEntry.submission_status == SubmissionStatus.SUBMITTED,
            JudgeAssignment.id.in_(effective_assignment_ids),
            JudgeAssignment.role == role,
        )
        .order_by(ScoreEntry.submitted_at.asc(), ScoreEntry.id.asc())
    ).all()

    resolution = db.session.get(RoleScoreResolution, (gymnast_id, role))
    if resolution is None:
        resolution = RoleScoreResolution(gymnast_id=gymnast_id, role=role)
        db.session.add(resolution)

    if not rows:
        resolution.effective_value = Decimal('0.00')
        resolution.first_received_value = None
        resolution.first_received_at = None
        resolution.source = ResolutionSource.AUTO
        resolution.has_discrepancy = False
        resolution.discrepancy_revision = 0
        resolution.acknowledged_revision = 0
        resolution.values_fingerprint = None
        resolution.acknowledged_at = None
        resolution.acknowledged_by_user_id = None
        db.session.flush()
        return resolution

    if resolution.first_received_value is None:
        resolution.first_received_value = rows[0].value
        resolution.first_received_at = rows[0].submitted_at
        resolution.effective_value = rows[0].value

    fingerprint_source = '|'.join(
        f'{entry_id}:{Decimal(value):.2f}' for entry_id, value, _ in rows
    )
    fingerprint = hashlib.sha256(
        fingerprint_source.encode('utf-8')
    ).hexdigest()
    unique_values = {Decimal(value) for _, value, _ in rows}
    has_discrepancy = len(unique_values) > 1

    if has_discrepancy and fingerprint != resolution.values_fingerprint:
        resolution.discrepancy_revision += 1

    resolution.values_fingerprint = fingerprint
    resolution.has_discrepancy = has_discrepancy

    if has_discrepancy:
        if resolution.source == ResolutionSource.AUTO:
            resolution.effective_value = resolution.first_received_value
    else:
        resolution.effective_value = rows[0].value
        resolution.source = ResolutionSource.AUTO
        resolution.acknowledged_at = None
        resolution.acknowledged_by_user_id = None

    db.session.flush()
    return resolution


def acknowledge_role_resolution(
    resolution,
    administrator_user_id,
    raw_value=None,
    acknowledged_at=None,
):
    """Acknowledge a DA/DB discrepancy, optionally fixing another value."""
    if raw_value is not None:
        resolution.effective_value = parse_score_value(raw_value)
    resolution.source = ResolutionSource.ADMIN
    resolution.acknowledged_revision = resolution.discrepancy_revision
    resolution.acknowledged_by_user_id = administrator_user_id
    resolution.acknowledged_at = acknowledged_at or datetime.now(timezone.utc)
    db.session.flush()
    refresh_score_summary(
        resolution.gymnast_id,
        resolution.acknowledged_at,
    )
    return resolution
