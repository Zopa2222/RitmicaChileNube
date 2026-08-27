import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AccountType,
    AuditLog,
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
    ScoreSummary,
    Session,
    SubmissionStatus,
    User,
)
from app.routes.cloud_championships import (
    championship_response,
    get_championship_or_404,
    validation_error,
)
from app.security.permissions import account_types_required
from app.services.championship_operations_service import (
    ChampionshipOperationError,
    activate_gymnast,
    create_judge_assignment,
    get_competition_day,
    next_gymnast_for_bench,
    remove_judge_assignment,
    reassign_judge,
    validate_judge,
)
from app.services.judge_account_service import (
    JudgeAccountError,
    create_judge_account,
    find_judge,
)
from app.services.publication_service import publish_up_to_gymnast


bp = Blueprint('cloud_operations', __name__, url_prefix='/api/v1')
ADMIN_ACCOUNT_TYPES = (
    AccountType.SUPER_ADMIN,
    AccountType.GLOBAL_ADMIN,
)


def parse_uuid_value(raw_value, field_name):
    try:
        return uuid.UUID(str(raw_value))
    except (TypeError, ValueError, AttributeError):
        raise ChampionshipOperationError(
            f'{field_name} no es válido',
            code='INVALID_IDENTIFIER',
        ) from None


def parse_enum_value(enum_class, raw_value, field_name):
    try:
        return enum_class(str(raw_value).strip().upper())
    except (TypeError, ValueError, AttributeError):
        values = ', '.join(member.value for member in enum_class)
        raise ChampionshipOperationError(
            f'{field_name} debe ser uno de: {values}'
        ) from None


def operation_error(error):
    return validation_error(
        str(error),
        code=error.code,
        status=error.status,
    )


def decimal_response(value):
    return format(value, '.2f')


def active_score_response(activation, gymnast, category):
    summary = db.session.get(ScoreSummary, gymnast.id)
    pending_count = db.session.scalar(
        select(func.count(ScoreEntry.id)).where(
            ScoreEntry.gymnast_id == gymnast.id,
            ScoreEntry.activation_id == activation.id,
            ScoreEntry.submission_status == SubmissionStatus.PENDING,
        )
    ) or 0
    score = {
        'da_score': '0.00',
        'db_score': '0.00',
        'a_score': '10.00',
        'e_score': '10.00',
        'discount': '0.00',
        'total_score': '20.00',
        'calculation_status': 'PROVISIONAL',
        'calculated_at': None,
    }
    if summary is not None:
        score = {
            'da_score': decimal_response(summary.da_score),
            'db_score': decimal_response(summary.db_score),
            'a_score': decimal_response(summary.a_score),
            'e_score': decimal_response(summary.e_score),
            'discount': decimal_response(summary.discount),
            'total_score': decimal_response(summary.total_score),
            'calculation_status': summary.calculation_status.value,
            'calculated_at': summary.calculated_at.isoformat(),
        }
    return {
        'activation_id': str(activation.id),
        'gymnast_id': str(gymnast.id),
        'full_name': gymnast.full_name,
        'club_name': gymnast.club_name,
        'activated_at': activation.activated_at.isoformat(),
        'category': {
            'id': str(category.id),
            'name': category.name,
            'session': category.session.value,
        },
        'score': score,
        'pending_count': pending_count,
    }


def judge_response(judge):
    return {
        'id': str(judge.id),
        'first_name': judge.first_name,
        'last_name': judge.last_name,
        'rut': judge.rut_normalized,
        'username': judge.username,
        'status': judge.status.value,
    }


