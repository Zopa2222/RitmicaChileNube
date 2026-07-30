from datetime import date, datetime, timedelta, timezone

from flask import jsonify
from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import (
    AccountType,
    AuditLog,
    Championship,
    ChampionshipStatus,
    CompetitionDay,
    JudgeAccessWindow,
    SystemRole,
    User,
    UserStatus,
)
from app.security.passwords import hash_password
from app.security.permissions import account_types_required


def create_user(account_type, username, password='Clave-Segura-123', rut=None):
    user = User(
        account_type=account_type,
        first_name='Nombre',
        last_name='Apellido',
        rut_normalized=rut,
        username=username,
        password_hash=hash_password(password),
    )
    db.session.add(user)
    db.session.commit()
    return user


def login(client, username='ADMIN', password='Clave-Segura-123'):
    return client.post(
        '/api/v1/auth/login',
        json={'username': username, 'password': password},
    )


def test_admin_can_login_read_session_and_logout(app, client):
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')

    response = login(client)

    assert response.status_code == 200
    assert response.get_json()['user'] == {
        'id': str(admin.id),
        'username': 'ADMIN',
        'first_name': 'Nombre',
        'last_name': 'Apellido',
        'account_type': 'GLOBAL_ADMIN',
    }
    access_cookie = client.get_cookie('ritmica_access', path='/api/')
    csrf_cookie = client.get_cookie('ritmica_csrf')
    assert access_cookie is not None
    assert access_cookie.http_only
    assert csrf_cookie is not None

    me_response = client.get('/api/v1/auth/me')
    assert me_response.status_code == 200
    assert me_response.get_json()['user']['id'] == str(admin.id)

    logout_response = client.post(
        '/api/v1/auth/logout',
        headers={'X-CSRF-TOKEN': csrf_cookie.value},
    )
    assert logout_response.status_code == 204
    assert client.get('/api/v1/auth/me').status_code == 401

    actions = db.session.execute(
        select(AuditLog.action).order_by(AuditLog.occurred_at)
    ).scalars().all()
    assert actions == ['LOGIN_SUCCESS', 'LOGOUT']


def test_login_uses_generic_error_for_invalid_credentials(app, client):
    create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')

    response = login(client, password='incorrecta')

    assert response.status_code == 401
    assert response.get_json()['code'] == 'INVALID_CREDENTIALS'
    audit = db.session.execute(select(AuditLog)).scalar_one()
    assert audit.action == 'LOGIN_FAILED'
    assert audit.details['reason'] == 'INVALID_PASSWORD'


def test_disabled_account_cannot_login(app, client):
    user = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    user.status = UserStatus.DISABLED
    db.session.commit()

    response = login(client)

    assert response.status_code == 403
    assert response.get_json()['code'] == 'ACCOUNT_DISABLED'


def test_judge_requires_an_open_window_in_active_championship(app, client):
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    judge = create_user(
        AccountType.JUDGE,
        'JUEZ1',
        rut='111111111',
    )

    @app.get('/api/v1/test/judge-only')
    @account_types_required(AccountType.JUDGE)
    def judge_only(current_user):
        return jsonify({'id': str(current_user.id)})

    denied = login(client, username='JUEZ1')
    assert denied.status_code == 403
    assert denied.get_json()['code'] == 'ACCESS_WINDOW_CLOSED'

    championship = Championship(
        name='Clasificatorio Centro',
        kind='CLASIFICATORIO',
        zone='CENTRO',
        start_date=date(2026, 8, 1),
        status=ChampionshipStatus.ACTIVE,
        responsible_admin_id=admin.id,
    )
    db.session.add(championship)
    db.session.flush()
    competition_day = CompetitionDay(
        championship_id=championship.id,
        sequence=1,
        competition_date=championship.start_date,
        source_sheet_name='SABADO',
    )
    db.session.add(competition_day)
    db.session.flush()

    now = datetime.now(timezone.utc)
    access_window = JudgeAccessWindow(
        judge_user_id=judge.id,
        championship_id=championship.id,
        competition_day_id=competition_day.id,
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=9),
    )
    db.session.add(access_window)
    db.session.commit()

    future = login(client, username='JUEZ1')
    assert future.status_code == 403
    assert (
        future.get_json()['next_access_window']['competition_day_id']
        == str(competition_day.id)
    )

    access_window.starts_at = now - timedelta(minutes=5)
    access_window.ends_at = now + timedelta(hours=8)
    db.session.commit()

    allowed = login(client, username='JUEZ1')
    assert allowed.status_code == 200
    assert client.get('/api/v1/test/judge-only').status_code == 200

    access_window.ends_at = now - timedelta(minutes=1)
    db.session.commit()
    expired = client.get('/api/v1/test/judge-only')
    assert expired.status_code == 403
    assert expired.get_json()['code'] == 'ACCESS_WINDOW_CLOSED'


def test_account_type_decorator_blocks_wrong_role(app):
    create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')

    @app.get('/api/v1/test/super-only')
    @account_types_required(AccountType.SUPER_ADMIN)
    def super_only(current_user):
        return jsonify({'id': str(current_user.id)})

    local_client = app.test_client()
    assert login(local_client).status_code == 200

    response = local_client.get('/api/v1/test/super-only')
    assert response.status_code == 403
    assert response.get_json()['code'] == 'FORBIDDEN'


def test_bootstrap_command_creates_exact_fixed_accounts(app):
    runner = app.test_cli_runner()

    result = runner.invoke(
        args=[
            'bootstrap-fixed-users',
            '--super-username',
            'SUPER',
            '--super-password',
            'Clave-Super-123',
            '--admin-username',
            'ADMIN',
            '--admin-password',
            'Clave-Admin-123',
        ]
    )

    assert result.exit_code == 0
    assert User.query.count() == 2
    roles = db.session.get(SystemRole, 1)
    assert roles is not None
    assert roles.super_admin_user_id != roles.global_admin_user_id


def test_production_does_not_expose_legacy_routes():
    production_app = create_app(
        'production',
        {
            'SQLALCHEMY_DATABASE_URI':
                'postgresql+psycopg://user:password@localhost/database',
            'JWT_SECRET_KEY': 'production-test-secret',
            'GCS_BUCKET': 'test-bucket',
        },
    )

    rules = {rule.rule for rule in production_app.url_map.iter_rules()}
    assert '/api/v1/auth/login' in rules
    assert '/campeonatos' not in rules
