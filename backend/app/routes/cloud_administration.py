"""Administrative cloud routes that are intentionally unavailable to judges.

The operations routes keep the competition running; this module contains the
rare, high-impact actions that are restricted to the super administrator.
"""

import uuid
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from app.extensions import db
from app.models import (
    AccountType,
    AuditLog,
    AuthRecoveryRequest,
    Championship,
    ChampionshipDeletionConfirmation,
    ChampionshipStatus,
    CredentialEvent,
    CredentialEventType,
    User,
    UserStatus,
)
from app.routes.cloud_championships import (
    championship_response,
    get_championship_or_404,
    validation_error,
)
from app.security.passwords import hash_password
from app.security.permissions import account_types_required
from app.services.file_storage_service import FileStorageError, delete_object
from app.services.judge_account_service import (
    JudgeAccountError,
    create_judge_account,
    generate_initial_password,
    normalize_rut,
)


bp = Blueprint('cloud_administration', __name__, url_prefix='/api/v1')
SUPER_ADMIN = (AccountType.SUPER_ADMIN,)
ADMINS = (AccountType.SUPER_ADMIN, AccountType.GLOBAL_ADMIN)


def _uuid(raw_value, field_name):
    try:
        return uuid.UUID(str(raw_value))
    except (TypeError, ValueError, AttributeError):
        return None


def _judge_response(judge):
    return {
        'id': str(judge.id),
        'first_name': judge.first_name,
        'last_name': judge.last_name,
        'rut': judge.rut_normalized,
        'username': judge.username,
        'status': judge.status.value,
        'last_login_at': (
            judge.last_login_at.isoformat() if judge.last_login_at else None
        ),
    }


def _audit(actor, action, championship=None, entity_type=None, entity_id=None,
           details=None):
    db.session.add(AuditLog(
        actor_user_id=actor.id,
        action=action,
        championship_id=championship.id if championship else None,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    ))


def _get_judge_or_error(judge_id):
    parsed_id = _uuid(judge_id, 'judge_id')
    judge = db.session.get(User, parsed_id) if parsed_id else None
    if judge is None or judge.account_type != AccountType.JUDGE:
        return None
    return judge