def assignment_response(assignment):
    judge = db.session.get(User, assignment.judge_user_id)
    competition_day = db.session.get(
        CompetitionDay,
        assignment.competition_day_id,
    )
    effective_from = db.session.get(
        Category,
        assignment.effective_from_category_id,
    )
    effective_to = (
        db.session.get(Category, assignment.effective_to_category_id)
        if assignment.effective_to_category_id
        else None
    )
    access_window = db.session.execute(
        select(JudgeAccessWindow).where(
            JudgeAccessWindow.judge_user_id == assignment.judge_user_id,
            JudgeAccessWindow.championship_id == assignment.championship_id,
            JudgeAccessWindow.competition_day_id
            == assignment.competition_day_id,
        )
    ).scalar_one_or_none()
    return {
        'id': str(assignment.id),
        'judge': judge_response(judge),
        'competition_day': {
            'id': str(competition_day.id),
            'sequence': competition_day.sequence,
            'date': competition_day.competition_date.isoformat(),
            'sheet_name': competition_day.source_sheet_name,
        },
        'bench': assignment.bench.value,
        'session': assignment.session.value,
        'role': assignment.role.value,
        'effective_from_category': {
            'id': str(effective_from.id),
            'name': effective_from.name,
            'passing_order': effective_from.passing_order,
        },
        'effective_to_category': (
            {
                'id': str(effective_to.id),
                'name': effective_to.name,
                'passing_order': effective_to.passing_order,
            }
            if effective_to else None
        ),
        'superseded_at': (
            assignment.superseded_at.isoformat()
            if assignment.superseded_at else None
        ),
        'access_window': (
            {
                'starts_at': access_window.starts_at.isoformat(),
                'ends_at': access_window.ends_at.isoformat(),
            }
            if access_window else None
        ),
    }


def get_or_create_assignment_judge(payload, current_user):
    raw_judge_id = payload.get('judge_id')
    inline_judge = payload.get('judge')
    if raw_judge_id and inline_judge:
        raise ChampionshipOperationError(
            'Envíe judge_id o los datos de un juez nuevo, no ambos'
        )
    if raw_judge_id:
        return validate_judge(
            parse_uuid_value(raw_judge_id, 'judge_id')
        ), None
    if not isinstance(inline_judge, dict):
        raise ChampionshipOperationError(
            'Debe seleccionar un juez o enviar sus datos para crearlo'
        )
    judge, credentials = create_judge_account(
        inline_judge.get('first_name'),
        inline_judge.get('last_name'),
        inline_judge.get('rut'),
        current_user.id,
    )
    return validate_judge(judge.id), credentials


def get_assignment_for_championship(championship, assignment_id):
    parsed_id = parse_uuid_value(assignment_id, 'assignment_id')
    assignment = db.session.get(JudgeAssignment, parsed_id)
    if (
        assignment is None
        or assignment.championship_id != championship.id
    ):
        raise ChampionshipOperationError(
            'Asignación no encontrada',
            code='ASSIGNMENT_NOT_FOUND',
            status=404,
        )
    return assignment


