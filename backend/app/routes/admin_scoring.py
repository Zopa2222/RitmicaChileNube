import uuid
from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AccountType,
    AuditLog,
    BenchActivation,
    CalculationStatus,
    Category,
    Championship,
    ChampionshipStatus,
    CompetitionDay,
    Gymnast,
    JudgeAssignment,
    JudgeRole,
    ResolutionSource,
    RoleScoreResolution,
    ScoreEntry,
    ScoreSummary,
    SubmissionStatus,
    User,
)
from app.routes.cloud_championships import (
    get_championship_or_404,
    validation_error,
)
from app.security.permissions import account_types_required
from app.services.championship_operations_service import (
    assignments_effective_for_category,
)
from app.services.cloud_scoring_service import (
    ScoreSubmissionError,
    ScoreValidationError,
    acknowledge_role_resolution,
    calculate_area_score,
    calculate_total_score,
    has_area_difference,
    parse_score_value,
    refresh_score_summary,
    submit_administrator_score,
)
from app.services.gymnast_management_service import (
    GymnastManagementError,
    create_gymnast,
    delete_gymnast,
    order_gymnasts_by_score,
    reorder_gymnasts,
)


bp = Blueprint('admin_scoring', __name__, url_prefix='/api/v1/championships')
ADMIN_ACCOUNT_TYPES = (
    AccountType.SUPER_ADMIN,
    AccountType.GLOBAL_ADMIN,
)
ROLE_ORDER = {
    JudgeRole.DA: 0,
    JudgeRole.DB: 1,
    JudgeRole.A: 2,
    JudgeRole.E: 3,
    JudgeRole.L: 4,
    JudgeRole.P: 5,
}


def parse_uuid_value(raw_value, field_name):
    try:
        return uuid.UUID(str(raw_value))
    except (TypeError, ValueError, AttributeError):
        raise ScoreSubmissionError(
            f'{field_name} no es válido',
            code='INVALID_IDENTIFIER',
            status=400,
        ) from None


def decimal_response(value):
    return format(Decimal(value), '.2f')


def score_response(score_entry):
    return {
        'id': str(score_entry.id),
        'assignment_id': str(score_entry.judge_assignment_id),
        'role': score_entry.assignment.role.value,
        'value': decimal_response(score_entry.value),
        'submission_status': score_entry.submission_status.value,
        'submitted_at': (
            score_entry.submitted_at.isoformat()
            if score_entry.submitted_at else None
        ),
        'last_modified_by_user_id': (
            str(score_entry.last_modified_by_user_id)
            if score_entry.last_modified_by_user_id else None
        ),
    }


def summary_response(summary):
    return {
        'da_score': decimal_response(summary['da_score']),
        'db_score': decimal_response(summary['db_score']),
        'a_score': decimal_response(summary['a_score']),
        'e_score': decimal_response(summary['e_score']),
        'discount': decimal_response(summary['discount']),
        'total_score': decimal_response(summary['total_score']),
        'calculation_status': summary['calculation_status'].value,
        'calculated_at': (
            summary['calculated_at'].isoformat()
            if summary['calculated_at'] else None
        ),
    }


def persisted_summary_values(summary):
    return {
        'da_score': summary.da_score,
        'db_score': summary.db_score,
        'a_score': summary.a_score,
        'e_score': summary.e_score,
        'discount': summary.discount,
        'total_score': summary.total_score,
        'calculation_status': summary.calculation_status,
        'calculated_at': summary.calculated_at,
    }


def calculated_summary_values(score_entries, resolutions):
    values_by_role = {
        JudgeRole.A: [],
        JudgeRole.E: [],
    }
    all_submitted = bool(score_entries)
    for score_entry in score_entries:
        role = score_entry.assignment.role
        if role in values_by_role:
            values_by_role[role].append(score_entry.value)
        if score_entry.submission_status != SubmissionStatus.SUBMITTED:
            all_submitted = False

    da_resolution = resolutions.get(JudgeRole.DA)
    db_resolution = resolutions.get(JudgeRole.DB)
    da_score = (
        da_resolution.effective_value
        if da_resolution else Decimal('0.00')
    )
    db_score = (
        db_resolution.effective_value
        if db_resolution else Decimal('0.00')
    )
    discount = Decimal('0.00')
    return {
        'da_score': da_score,
        'db_score': db_score,
        'a_score': calculate_area_score(values_by_role[JudgeRole.A]),
        'e_score': calculate_area_score(values_by_role[JudgeRole.E]),
        'discount': discount,
        'total_score': calculate_total_score(
            da_score,
            db_score,
            values_by_role[JudgeRole.A],
            values_by_role[JudgeRole.E],
            discount,
        ),
        'calculation_status': (
            CalculationStatus.COMPLETE
            if all_submitted else CalculationStatus.PROVISIONAL
        ),
        'calculated_at': None,
    }