def _as_utc(value):
    """SQLite returns naive DateTime values even for timezone-aware columns."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@bp.get('/admin/judges')
@account_types_required(*SUPER_ADMIN)
def list_judges(current_user):
    query = str(request.args.get('query', '')).strip().upper()
    statement = select(User).where(User.account_type == AccountType.JUDGE)
    if query:
        wildcard = f'%{query}%'
        statement = statement.where(
            User.username.ilike(wildcard)
            | User.first_name.ilike(wildcard)
            | User.last_name.ilike(wildcard)
            | User.rut_normalized.ilike(wildcard)
        )
    judges = db.session.execute(
        statement.order_by(User.last_name, User.first_name).limit(100)
    ).scalars().all()
    return jsonify({'judges': [_judge_response(judge) for judge in judges]})


@bp.post('/admin/judges')
@account_types_required(*SUPER_ADMIN)
def create_judge(current_user):
    payload = request.get_json(silent=True) or {}
    try:
        judge, credentials = create_judge_account(
            payload.get('first_name'), payload.get('last_name'),
            payload.get('rut'), current_user.id,
        )
        if credentials is None:
            return validation_error(
                'Ya existe una cuenta de juez para ese RUT',
                code='JUDGE_ALREADY_EXISTS', status=409,
            )
        _audit(current_user, 'JUDGE_CREATED', entity_type='USER',
               entity_id=judge.id, details={'username': judge.username})
        db.session.commit()
    except JudgeAccountError as error:
        db.session.rollback()
        return validation_error(str(error), code='INVALID_JUDGE')
    return jsonify({'judge': _judge_response(judge), 'credentials': credentials}), 201


@bp.patch('/admin/judges/<judge_id>')
@account_types_required(*SUPER_ADMIN)
def update_judge(current_user, judge_id):
    judge = _get_judge_or_error(judge_id)
    if judge is None:
        return validation_error('Juez no encontrado', code='JUDGE_NOT_FOUND', status=404)
    payload = request.get_json(silent=True) or {}
    try:
        if 'first_name' in payload:
            value = str(payload['first_name']).strip()
            if not value or len(value) > 100:
                raise JudgeAccountError('El nombre debe tener entre 1 y 100 caracteres')
            judge.first_name = value
        if 'last_name' in payload:
            value = str(payload['last_name']).strip()
            if not value or len(value) > 100:
                raise JudgeAccountError('El apellido debe tener entre 1 y 100 caracteres')
            judge.last_name = value
        if 'rut' in payload:
            rut = normalize_rut(payload['rut'])
            duplicate = db.session.execute(
                select(User.id).where(User.rut_normalized == rut, User.id != judge.id)
            ).scalar_one_or_none()
            if duplicate:
                raise JudgeAccountError('El RUT ya pertenece a otra cuenta')
            judge.rut_normalized = rut
        if 'status' in payload:
            try:
                judge.status = UserStatus(str(payload['status']).upper())
            except (TypeError, ValueError):
                raise JudgeAccountError('El estado debe ser ACTIVE, DISABLED o LOCKED')
        _audit(current_user, 'JUDGE_UPDATED', entity_type='USER', entity_id=judge.id,
               details={'status': judge.status.value})
        db.session.commit()
    except JudgeAccountError as error:
        db.session.rollback()
        return validation_error(str(error), code='INVALID_JUDGE')
    return jsonify({'judge': _judge_response(judge)})


@bp.delete('/admin/judges/<judge_id>')
@account_types_required(*SUPER_ADMIN)
def disable_judge(current_user, judge_id):
    judge = _get_judge_or_error(judge_id)
    if judge is None:
        return validation_error('Juez no encontrado', code='JUDGE_NOT_FOUND', status=404)
    judge.status = UserStatus.DISABLED
    _audit(current_user, 'JUDGE_DISABLED', entity_type='USER', entity_id=judge.id)
    db.session.commit()
    return jsonify({'judge': _judge_response(judge)})


@bp.post('/admin/judges/<judge_id>/credentials/regenerate')
@account_types_required(*SUPER_ADMIN)
def regenerate_judge_credentials(current_user, judge_id):
    judge = _get_judge_or_error(judge_id)
    if judge is None:
        return validation_error('Juez no encontrado', code='JUDGE_NOT_FOUND', status=404)
    password = generate_initial_password()
    judge.password_hash = hash_password(password)
    judge.status = UserStatus.ACTIVE
    db.session.add(CredentialEvent(
        user_id=judge.id,
        event_type=CredentialEventType.REGENERATED,
        created_by_user_id=current_user.id,
    ))
    _audit(current_user, 'JUDGE_CREDENTIALS_REGENERATED', entity_type='USER',
           entity_id=judge.id)
    db.session.commit()
    return jsonify({
        'judge': _judge_response(judge),
        'credentials': {'username': judge.username, 'password': password},
    })


@bp.post('/admin/global-admin/recovery')
@account_types_required(*SUPER_ADMIN)
def recover_global_administrator(current_user):
    payload = request.get_json(silent=True) or {}
    password = payload.get('new_password')
    if not isinstance(password, str) or len(password) < 12:
        return validation_error(
            'La nueva contraseña debe tener al menos 12 caracteres',
            code='INVALID_PASSWORD',
        )
    administrator = db.session.execute(select(User).where(
        User.account_type == AccountType.GLOBAL_ADMIN
    )).scalar_one_or_none()
    if administrator is None:
        return validation_error('No existe administrador global', code='GLOBAL_ADMIN_NOT_FOUND', status=404)
    now = datetime.now(timezone.utc)
    administrator.password_hash = hash_password(password)
    administrator.status = UserStatus.ACTIVE
    db.session.add(AuthRecoveryRequest(
        user_id=administrator.id,
        verified_by_user_id=current_user.id,
        verified_at=now,
        resolved_at=now,
    ))
    db.session.add(CredentialEvent(
        user_id=administrator.id,
        event_type=CredentialEventType.REGENERATED,
        created_by_user_id=current_user.id,
    ))
    _audit(current_user, 'GLOBAL_ADMIN_ACCESS_RECOVERED', entity_type='USER',
           entity_id=administrator.id)
    db.session.commit()
    return jsonify({'administrator': {
        'id': str(administrator.id), 'username': administrator.username,
    }})


@bp.get('/admin/audit-logs')
@account_types_required(*SUPER_ADMIN)
def audit_logs(current_user):
    limit = min(max(int(request.args.get('limit', 100)), 1), 250)
    statement = select(AuditLog).order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
    championship_id = _uuid(request.args.get('championship_id'), 'championship_id')
    if request.args.get('championship_id') and championship_id is None:
        return validation_error('championship_id no es válido', code='INVALID_IDENTIFIER')
    if championship_id:
        statement = statement.where(AuditLog.championship_id == championship_id)
    logs = db.session.execute(statement.limit(limit)).scalars().all()
    return jsonify({'logs': [{
        'id': str(log.id), 'occurred_at': log.occurred_at.isoformat(),
        'actor_user_id': str(log.actor_user_id) if log.actor_user_id else None,
        'action': log.action,
        'championship_id': str(log.championship_id) if log.championship_id else None,
        'entity_type': log.entity_type,
        'entity_id': str(log.entity_id) if log.entity_id else None,
        'details': log.details,
    } for log in logs]})


@bp.post('/championships/<championship_id>/deletion-confirmations')
@account_types_required(*ADMINS)
def confirm_championship_deletion(current_user, championship_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error('Campeonato no encontrado', code='CHAMPIONSHIP_NOT_FOUND', status=404)
    payload = request.get_json(silent=True) or {}
    step = payload.get('step')
    if not isinstance(step, int) or step not in {1, 2, 3}:
        return validation_error('step debe ser 1, 2 o 3', code='INVALID_DELETION_STEP')
    if championship.status in {ChampionshipStatus.DELETED, ChampionshipStatus.PENDING_DELETION}:
        return validation_error('El campeonato ya está en proceso de eliminación', code='INVALID_CHAMPIONSHIP_STATUS', status=409)
    previous_steps = set(db.session.execute(select(
        ChampionshipDeletionConfirmation.confirmation_step
    ).where(
        ChampionshipDeletionConfirmation.championship_id == championship.id,
        ChampionshipDeletionConfirmation.confirmed_by_user_id == current_user.id,
    )).scalars())
    if step > 1 and not set(range(1, step)).issubset(previous_steps):
        return validation_error('Las confirmaciones deben realizarse en orden', code='DELETION_CONFIRMATION_ORDER', status=409)
    if step not in previous_steps:
        db.session.add(ChampionshipDeletionConfirmation(
            championship_id=championship.id,
            confirmed_by_user_id=current_user.id,
            confirmation_step=step,
        ))
    if step == 3:
        now = datetime.now(timezone.utc)
        championship.status = ChampionshipStatus.PENDING_DELETION
        championship.deletion_requested_at = now
        championship.purge_after = now + timedelta(days=14)
        _audit(current_user, 'CHAMPIONSHIP_DELETION_REQUESTED', championship,
               'CHAMPIONSHIP', championship.id,
               {'purge_after': championship.purge_after.isoformat()})
    db.session.commit()
    return jsonify({'championship': championship_response(championship), 'step': step})


@bp.post('/championships/<championship_id>/recover')
@account_types_required(*ADMINS)
def recover_championship(current_user, championship_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error('Campeonato no encontrado', code='CHAMPIONSHIP_NOT_FOUND', status=404)
    now = datetime.now(timezone.utc)
    if championship.status != ChampionshipStatus.PENDING_DELETION:
        return validation_error('El campeonato no está pendiente de eliminación', code='CHAMPIONSHIP_NOT_RECOVERABLE', status=409)
    if _as_utc(championship.purge_after) and _as_utc(championship.purge_after) <= now:
        return validation_error('El período de recuperación ya terminó', code='RECOVERY_WINDOW_EXPIRED', status=409)
    championship.status = ChampionshipStatus.CLOSED
    championship.deletion_requested_at = None
    championship.purge_after = None
    _audit(current_user, 'CHAMPIONSHIP_RECOVERED', championship, 'CHAMPIONSHIP', championship.id)
    db.session.commit()
    return jsonify({'championship': championship_response(championship)})


def purge_expired_championships(now=None):
    """Permanently remove only records whose two-week grace period elapsed."""
    timestamp = now or datetime.now(timezone.utc)
    expired = db.session.execute(select(Championship).where(
        Championship.status == ChampionshipStatus.PENDING_DELETION,
        Championship.purge_after <= timestamp,
    )).scalars().all()
    from app.models import FileObject
    purged = []
    for championship in expired:
        files = db.session.execute(select(FileObject).where(
            FileObject.championship_id == championship.id
        )).scalars().all()
        for file_object in files:
            delete_object(file_object.bucket_object)
        purged.append(str(championship.id))
        db.session.delete(championship)
    db.session.commit()
    return purged
