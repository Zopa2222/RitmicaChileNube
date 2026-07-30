from datetime import datetime, timezone

from flask import Blueprint, jsonify, make_response, request
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
)
from sqlalchemy import select

from app.extensions import db, limiter
from app.models import (
    AccountType,
    AuditLog,
    User,
    UserStatus,
)
from app.security.access import (
    judge_has_open_access_window,
    next_judge_access_window,
)
from app.security.passwords import hash_password, verify_password
from app.security.permissions import get_authenticated_user


bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')


def serialize_user(user):
    return {
        'id': str(user.id),
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'account_type': user.account_type.value,
    }


def record_login_event(action, user=None, reason=None):
    details = {
        'ip': request.remote_addr,
        'user_agent': request.user_agent.string[:255],
    }
    if reason:
        details['reason'] = reason
    db.session.add(
        AuditLog(
            actor_user_id=user.id if user else None,
            action=action,
            entity_type='USER',
            entity_id=user.id if user else None,
            details=details,
        )
    )


@bp.post('/login')
@limiter.limit('5 per minute;20 per hour')
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get('username', '')).strip().upper()
    password = payload.get('password')

    if not username or not isinstance(password, str):
        record_login_event('LOGIN_FAILED', reason='INVALID_PAYLOAD')
        db.session.commit()
        return jsonify({
            'error': 'Usuario o contraseña incorrectos',
            'code': 'INVALID_CREDENTIALS',
        }), 401

    user = db.session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if user is None:
        record_login_event('LOGIN_FAILED', reason='UNKNOWN_USERNAME')
        db.session.commit()
        return jsonify({
            'error': 'Usuario o contraseña incorrectos',
            'code': 'INVALID_CREDENTIALS',
        }), 401

    valid_password, needs_rehash = verify_password(
        user.password_hash,
        password,
    )
    if not valid_password:
        record_login_event(
            'LOGIN_FAILED',
            user=user,
            reason='INVALID_PASSWORD',
        )
        db.session.commit()
        return jsonify({
            'error': 'Usuario o contraseña incorrectos',
            'code': 'INVALID_CREDENTIALS',
        }), 401

    if user.status != UserStatus.ACTIVE:
        record_login_event(
            'LOGIN_FAILED',
            user=user,
            reason='ACCOUNT_DISABLED',
        )
        db.session.commit()
        return jsonify({
            'error': 'La cuenta no está habilitada',
            'code': 'ACCOUNT_DISABLED',
        }), 403

    now = datetime.now(timezone.utc)
    if (
        user.account_type == AccountType.JUDGE
        and not judge_has_open_access_window(user.id, now)
    ):
        next_window = next_judge_access_window(user.id, now)
        record_login_event(
            'LOGIN_FAILED',
            user=user,
            reason='ACCESS_WINDOW_CLOSED',
        )
        db.session.commit()
        return jsonify({
            'error': 'El juez no tiene una ventana de acceso vigente',
            'code': 'ACCESS_WINDOW_CLOSED',
            'next_access_window': (
                {
                    'championship_id': str(next_window.championship_id),
                    'competition_day_id': str(
                        next_window.competition_day_id
                    ),
                    'starts_at': next_window.starts_at.isoformat(),
                    'ends_at': next_window.ends_at.isoformat(),
                }
                if next_window else None
            ),
        }), 403

    if needs_rehash:
        user.password_hash = hash_password(password)
    user.last_login_at = now
    record_login_event('LOGIN_SUCCESS', user=user)
    db.session.commit()

    token = create_access_token(
        identity=str(user.id),
        additional_claims={'account_type': user.account_type.value},
    )
    response = make_response(jsonify({'user': serialize_user(user)}))
    set_access_cookies(response, token)
    return response


@bp.post('/logout')
@jwt_required()
def logout():
    user = get_authenticated_user()
    if user is not None:
        db.session.add(
            AuditLog(
                actor_user_id=user.id,
                action='LOGOUT',
                entity_type='USER',
                entity_id=user.id,
                details={'ip': request.remote_addr},
            )
        )
        db.session.commit()

    response = make_response('', 204)
    unset_jwt_cookies(response)
    return response


@bp.get('/me')
@jwt_required()
def me():
    user = get_authenticated_user()
    if user is None:
        return jsonify({
            'error': 'Sesión inválida o cuenta deshabilitada',
            'code': 'AUTHENTICATION_REQUIRED',
        }), 401
    return jsonify({'user': serialize_user(user)})