def resolution_response(role, resolution):
    if resolution is None:
        return {
            'role': role.value,
            'effective_value': '0.00',
            'first_received_value': None,
            'source': ResolutionSource.AUTO.value,
            'has_discrepancy': False,
            'warning_active': False,
            'discrepancy_revision': 0,
            'acknowledged_revision': 0,
        }
    return {
        'role': role.value,
        'effective_value': decimal_response(resolution.effective_value),
        'first_received_value': (
            decimal_response(resolution.first_received_value)
            if resolution.first_received_value is not None else None
        ),
        'source': resolution.source.value,
        'has_discrepancy': resolution.has_discrepancy,
        'warning_active': resolution.warning_active,
        'discrepancy_revision': resolution.discrepancy_revision,
        'acknowledged_revision': resolution.acknowledged_revision,
    }


def get_category(championship, category_id):
    parsed_id = parse_uuid_value(category_id, 'category_id')
    category = db.session.get(Category, parsed_id)
    if (
        category is None
        or category.championship_id != championship.id
        or category.deleted_at is not None
    ):
        raise ScoreSubmissionError(
            'Categoría no encontrada',
            code='CATEGORY_NOT_FOUND',
            status=404,
        )
    return category


def get_gymnast(championship, gymnast_id):
    parsed_id = parse_uuid_value(gymnast_id, 'gymnast_id')
    gymnast = db.session.get(Gymnast, parsed_id)
    category = (
        db.session.get(Category, gymnast.category_id)
        if gymnast else None
    )
    if (
        gymnast is None
        or category is None
        or category.championship_id != championship.id
        or category.deleted_at is not None
        or gymnast.deleted_at is not None
    ):
        raise ScoreSubmissionError(
            'Gimnasta no encontrada',
            code='GYMNAST_NOT_FOUND',
            status=404,
        )
    return gymnast, category


def ensure_scores_editable(championship):
    if championship.status not in {
        ChampionshipStatus.ACTIVE,
        ChampionshipStatus.PAUSED,
    }:
        raise ScoreSubmissionError(
            'Las notas solo se modifican en un campeonato activo o pausado',
            code='CHAMPIONSHIP_SCORES_READ_ONLY',
            status=409,
        )


def ensure_gymnasts_editable(championship):
    if championship.status not in {
        ChampionshipStatus.DRAFT,
        ChampionshipStatus.ACTIVE,
        ChampionshipStatus.PAUSED,
    }:
        raise GymnastManagementError(
            'Las gimnastas no se modifican en un campeonato cerrado '
            'o eliminado',
            code='CHAMPIONSHIP_GYMNASTS_READ_ONLY',
            status=409,
        )


