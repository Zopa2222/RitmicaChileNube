from datetime import date, datetime, timezone

import pytest
from app.security import access


@pytest.fixture(autouse=True)
def fixed_shift_time(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(access, 'datetime', Clock)

from flask import jsonify
from flask_jwt_extended import decode_token
from sqlalchemy import select

from app import create_app
from app.extensions import db, limiter
from app.models import (
    AccountType,
    AuditLog,
    Bench,
    Category,
    Championship,
    ChampionshipStatus,
    CompetitionDay,
    JudgeAssignment,
    JudgeRole,
    Session,
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


def create_active_judge_assignment(
    admin,
    judge,
    status=ChampionshipStatus.ACTIVE,
):
    championship = Championship(
        name='Clasificatorio Centro',
        kind='CLASIFICATORIO',
        zone='CENTRO',
        start_date=date(2026, 8, 1),
        status=status,
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
    category = Category(
        championship_id=championship.id,
        competition_day_id=competition_day.id,
        name='Senior',
        bench=Bench.A,
        session=Session.AM,
        passing_order=0,
    )
    db.session.add(category)
    db.session.flush()
    db.session.add(JudgeAssignment(
        championship_id=championship.id,
        judge_user_id=judge.id,
        competition_day_id=competition_day.id,
        bench=Bench.A,
        session=Session.AM,
        role=JudgeRole.A,
        effective_from_category_id=category.id,
        assigned_by_user_id=admin.id,
    ))
    db.session.commit()
    return championship


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


def test_judge_can_reconnect_throughout_active_or_paused_championship(
    app,
    client,
):
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
    assert denied.get_json()['code'] == 'JUDGE_ACCESS_NOT_AVAILABLE'

    championship = create_active_judge_assignment(admin, judge)

    allowed = login(client, username='JUEZ1')
    assert allowed.status_code == 200
    assert client.get('/api/v1/test/judge-only').status_code == 200

    championship.status = ChampionshipStatus.PAUSED
    db.session.commit()
    assert login(client, username='JUEZ1').status_code == 200
    assert client.get('/api/v1/test/judge-only').status_code == 200

    championship.status = ChampionshipStatus.CLOSED
    db.session.commit()
    closed = client.get('/api/v1/test/judge-only')
    assert closed.status_code == 403
    assert closed.get_json()['code'] == 'JUDGE_ACCESS_NOT_AVAILABLE'
    assert client.get('/api/v1/auth/me').status_code == 401


def test_judge_token_lasts_24_hours_and_admin_token_remains_8_hours(
    app,
    client,
):
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    judge = create_user(AccountType.JUDGE, 'JUEZ1', rut='111111111')
    create_active_judge_assignment(admin, judge)

    assert login(client, username='JUEZ1').status_code == 200
    judge_cookie = client.get_cookie('ritmica_access', path='/api/')
    judge_claims = decode_token(judge_cookie.value)
    assert judge_claims['exp'] - judge_claims['iat'] == 24 * 3600

    admin_client = app.test_client()
    assert login(admin_client, username='ADMIN').status_code == 200
    admin_cookie = admin_client.get_cookie('ritmica_access', path='/api/')
    admin_claims = decode_token(admin_cookie.value)
    assert admin_claims['exp'] - admin_claims['iat'] == 8 * 3600


def test_judge_shift_boundaries_and_existing_session_expiry(app, client):
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    judge = create_user(AccountType.JUDGE, 'JUEZ1', rut='111111111')
    create_active_judge_assignment(admin, judge)
    assignment = db.session.execute(select(JudgeAssignment)).scalar_one()
    # Chile in August: UTC-4. AM 08:00–16:00; PM 12:00–00:00.
    def allowed(hour):
        return access.judge_has_championship_access(
            judge.id, datetime(2026, 8, 1, hour, tzinfo=timezone.utc))
    assert not allowed(11)
    assert allowed(12)
    assert allowed(19)
    assert not allowed(20)
    assert login(client, username='JUEZ1').status_code == 200
    assignment.session = Session.PM
    db.session.commit()
    from app.services.championship_operations_service import recalculate_judge_access_window
    window = recalculate_judge_access_window(
        judge.id, db.session.get(Championship, assignment.championship_id),
        db.session.get(CompetitionDay, assignment.competition_day_id),
    )
    assert window.starts_at == datetime(2026, 8, 1, 16, tzinfo=timezone.utc)
    assert window.ends_at == datetime(2026, 8, 2, 4, tzinfo=timezone.utc)
    assert not allowed(12)
    assert not allowed(15)
    assert allowed(16)
    assert allowed(20)
    assert client.get('/api/v1/auth/me').status_code == 401
    db.session.add(JudgeAssignment(
        championship_id=assignment.championship_id, judge_user_id=judge.id,
        competition_day_id=assignment.competition_day_id, bench=Bench.A,
        session=Session.AM, role=JudgeRole.A,
        effective_from_category_id=assignment.effective_from_category_id,
        assigned_by_user_id=admin.id,
    ))
    db.session.commit()
    assert allowed(12) and allowed(20)
    assert not access.judge_has_championship_access(
        judge.id, datetime(2026, 8, 2, 4, tzinfo=timezone.utc))
    judge.status = UserStatus.DISABLED
    db.session.commit()
    assert login(client, username='JUEZ1').get_json()['code'] == 'ACCOUNT_DISABLED'


def rate_limited_test_app(ip_limit, username_limit):
    return create_app('testing', {
        'RATELIMIT_ENABLED': True,
        'LOGIN_IP_RATE_LIMIT': ip_limit,
        'LOGIN_USERNAME_FAILURE_RATE_LIMIT': username_limit,
    })


def test_login_rate_limits_shared_ip_without_combining_judge_attempts():
    rate_limited_app = rate_limited_test_app(
        '2 per minute',
        '10 per minute',
    )
    with rate_limited_app.app_context():
        db.create_all()
        limiter.reset()
        shared_network_client = rate_limited_app.test_client()

        first = login(shared_network_client, username='JUEZ1')
        second = login(shared_network_client, username='JUEZ2')
        third = login(shared_network_client, username='JUEZ3')

        assert first.status_code == 401
        assert second.status_code == 401
        assert third.status_code == 429
        db.session.remove()
        db.drop_all()


def test_login_rate_limits_failed_attempts_for_one_account():
    rate_limited_app = rate_limited_test_app(
        '10 per minute',
        '2 per minute',
    )
    with rate_limited_app.app_context():
        db.create_all()
        limiter.reset()
        client = rate_limited_app.test_client()

        first = login(client, username='JUEZ1')
        second = login(client, username='JUEZ1')
        third = login(client, username='JUEZ1')

        assert first.status_code == 401
        assert second.status_code == 401
        assert third.status_code == 429
        db.session.remove()
        db.drop_all()


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