def audit(
    current_user,
    action,
    championship=None,
    entity_type=None,
    entity_id=None,
    details=None,
):
    db.session.add(
        AuditLog(
            actor_user_id=current_user.id,
            action=action,
            championship_id=championship.id if championship else None,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
    )


@bp.post('/championships/<championship_id>/activate')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def activate_championship(current_user, championship_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    if championship.status == ChampionshipStatus.ACTIVE:
        return jsonify({
            'championship': championship_response(championship),
            'changed': False,
        })
    if championship.status not in {
        ChampionshipStatus.DRAFT,
        ChampionshipStatus.PAUSED,
    }:
        return validation_error(
            'Solo se puede activar un campeonato en borrador o pausado',
            code='INVALID_CHAMPIONSHIP_TRANSITION',
            status=409,
        )

    category_count = db.session.execute(
        select(func.count(Category.id)).where(
            Category.championship_id == championship.id,
            Category.deleted_at.is_(None),
        )
    ).scalar_one()
    if not category_count:
        return validation_error(
            'Debe confirmar un orden de paso antes de activar',
            code='CHAMPIONSHIP_NOT_IMPORTED',
            status=409,
        )

    other_active = db.session.execute(
        select(Championship)
        .where(
            Championship.status == ChampionshipStatus.ACTIVE,
            Championship.id != championship.id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if other_active is not None:
        return jsonify({
            'error': 'Ya existe otro campeonato activo',
            'code': 'ACTIVE_CHAMPIONSHIP_EXISTS',
            'active_championship': championship_response(other_active),
        }), 409

    previous_status = championship.status
    championship.status = ChampionshipStatus.ACTIVE
    audit(
        current_user,
        'CHAMPIONSHIP_ACTIVATED',
        championship,
        'CHAMPIONSHIP',
        championship.id,
        {'previous_status': previous_status.value},
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'Otro campeonato fue activado simultáneamente',
            code='ACTIVE_CHAMPIONSHIP_EXISTS',
            status=409,
        )
    return jsonify({
        'championship': championship_response(championship),
        'changed': True,
    })


@bp.post('/championships/<championship_id>/pause')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def pause_championship(current_user, championship_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    if championship.status == ChampionshipStatus.PAUSED:
        return jsonify({
            'championship': championship_response(championship),
            'changed': False,
        })
    if championship.status != ChampionshipStatus.ACTIVE:
        return validation_error(
            'Solo se puede pausar un campeonato activo',
            code='INVALID_CHAMPIONSHIP_TRANSITION',
            status=409,
        )
    championship.status = ChampionshipStatus.PAUSED
    audit(
        current_user,
        'CHAMPIONSHIP_PAUSED',
        championship,
        'CHAMPIONSHIP',
        championship.id,
    )
    db.session.commit()
    return jsonify({
        'championship': championship_response(championship),
        'changed': True,
    })


@bp.post('/championships/<championship_id>/close')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def close_championship(current_user, championship_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    if championship.status == ChampionshipStatus.CLOSED:
        return jsonify({
            'championship': championship_response(championship),
            'changed': False,
        })
    if championship.status not in {
        ChampionshipStatus.DRAFT,
        ChampionshipStatus.ACTIVE,
        ChampionshipStatus.PAUSED,
    }:
        return validation_error(
            'El campeonato no se puede cerrar en su estado actual',
            code='INVALID_CHAMPIONSHIP_TRANSITION',
            status=409,
        )
    previous_status = championship.status
    championship.status = ChampionshipStatus.CLOSED
    championship.closed_at = datetime.now(timezone.utc)
    open_activations = db.session.execute(
        select(BenchActivation).where(
            BenchActivation.championship_id == championship.id,
            BenchActivation.deactivated_at.is_(None),
        )
    ).scalars().all()
    for activation in open_activations:
        activation.deactivated_at = championship.closed_at
    audit(
        current_user,
        'CHAMPIONSHIP_CLOSED',
        championship,
        'CHAMPIONSHIP',
        championship.id,
        {'previous_status': previous_status.value},
    )
    db.session.commit()
    return jsonify({
        'championship': championship_response(championship),
        'changed': True,
    })


@bp.get('/judges')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def list_judges(current_user):
    query = request.args.get('query', '').strip()
    if query:
        judges = find_judge(query)
    else:
        judges = db.session.execute(
            select(User)
            .where(User.account_type == AccountType.JUDGE)
            .order_by(User.last_name, User.first_name)
            .limit(100)
        ).scalars().all()
    return jsonify({'judges': [judge_response(judge) for judge in judges]})


@bp.post('/judges')
@account_types_required(AccountType.SUPER_ADMIN)
def create_judge(current_user):
    payload = request.get_json(silent=True) or {}
    try:
        judge, credentials = create_judge_account(
            payload.get('first_name'),
            payload.get('last_name'),
            payload.get('rut'),
            current_user.id,
        )
        if credentials is None:
            return validation_error(
                'Ya existe una cuenta de juez con ese RUT',
                code='JUDGE_ALREADY_EXISTS',
                status=409,
            )
        audit(
            current_user,
            'JUDGE_CREATED',
            entity_type='USER',
            entity_id=judge.id,
            details={'rut': judge.rut_normalized},
        )
        db.session.commit()
    except JudgeAccountError as error:
        db.session.rollback()
        return validation_error(str(error))
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'El RUT o usuario ya existe',
            code='JUDGE_ALREADY_EXISTS',
            status=409,
        )
    return jsonify({
        'judge': judge_response(judge),
        'credentials': credentials,
    }), 201


@bp.get('/championships/<championship_id>/judge-assignments')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def list_judge_assignments(current_user, championship_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    include_history = (
        request.args.get('include_history', '').strip().lower()
        in {'1', 'true', 'yes'}
    )
    query = (
        select(JudgeAssignment)
        .where(JudgeAssignment.championship_id == championship.id)
        .order_by(
            JudgeAssignment.competition_day_id,
            JudgeAssignment.bench,
            JudgeAssignment.session,
            JudgeAssignment.role,
            JudgeAssignment.created_at,
        )
    )
    if not include_history:
        query = query.where(JudgeAssignment.superseded_at.is_(None))
    assignments = db.session.execute(query).scalars().all()
    return jsonify({
        'assignments': [
            assignment_response(assignment)
            for assignment in assignments
        ]
    })


@bp.get('/championships/<championship_id>/competition-days')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def list_competition_days(current_user, championship_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    days = db.session.execute(
        select(CompetitionDay)
        .where(CompetitionDay.championship_id == championship.id)
        .order_by(CompetitionDay.sequence)
    ).scalars().all()
    return jsonify({
        'competition_days': [
            {
                'id': str(competition_day.id),
                'sequence': competition_day.sequence,
                'date': competition_day.competition_date.isoformat(),
                'sheet_name': competition_day.source_sheet_name,
            }
            for competition_day in days
        ]
    })


@bp.post('/championships/<championship_id>/judge-assignments')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def assign_judge(current_user, championship_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    payload = request.get_json(silent=True) or {}
    try:
        competition_day = get_competition_day(
            championship,
            parse_uuid_value(
                payload.get('competition_day_id'),
                'competition_day_id',
            ),
        )
        bench = parse_enum_value(Bench, payload.get('bench'), 'bench')
        session = parse_enum_value(
            Session,
            payload.get('session'),
            'session',
        )
        role = parse_enum_value(JudgeRole, payload.get('role'), 'role')
        if payload.get('effective_from_category_id'):
            raise ChampionshipOperationError(
                'La categoría inicial se calcula automáticamente; '
                'use la ruta de reasignación durante el campeonato'
            )
        judge, credentials = get_or_create_assignment_judge(
            payload,
            current_user,
        )
        assignment = create_judge_assignment(
            championship,
            competition_day,
            judge,
            bench,
            session,
            role,
            current_user.id,
        )
        if credentials:
            audit(
                current_user,
                'JUDGE_CREATED',
                championship,
                'USER',
                judge.id,
                {'rut': judge.rut_normalized, 'created_during_assignment': True},
            )
        audit(
            current_user,
            'JUDGE_ASSIGNED',
            championship,
            'JUDGE_ASSIGNMENT',
            assignment.id,
            {
                'judge_user_id': str(judge.id),
                'day_id': str(competition_day.id),
                'bench': bench.value,
                'session': session.value,
                'role': role.value,
            },
        )
        db.session.commit()
    except (ChampionshipOperationError, JudgeAccountError) as error:
        db.session.rollback()
        if isinstance(error, ChampionshipOperationError):
            return operation_error(error)
        return validation_error(str(error))
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'La asignación entra en conflicto con una asignación vigente',
            code='ASSIGNMENT_CONFLICT',
            status=409,
        )

    return jsonify({
        'assignment': assignment_response(assignment),
        'credentials': credentials,
    }), 201


@bp.post(
    '/championships/<championship_id>/judge-assignments/'
    '<assignment_id>/reassign'
)
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def reassign_judge_route(
    current_user,
    championship_id,
    assignment_id,
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
        assignment = get_assignment_for_championship(
            championship,
            assignment_id,
        )
        competition_day = get_competition_day(
            championship,
            assignment.competition_day_id,
        )
        new_judge, credentials = get_or_create_assignment_judge(
            payload,
            current_user,
        )
        new_assignment, effective_from = reassign_judge(
            assignment,
            championship,
            competition_day,
            new_judge,
            current_user.id,
        )
        if credentials:
            audit(
                current_user,
                'JUDGE_CREATED',
                championship,
                'USER',
                new_judge.id,
                {
                    'rut': new_judge.rut_normalized,
                    'created_during_reassignment': True,
                },
            )
        audit(
            current_user,
            'JUDGE_REASSIGNED',
            championship,
            'JUDGE_ASSIGNMENT',
            new_assignment.id,
            {
                'previous_assignment_id': str(assignment.id),
                'previous_judge_user_id': str(assignment.judge_user_id),
                'new_judge_user_id': str(new_judge.id),
                'effective_from_category_id': str(effective_from.id),
            },
        )
        db.session.commit()
    except (ChampionshipOperationError, JudgeAccountError) as error:
        db.session.rollback()
        if isinstance(error, ChampionshipOperationError):
            return operation_error(error)
        return validation_error(str(error))
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'La reasignación entra en conflicto con otra asignación',
            code='ASSIGNMENT_CONFLICT',
            status=409,
        )
    return jsonify({
        'assignment': assignment_response(new_assignment),
        'credentials': credentials,
    }), 201


@bp.delete(
    '/championships/<championship_id>/judge-assignments/'
    '<assignment_id>'
)
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def remove_judge_assignment_route(
    current_user,
    championship_id,
    assignment_id,
):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    try:
        assignment = get_assignment_for_championship(
            championship,
            assignment_id,
        )
        competition_day = get_competition_day(
            championship,
            assignment.competition_day_id,
        )
        judge_user_id = assignment.judge_user_id
        assignment_audit_details = {
            'day_id': str(competition_day.id),
            'bench': assignment.bench.value,
            'session': assignment.session.value,
            'role': assignment.role.value,
        }
        effective_from = remove_judge_assignment(
            assignment,
            championship,
            competition_day,
        )
        audit(
            current_user,
            'JUDGE_ASSIGNMENT_REMOVED',
            championship,
            'JUDGE_ASSIGNMENT',
            assignment.id,
            {
                'judge_user_id': str(judge_user_id),
                **assignment_audit_details,
                'effective_from_category_id': (
                    str(effective_from.id) if effective_from else None
                ),
            },
        )
        db.session.commit()
    except ChampionshipOperationError as error:
        db.session.rollback()
        return operation_error(error)

    return jsonify({
        'removed': True,
        'effective_from_category': (
            {
                'id': str(effective_from.id),
                'name': effective_from.name,
                'passing_order': effective_from.passing_order,
            }
            if effective_from else None
        ),
    })


@bp.get(
    '/championships/<championship_id>/competition-days/'
    '<competition_day_id>/operations'
)
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def competition_day_operations(
    current_user,
    championship_id,
    competition_day_id,
):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    try:
        competition_day = get_competition_day(
            championship,
            parse_uuid_value(
                competition_day_id,
                'competition_day_id',
            ),
        )
    except ChampionshipOperationError as error:
        return operation_error(error)

    categories = db.session.execute(
        select(Category)
        .where(
            Category.competition_day_id == competition_day.id,
            Category.deleted_at.is_(None),
        )
        .order_by(
            Category.bench,
            Category.session,
            Category.passing_order,
        )
    ).scalars().all()
    active_by_bench = {
        activation.bench: activation
        for activation in db.session.execute(
            select(BenchActivation).where(
                BenchActivation.championship_id == championship.id,
                BenchActivation.competition_day_id == competition_day.id,
                BenchActivation.deactivated_at.is_(None),
            )
        ).scalars()
    }
    benches = {}
    for bench in Bench:
        activation = active_by_bench.get(bench)
        active_gymnast = (
            db.session.get(Gymnast, activation.gymnast_id)
            if activation else None
        )
        benches[bench.value] = {
            'active': (
                {
                    'activation_id': str(activation.id),
                    'gymnast_id': str(active_gymnast.id),
                    'full_name': active_gymnast.full_name,
                    'activated_at': activation.activated_at.isoformat(),
                }
                if activation else None
            ),
            'categories': [],
        }

    for category in categories:
        gymnasts = db.session.execute(
            select(Gymnast)
            .where(
                Gymnast.category_id == category.id,
                Gymnast.deleted_at.is_(None),
            )
            .order_by(Gymnast.passing_order)
        ).scalars().all()
        benches[category.bench.value]['categories'].append({
            'id': str(category.id),
            'name': category.name,
            'session': category.session.value,
            'passing_order': category.passing_order,
            'gymnasts': [
                {
                    'id': str(gymnast.id),
                    'full_name': gymnast.full_name,
                    'club_name': gymnast.club_name,
                    'passing_order': gymnast.passing_order,
                }
                for gymnast in gymnasts
            ],
        })

    return jsonify({
        'championship': championship_response(championship),
        'competition_day': {
            'id': str(competition_day.id),
            'sequence': competition_day.sequence,
            'date': competition_day.competition_date.isoformat(),
            'sheet_name': competition_day.source_sheet_name,
        },
        'benches': benches,
    })


@bp.put(
    '/championships/<championship_id>/competition-days/'
    '<competition_day_id>/benches/<bench_value>/active-gymnast'
)
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def set_active_gymnast(
    current_user,
    championship_id,
    competition_day_id,
    bench_value,
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
        competition_day = get_competition_day(
            championship,
            parse_uuid_value(
                competition_day_id,
                'competition_day_id',
            ),
        )
        bench = parse_enum_value(Bench, bench_value, 'bench')
        gymnast_id = parse_uuid_value(
            payload.get('gymnast_id'),
            'gymnast_id',
        )
        gymnast = db.session.get(Gymnast, gymnast_id)
        if gymnast is None:
            raise ChampionshipOperationError(
                'Gimnasta no encontrada',
                code='GYMNAST_NOT_FOUND',
                status=404,
            )
        activation, changed, category = activate_gymnast(
            championship,
            competition_day,
            bench,
            gymnast,
            current_user.id,
        )
        if changed:
            audit(
                current_user,
                'GYMNAST_ACTIVATED',
                championship,
                'BENCH_ACTIVATION',
                activation.id,
                {
                    'competition_day_id': str(competition_day.id),
                    'bench': bench.value,
                    'gymnast_id': str(gymnast.id),
                    'category_id': str(category.id),
                },
            )
        db.session.commit()
    except ChampionshipOperationError as error:
        db.session.rollback()
        return operation_error(error)
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'Otra activación fue registrada simultáneamente',
            code='ACTIVATION_CONFLICT',
            status=409,
        )
    return jsonify({
        'activation': {
            'id': str(activation.id),
            'championship_id': str(championship.id),
            'competition_day_id': str(competition_day.id),
            'bench': bench.value,
            'gymnast': {
                'id': str(gymnast.id),
                'full_name': gymnast.full_name,
                'club_name': gymnast.club_name,
            },
            'category': {
                'id': str(category.id),
                'name': category.name,
                'session': category.session.value,
            },
            'activated_at': activation.activated_at.isoformat(),
        },
        'changed': changed,
    })