def lock_championship(championship):
    return db.session.execute(
        select(Championship)
        .where(Championship.id == championship.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).scalar_one()


def lock_category(category):
    return db.session.execute(
        select(Category)
        .where(Category.id == category.id)
        .execution_options(populate_existing=True)
        .with_for_update(of=Category)
    ).scalar_one()


def validated_gymnast_fields(payload):
    full_name = payload.get('full_name')
    if not isinstance(full_name, str) or not full_name.strip():
        raise GymnastManagementError(
            'El nombre de la gimnasta es obligatorio',
            code='INVALID_GYMNAST_NAME',
        )
    full_name = full_name.strip()
    if len(full_name) > 180:
        raise GymnastManagementError(
            'El nombre de la gimnasta admite hasta 180 caracteres',
            code='INVALID_GYMNAST_NAME',
        )

    club_name = payload.get('club_name', '')
    if club_name is None:
        club_name = ''
    if not isinstance(club_name, str):
        raise GymnastManagementError(
            'El club debe ser texto',
            code='INVALID_CLUB_NAME',
        )
    club_name = club_name.strip()
    if len(club_name) > 180:
        raise GymnastManagementError(
            'El club admite hasta 180 caracteres',
            code='INVALID_CLUB_NAME',
        )
    return full_name, club_name


def gymnast_order_response(gymnast):
    return {
        'id': str(gymnast.id),
        'full_name': gymnast.full_name,
        'club_name': gymnast.club_name,
        'passing_order': gymnast.passing_order,
    }


def add_gymnast_audit(
    current_user,
    action,
    championship,
    gymnast,
    details,
):
    db.session.add(
        AuditLog(
            actor_user_id=current_user.id,
            action=action,
            championship_id=championship.id,
            entity_type='GYMNAST',
            entity_id=gymnast.id,
            details=details,
        )
    )


def error_response(error):
    return jsonify({
        'error': str(error),
        'code': error.code,
    }), error.status


@bp.get('/<championship_id>/categories/<category_id>/scoring')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def get_category_scoring(current_user, championship_id, category_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    try:
        category = get_category(championship, category_id)
    except ScoreSubmissionError as error:
        return error_response(error)

    competition_day = db.session.get(
        CompetitionDay,
        category.competition_day_id,
    )
    assignments = sorted(
        assignments_effective_for_category(
            category,
            include_superseded=True,
        ),
        key=lambda assignment: (
            ROLE_ORDER[assignment.role],
            assignment.created_at,
            str(assignment.id),
        ),
    )
    assignment_payload = []
    for assignment in assignments:
        judge = db.session.get(User, assignment.judge_user_id)
        assignment_payload.append({
            'id': str(assignment.id),
            'role': assignment.role.value,
            'scoring': assignment.role not in {JudgeRole.L, JudgeRole.P},
            'judge': {
                'id': str(judge.id),
                'first_name': judge.first_name,
                'last_name': judge.last_name,
            },
        })

    gymnasts = db.session.execute(
        select(Gymnast)
        .where(
            Gymnast.category_id == category.id,
            Gymnast.deleted_at.is_(None),
        )
        .order_by(Gymnast.passing_order)
    ).scalars().all()
    active_activation = db.session.execute(
        select(BenchActivation).where(
            BenchActivation.championship_id == championship.id,
            BenchActivation.competition_day_id == competition_day.id,
            BenchActivation.bench == category.bench,
            BenchActivation.deactivated_at.is_(None),
        )
    ).scalar_one_or_none()

    gymnast_payload = []
    for gymnast in gymnasts:
        score_entries = db.session.execute(
            select(ScoreEntry)
            .join(
                JudgeAssignment,
                JudgeAssignment.id == ScoreEntry.judge_assignment_id,
            )
            .where(
                ScoreEntry.gymnast_id == gymnast.id,
                JudgeAssignment.id.in_(
                    [assignment.id for assignment in assignments]
                ),
            )
        ).scalars().unique().all() if assignments else []
        score_entries.sort(
            key=lambda entry: (
                ROLE_ORDER[entry.assignment.role],
                entry.assignment.created_at,
                str(entry.id),
            )
        )
        resolutions = {
            role: db.session.get(
                RoleScoreResolution,
                (gymnast.id, role),
            )
            for role in (JudgeRole.DA, JudgeRole.DB)
        }
        persisted_summary = db.session.get(ScoreSummary, gymnast.id)
        summary_values = (
            persisted_summary_values(persisted_summary)
            if persisted_summary
            else calculated_summary_values(
                score_entries,
                resolutions,
            )
        )
        submitted_by_role = {
            role: [
                entry.value
                for entry in score_entries
                if entry.assignment.role == role
                and entry.submission_status == SubmissionStatus.SUBMITTED
            ]
            for role in (JudgeRole.A, JudgeRole.E)
        }
        gymnast_payload.append({
            'id': str(gymnast.id),
            'full_name': gymnast.full_name,
            'club_name': gymnast.club_name,
            'passing_order': gymnast.passing_order,
            'is_active': (
                active_activation is not None
                and active_activation.gymnast_id == gymnast.id
            ),
            'activation_id': (
                str(active_activation.id)
                if active_activation is not None
                and active_activation.gymnast_id == gymnast.id
                else None
            ),
            'scores': [
                score_response(score_entry)
                for score_entry in score_entries
            ],
            'pending_count': sum(
                entry.submission_status == SubmissionStatus.PENDING
                for entry in score_entries
            ),
            'area_warnings': {
                'A': has_area_difference(
                    submitted_by_role[JudgeRole.A]
                ),
                'E': has_area_difference(
                    submitted_by_role[JudgeRole.E]
                ),
            },
            'role_resolutions': {
                role.value: resolution_response(
                    role,
                    resolutions[role],
                )
                for role in (JudgeRole.DA, JudgeRole.DB)
            },
            'summary': summary_response(summary_values),
        })

    return jsonify({
        'championship': {
            'id': str(championship.id),
            'name': championship.name,
            'status': championship.status.value,
        },
        'competition_day': {
            'id': str(competition_day.id),
            'sequence': competition_day.sequence,
            'date': competition_day.competition_date.isoformat(),
        },
        'category': {
            'id': str(category.id),
            'name': category.name,
            'bench': category.bench.value,
            'session': category.session.value,
            'passing_order': category.passing_order,
        },
        'assignments': assignment_payload,
        'gymnasts': gymnast_payload,
    })


@bp.post('/<championship_id>/categories/<category_id>/gymnasts')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def add_gymnast(current_user, championship_id, category_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    payload = request.get_json(silent=True) or {}
    try:
        full_name, club_name = validated_gymnast_fields(payload)
        category = get_category(championship, category_id)
        championship = lock_championship(championship)
        ensure_gymnasts_editable(championship)
        category = lock_category(category)
        gymnast, initialized_scores = create_gymnast(
            category,
            full_name,
            club_name,
            payload.get('passing_order'),
        )
        summary = db.session.get(ScoreSummary, gymnast.id)
        add_gymnast_audit(
            current_user,
            'GYMNAST_CREATED',
            championship,
            gymnast,
            {
                'category_id': str(category.id),
                'passing_order': gymnast.passing_order,
                'full_name': gymnast.full_name,
            },
        )
        db.session.commit()
    except (GymnastManagementError, ScoreSubmissionError) as error:
        db.session.rollback()
        return error_response(error)
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'La gimnasta no pudo agregarse por un cambio simultáneo',
            code='GYMNAST_CONFLICT',
            status=409,
        )
    return jsonify({
        'gymnast': gymnast_order_response(gymnast),
        'initialized_scores': initialized_scores,
        'summary': summary_response(persisted_summary_values(summary)),
        'changed': True,
    }), 201


@bp.delete('/<championship_id>/gymnasts/<gymnast_id>')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def remove_gymnast(current_user, championship_id, gymnast_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    try:
        gymnast, category = get_gymnast(championship, gymnast_id)
        championship = lock_championship(championship)
        ensure_gymnasts_editable(championship)
        lock_category(category)
        gymnast, activation, previous_order = delete_gymnast(
            championship,
            gymnast,
            current_user.id,
        )
        remaining = db.session.execute(
            select(Gymnast)
            .where(
                Gymnast.category_id == category.id,
                Gymnast.deleted_at.is_(None),
            )
            .order_by(Gymnast.passing_order)
        ).scalars().all()
        add_gymnast_audit(
            current_user,
            'GYMNAST_DELETED',
            championship,
            gymnast,
            {
                'category_id': str(category.id),
                'previous_passing_order': previous_order,
                'full_name': gymnast.full_name,
                'deactivated_activation_id': (
                    str(activation.id) if activation else None
                ),
            },
        )
        db.session.commit()
    except (GymnastManagementError, ScoreSubmissionError) as error:
        db.session.rollback()
        return error_response(error)
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'La gimnasta no pudo eliminarse por un cambio simultáneo',
            code='GYMNAST_CONFLICT',
            status=409,
        )
    return jsonify({
        'gymnast_id': str(gymnast.id),
        'active_activation_cleared': activation is not None,
        'gymnasts': [
            gymnast_order_response(candidate)
            for candidate in remaining
        ],
        'changed': True,
    })


@bp.put('/<championship_id>/categories/<category_id>/gymnasts/order')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def update_gymnast_order(current_user, championship_id, category_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    payload = request.get_json(silent=True) or {}
    try:
        raw_ids = payload.get('gymnast_ids')
        if not isinstance(raw_ids, list):
            raise GymnastManagementError(
                'gymnast_ids debe ser una lista',
                code='INVALID_GYMNAST_ORDER',
            )
        gymnast_ids = [
            parse_uuid_value(raw_id, 'gymnast_id')
            for raw_id in raw_ids
        ]
        category = get_category(championship, category_id)
        championship = lock_championship(championship)
        ensure_gymnasts_editable(championship)
        category = lock_category(category)
        gymnasts, changed = reorder_gymnasts(category, gymnast_ids)
        db.session.commit()
    except (GymnastManagementError, ScoreSubmissionError) as error:
        db.session.rollback()
        return error_response(error)
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'El orden no pudo guardarse por un cambio simultáneo',
            code='GYMNAST_ORDER_CONFLICT',
            status=409,
        )
    return jsonify({
        'order_mode': 'MANUAL',
        'gymnasts': [
            gymnast_order_response(gymnast)
            for gymnast in gymnasts
        ],
        'changed': changed,
    })


@bp.post(
    '/<championship_id>/categories/<category_id>/'
    'gymnasts/order-by-score'
)
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def sort_gymnasts_by_score(current_user, championship_id, category_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    try:
        category = get_category(championship, category_id)
        championship = lock_championship(championship)
        ensure_gymnasts_editable(championship)
        category = lock_category(category)
        gymnasts, summaries, changed = order_gymnasts_by_score(category)
        db.session.commit()
    except (GymnastManagementError, ScoreSubmissionError) as error:
        db.session.rollback()
        return error_response(error)
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'El ranking no pudo guardarse por un cambio simultáneo',
            code='GYMNAST_ORDER_CONFLICT',
            status=409,
        )
    return jsonify({
        'order_mode': 'SCORE',
        'gymnasts': [
            {
                **gymnast_order_response(gymnast),
                'total_score': decimal_response(
                    summaries[gymnast.id].total_score
                ),
                'e_score': decimal_response(
                    summaries[gymnast.id].e_score
                ),
                'a_score': decimal_response(
                    summaries[gymnast.id].a_score
                ),
            }
            for gymnast in gymnasts
        ],
        'changed': changed,
    })


@bp.put('/<championship_id>/score-entries/<score_entry_id>')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def update_score_entry(current_user, championship_id, score_entry_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    payload = request.get_json(silent=True) or {}
    try:
        ensure_scores_editable(championship)
        if 'value' not in payload:
            raise ScoreValidationError('La nota es obligatoria')
        parsed_id = parse_uuid_value(score_entry_id, 'score_entry_id')
        score_entry = db.session.get(ScoreEntry, parsed_id)
        if (
            score_entry is None
            or score_entry.assignment.championship_id != championship.id
        ):
            raise ScoreSubmissionError(
                'Nota no encontrada',
                code='SCORE_ENTRY_NOT_FOUND',
                status=404,
            )
        db.session.execute(
            select(Championship)
            .where(Championship.id == championship.id)
            .with_for_update()
        ).scalar_one()
        score_entry = db.session.execute(
            select(ScoreEntry)
            .where(ScoreEntry.id == parsed_id)
            .with_for_update(of=ScoreEntry)
        ).scalar_one()
        score_entry, changed = submit_administrator_score(
            score_entry,
            payload['value'],
            current_user.id,
        )
        summary = db.session.get(
            ScoreSummary,
            score_entry.gymnast_id,
        )
        db.session.commit()
    except ScoreValidationError as error:
        db.session.rollback()
        return jsonify({
            'error': str(error),
            'code': 'INVALID_SCORE',
        }), 400
    except ScoreSubmissionError as error:
        db.session.rollback()
        return error_response(error)
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'La nota no pudo guardarse por un cambio simultáneo',
            code='SCORE_CONFLICT',
            status=409,
        )
    return jsonify({
        'score': score_response(score_entry),
        'summary': summary_response(
            persisted_summary_values(summary)
        ),
        'changed': changed,
    })


@bp.put('/<championship_id>/gymnasts/<gymnast_id>/discount')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def update_discount(current_user, championship_id, gymnast_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    payload = request.get_json(silent=True) or {}
    try:
        ensure_scores_editable(championship)
        if 'value' not in payload:
            raise ScoreValidationError('El descuento es obligatorio')
        new_discount = parse_score_value(payload['value'])
        gymnast, _ = get_gymnast(championship, gymnast_id)
        db.session.execute(
            select(Championship)
            .where(Championship.id == championship.id)
            .with_for_update()
        ).scalar_one()
        db.session.execute(
            select(Gymnast)
            .where(Gymnast.id == gymnast.id)
            .with_for_update(of=Gymnast)
        ).scalar_one()
        summary = refresh_score_summary(gymnast.id)
        changed = summary.discount != new_discount
        if changed:
            summary.discount = new_discount
            db.session.flush()
            summary = refresh_score_summary(
                gymnast.id,
                datetime.now(timezone.utc),
            )
        db.session.commit()
    except ScoreValidationError as error:
        db.session.rollback()
        return jsonify({
            'error': str(error),
            'code': 'INVALID_DISCOUNT',
        }), 400
    except ScoreSubmissionError as error:
        db.session.rollback()
        return error_response(error)
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'El descuento no pudo guardarse por un cambio simultáneo',
            code='SCORE_CONFLICT',
            status=409,
        )
    return jsonify({
        'summary': summary_response(
            persisted_summary_values(summary)
        ),
        'changed': changed,
    })


@bp.put(
    '/<championship_id>/gymnasts/<gymnast_id>/'
    'role-resolutions/<role_value>'
)
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def resolve_role_discrepancy(
    current_user,
    championship_id,
    gymnast_id,
    role_value,
):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    payload = request.get_json(silent=True) or {}
    try:
        ensure_scores_editable(championship)
        try:
            role = JudgeRole(str(role_value).strip().upper())
        except ValueError:
            raise ScoreSubmissionError(
                'Solo DA y DB admiten resolución administrativa',
                code='INVALID_RESOLUTION_ROLE',
                status=400,
            ) from None
        if role not in {JudgeRole.DA, JudgeRole.DB}:
            raise ScoreSubmissionError(
                'Solo DA y DB admiten resolución administrativa',
                code='INVALID_RESOLUTION_ROLE',
                status=400,
            )
        gymnast, _ = get_gymnast(championship, gymnast_id)
        requested_value = (
            parse_score_value(payload['value'])
            if 'value' in payload and payload['value'] is not None
            else None
        )
        db.session.execute(
            select(Championship)
            .where(Championship.id == championship.id)
            .with_for_update()
        ).scalar_one()
        resolution = db.session.execute(
            select(RoleScoreResolution)
            .where(
                RoleScoreResolution.gymnast_id == gymnast.id,
                RoleScoreResolution.role == role,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if resolution is None or not resolution.has_discrepancy:
            raise ScoreSubmissionError(
                'No existe una discrepancia para resolver',
                code='NO_ROLE_DISCREPANCY',
            )
        changed = (
            resolution.warning_active
            or (
                requested_value is not None
                and requested_value != resolution.effective_value
            )
        )
        if changed:
            acknowledge_role_resolution(
                resolution,
                current_user.id,
                requested_value,
            )
        summary = db.session.get(ScoreSummary, gymnast.id)
        db.session.commit()
    except ScoreValidationError as error:
        db.session.rollback()
        return jsonify({
            'error': str(error),
            'code': 'INVALID_SCORE',
        }), 400
    except ScoreSubmissionError as error:
        db.session.rollback()
        return error_response(error)
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'La resolución no pudo guardarse por un cambio simultáneo',
            code='SCORE_CONFLICT',
            status=409,
        )
    return jsonify({
        'resolution': resolution_response(role, resolution),
        'summary': summary_response(
            persisted_summary_values(summary)
        ),
        'changed': changed,
    })
