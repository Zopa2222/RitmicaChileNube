import uuid
from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AccountType,
    BenchActivation,
    Category,
    Championship,
    ChampionshipStatus,
    CompetitionDay,
    Gymnast,
    JudgeAssignment,
    JudgeRole,
    ScoreEntry,
)
from app.security.permissions import account_types_required
from app.services.championship_operations_service import (
    assignments_effective_for_category,
)
from app.services.cloud_scoring_service import (
    ScoreSubmissionError,
    ScoreValidationError,
    submit_judge_score,
)


bp = Blueprint('judge_cabin', __name__, url_prefix='/api/v1/judge')


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


def score_entry_response(score_entry):
    return {
        'id': str(score_entry.id),
        'value': decimal_response(score_entry.value),
        'submission_status': score_entry.submission_status.value,
        'submitted_at': (
            score_entry.submitted_at.isoformat()
            if score_entry.submitted_at else None
        ),
    }


def assignment_context(assignment):
    championship = db.session.get(Championship, assignment.championship_id)
    competition_day = db.session.get(
        CompetitionDay,
        assignment.competition_day_id,
    )
    response = {
        'assignment_id': str(assignment.id),
        'championship': {
            'id': str(championship.id),
            'name': championship.name,
        },
        'competition_day': {
            'id': str(competition_day.id),
            'sequence': competition_day.sequence,
            'date': competition_day.competition_date.isoformat(),
        },
        'bench': assignment.bench.value,
        'session': assignment.session.value,
        'role': assignment.role.value,
        'can_score': assignment.role not in {JudgeRole.L, JudgeRole.P},
        'state': 'WAITING_FOR_GYMNAST',
        'active': None,
    }

    if championship.status != ChampionshipStatus.ACTIVE:
        response['state'] = 'WAITING_FOR_CHAMPIONSHIP'
        return response

    activation = db.session.execute(
        select(BenchActivation).where(
            BenchActivation.championship_id == assignment.championship_id,
            BenchActivation.competition_day_id
            == assignment.competition_day_id,
            BenchActivation.bench == assignment.bench,
            BenchActivation.deactivated_at.is_(None),
        )
    ).scalar_one_or_none()
    if activation is None:
        return response

    gymnast = db.session.get(Gymnast, activation.gymnast_id)
    category = db.session.get(Category, gymnast.category_id)
    if category.session != assignment.session:
        response['state'] = 'WAITING_FOR_SESSION'
        return response
    effective_assignment_ids = {
        effective_assignment.id
        for effective_assignment in assignments_effective_for_category(
            category
        )
    }
    if assignment.id not in effective_assignment_ids:
        response['state'] = 'WAITING_FOR_EFFECTIVE_CATEGORY'
        return response

    score_entry = None
    if response['can_score']:
        score_entry = db.session.execute(
            select(ScoreEntry).where(
                ScoreEntry.gymnast_id == gymnast.id,
                ScoreEntry.judge_assignment_id == assignment.id,
            )
        ).scalar_one_or_none()
        if score_entry is None:
            response['state'] = 'SCORE_NOT_INITIALIZED'
            return response

    response['state'] = 'ACTIVE'
    response['active'] = {
        'activation_id': str(activation.id),
        'gymnast': {
            'id': str(gymnast.id),
            'full_name': gymnast.full_name,
            'club_name': gymnast.club_name,
        },
        'category': {
            'id': str(category.id),
            'name': category.name,
        },
        'score': (
            score_entry_response(score_entry)
            if score_entry is not None else None
        ),
    }
    return response


@bp.get('/contexts')
@account_types_required(AccountType.JUDGE)
def get_judge_contexts(current_user):
    now = datetime.now(timezone.utc)
    assignments = db.session.execute(
        select(JudgeAssignment)
        .join(
            Championship,
            Championship.id == JudgeAssignment.championship_id,
        )
        .where(
            JudgeAssignment.judge_user_id == current_user.id,
            JudgeAssignment.superseded_at.is_(None),
            Championship.status.in_([
                ChampionshipStatus.ACTIVE,
                ChampionshipStatus.PAUSED,
            ]),
        )
        .order_by(
            JudgeAssignment.competition_day_id,
            JudgeAssignment.bench,
            JudgeAssignment.session,
            JudgeAssignment.role,
        )
    ).scalars().all()
    return jsonify({
        'contexts': [
            assignment_context(assignment)
            for assignment in assignments
        ],
        'server_time': now.isoformat(),
    })


@bp.put('/scores/<score_entry_id>')
@account_types_required(AccountType.JUDGE)
def update_judge_score(current_user, score_entry_id):
    payload = request.get_json(silent=True) or {}
    try:
        parsed_score_entry_id = parse_uuid_value(
            score_entry_id,
            'score_entry_id',
        )
        activation_id = parse_uuid_value(
            payload.get('activation_id'),
            'activation_id',
        )
        if 'value' not in payload:
            raise ScoreValidationError('La nota es obligatoria')

        score_entry = db.session.execute(
            select(ScoreEntry)
            .where(ScoreEntry.id == parsed_score_entry_id)
        ).scalar_one_or_none()
        if (
            score_entry is None
            or score_entry.assignment.judge_user_id != current_user.id
        ):
            raise ScoreSubmissionError(
                'Nota no encontrada',
                code='SCORE_ENTRY_NOT_FOUND',
                status=404,
            )
        championship = db.session.execute(
            select(Championship)
            .where(
                Championship.id
                == score_entry.assignment.championship_id
            )
            .with_for_update()
        ).scalar_one()
        if championship.status != ChampionshipStatus.ACTIVE:
            raise ScoreSubmissionError(
                'El campeonato ya no está activo',
                code='CHAMPIONSHIP_NOT_ACTIVE',
                status=403,
            )

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
        score_entry = db.session.execute(
            select(ScoreEntry)
            .where(ScoreEntry.id == parsed_score_entry_id)
            .with_for_update(of=ScoreEntry)
        ).scalar_one()
        score_entry, changed = submit_judge_score(
            score_entry,
            payload['value'],
            current_user.id,
            activation_id,
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
        return jsonify({
            'error': str(error),
            'code': error.code,
        }), error.status
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'error': 'La nota no pudo guardarse por un cambio simultáneo',
            'code': 'SCORE_CONFLICT',
        }), 409

    return jsonify({
        'score': score_entry_response(score_entry),
        'changed': changed,
        'server_time': datetime.now(timezone.utc).isoformat(),
    })
