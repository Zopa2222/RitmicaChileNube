import uuid
from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from app.extensions import db
from app.models import AccountType, User, UserStatus
from app.security.access import judge_has_championship_access


def get_authenticated_user():
    identity = get_jwt_identity()
    try:
        user_id = uuid.UUID(identity)
    except (TypeError, ValueError, AttributeError):
        return None

    user = db.session.get(User, user_id)
    if user is None:
        return None
    if user.status != UserStatus.ACTIVE:
        return None
    if user.account_type == AccountType.JUDGE:
        claims = get_jwt()
        if (
            claims.get('auth_method') != 'judge_link'
            or not user.judge_access_version
            or claims.get('judge_access_version') != user.judge_access_version
        ):
            return None
    return user


def account_types_required(*allowed_account_types):
    allowed = {
        account_type
        if isinstance(account_type, AccountType)
        else AccountType(account_type)
        for account_type in allowed_account_types
    }

    def decorator(view_function):
        @wraps(view_function)
        @jwt_required()
        def wrapped(*args, **kwargs):
            user = get_authenticated_user()
            if user is None:
                return jsonify({
                    'error': 'Sesión inválida o cuenta deshabilitada',
                    'code': 'AUTHENTICATION_REQUIRED',
                }), 401
            if user.account_type not in allowed:
                return jsonify({
                    'error': 'No tiene permisos para realizar esta acción',
                    'code': 'FORBIDDEN',
                }), 403
            if (
                user.account_type == AccountType.JUDGE
                and not judge_has_championship_access(user.id)
            ):
                return jsonify({
                    'error': (
                        'El juez no tiene una asignación vigente en un '
                        'campeonato en curso'
                    ),
                    'code': 'JUDGE_ACCESS_NOT_AVAILABLE',
                }), 403
            return view_function(user, *args, **kwargs)

        return wrapped

    return decorator
