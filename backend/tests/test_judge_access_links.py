from datetime import datetime, timedelta, timezone

import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy import select

from app.extensions import db, limiter
from app.models import AccountType, AuditLog, ChampionshipStatus, JudgeAccessWindow, UserStatus
from app.security import access
from app.security.judge_links import issue_judge_link, token_digest
from test_judge_cabin_routes import create_cabin_context, JUDGE_PASSWORD


def issue(judge):
    credentials = issue_judge_link(judge)
    db.session.commit()
    assert 'password' not in credentials
    return credentials['access_path'].split('#')[1]


def enter(client, token):
    return client.post('/api/v1/auth/judge/link', json={'token': token})


def test_link_reusable_and_judge_cannot_use_password_or_admin_functions(app, client):
    context = create_cabin_context()
    judge = context['judge_a']
    token = issue(judge)
    assert judge.judge_access_token_hash == token_digest(token)
    assert token not in judge.judge_access_token_hash
    for path in ('/api/v1/auth/login', '/api/v1/auth/admin/login'):
        response = client.post(path, json={'username': judge.username, 'password': JUDGE_PASSWORD})
        assert response.status_code == 401
    for _ in range(2):
        response = enter(client, token)
        assert response.status_code == 200
        assert response.headers['Cache-Control'] == 'no-store'
    assert client.get('/api/v1/judge/contexts').status_code == 200
    assert client.get('/api/v1/admin/judges').status_code == 403
    csrf = {'X-CSRF-TOKEN': client.get_cookie('ritmica_csrf').value}
    assert client.post('/api/v1/admin/judges', headers=csrf, json={}).status_code == 403
    assert client.post(f'/api/v1/admin/judges/{judge.id}/access-link', headers=csrf).status_code == 403
    assert client.get('/api/v1/admin/audit-logs').status_code == 403
    audits = db.session.execute(select(AuditLog)).scalars().all()
    assert all(token not in str(log.details) for log in audits)


def test_admin_can_issue_link_and_rotation_revokes_previous_sessions(app, client):
    context = create_cabin_context()
    judge = context['judge_a']
    old_token = issue(judge)
    assert enter(client, old_token).status_code == 200
    admin_client = app.test_client()
    assert admin_client.post('/api/v1/auth/admin/login', json={
        'username': context['admin'].username, 'password': JUDGE_PASSWORD,
    }).status_code == 200
    assert admin_client.get('/api/v1/judge/contexts').status_code == 403
    path = f'/api/v1/admin/judges/{judge.id}/access-link'
    assert admin_client.post(path).status_code == 401  # CSRF required
    response = admin_client.post(path, headers={
        'X-CSRF-TOKEN': admin_client.get_cookie('ritmica_csrf').value,
    })
    assert response.status_code == 200
    assert 'password' not in response.get_json()['credentials']
    new_token = response.get_json()['credentials']['access_path'].split('#')[1]
    assert client.get('/api/v1/auth/me').status_code == 401
    assert client.get('/api/v1/judge/contexts').status_code == 401
    assert enter(client, old_token).status_code == 401
    assert enter(client, new_token).status_code == 200


@pytest.mark.parametrize('status', [UserStatus.DISABLED, UserStatus.LOCKED])
def test_manual_deactivation_overrides_active_assignment(app, client, status):
    context = create_cabin_context()
    judge = context['judge_a']
    token = issue(judge)
    assert enter(client, token).status_code == 200
    judge.status = status
    db.session.commit()
    assert client.get('/api/v1/auth/me').status_code == 401
    assert client.get('/api/v1/judge/contexts').status_code == 401
    assert enter(client, token).get_json()['code'] == 'ACCOUNT_DISABLED'


def test_same_link_works_on_assigned_days_and_stops_at_window_end(app, client, monkeypatch):
    context = create_cabin_context()
    judge = context['judge_a']
    token = issue(judge)
    window = db.session.execute(select(JudgeAccessWindow).where(
        JudgeAccessWindow.judge_user_id == judge.id,
    )).scalar_one()
    start = datetime.now(timezone.utc)
    window.starts_at = start
    window.ends_at = start + timedelta(hours=8)
    db.session.commit()

    class Clock(datetime):
        value = start - timedelta(seconds=1)

        @classmethod
        def now(cls, tz=None):
            return cls.value

    monkeypatch.setattr(access, 'datetime', Clock)
    assert enter(client, token).status_code == 403
    Clock.value = start
    assert enter(client, token).status_code == 200
    Clock.value = start + timedelta(hours=8)
    assert client.get('/api/v1/judge/contexts').status_code == 403
    assert enter(client, token).status_code == 403
    # Scheduling another turn does not require replacing the personal link.
    window.starts_at = start + timedelta(days=1)
    window.ends_at = start + timedelta(days=1, hours=8)
    db.session.commit()
    Clock.value = start + timedelta(days=1, hours=1)
    assert enter(client, token).status_code == 200
    context['championship'].status = ChampionshipStatus.CLOSED
    db.session.commit()
    assert enter(client, token).status_code == 403
    assert client.get('/api/v1/auth/me').status_code == 401


def test_removed_assignments_deny_access_even_with_stale_window(app, client):
    context = create_cabin_context()
    token = issue(context['judge_a'])
    assert enter(client, token).status_code == 200
    for key in ('assignment_a', 'assignment_plan'):
        context[key].superseded_at = datetime.now(timezone.utc)
    db.session.commit()
    assert enter(client, token).status_code == 403
    assert client.get('/api/v1/judge/contexts').status_code == 403


@pytest.mark.parametrize('payload', [None, [], {'token': None}, {'token': 'x' * 43}, {'token': 1}, {'token': '../abc'}])
def test_malformed_and_unknown_links_fail_without_session(app, client, payload):
    response = client.post('/api/v1/auth/judge/link', json=payload)
    assert response.status_code == 401
    assert response.get_json()['code'] == 'INVALID_JUDGE_LINK'
    assert client.get_cookie('ritmica_access', path='/api/') is None


def test_admin_never_authenticates_via_link_and_old_judge_jwt_rejected(app, client):
    context = create_cabin_context()
    with pytest.raises(ValueError):
        issue(context['admin'])
    token = issue(context['judge_a'])
    context['admin'].judge_access_token_hash = token_digest('a' * 43)
    db.session.commit()
    assert enter(client, 'a' * 43).status_code == 401
    legacy_session = create_access_token(identity=str(context['judge_a'].id),
                                         additional_claims={'account_type': 'JUDGE'})
    client.set_cookie('ritmica_access', legacy_session, path='/api/')
    assert client.get('/api/v1/judge/contexts').status_code == 401
    assert enter(client, token).status_code == 200


def test_link_attempts_are_rate_limited():
    from app import create_app
    application = create_app('testing', {
        'RATELIMIT_ENABLED': True, 'LOGIN_IP_RATE_LIMIT': '2 per minute',
    })
    with application.app_context():
        db.create_all()
        limiter.reset()
        client = application.test_client()
        try:
            assert enter(client, 'a' * 43).status_code == 401
            assert enter(client, 'b' * 43).status_code == 401
            assert enter(client, 'c' * 43).status_code == 429
        finally:
            db.session.remove()
            db.drop_all()
            limiter.reset()


def test_import_delivers_working_links_instead_of_passwords(app, client, monkeypatch):
    from io import BytesIO
    import openpyxl
    from app.models import Championship, User
    from test_cloud_championship_routes import create_admin, login_headers, small_excel

    create_admin()
    headers = login_headers(client)
    created = client.post('/api/v1/championships', headers=headers, json={
        'name': 'Campeonato enlaces', 'kind': 'CLASIFICATORIO',
        'qualifier_number': 1, 'zone': 'CENTRO', 'start_date': '2026-08-01',
    })
    championship_id = created.get_json()['championship']['id']
    workbook = openpyxl.load_workbook(small_excel())
    judges = workbook.create_sheet('Jueces')
    judges.append(['JORNADA AM'])
    judges.append(['NOMBRE', 'RUT', 'AREA', 'NOMBRE', 'RUT', 'AREA'])
    judges.append(['Maria Perez', '12.345.678-5', 'A', None, None, None])
    contents = BytesIO()
    workbook.save(contents)
    workbook.close()
    contents.seek(0)
    uploaded = client.post(f'/api/v1/championships/{championship_id}/import-previews',
        headers=headers, data={'competition_date': '2026-08-01',
                               'file': (contents, 'dia.xlsx')})
    assert uploaded.status_code == 201, uploaded.get_json()
    preview_id = uploaded.get_json()['id']
    preview_path = f'/api/v1/championships/{championship_id}/import-previews/{preview_id}'
    assert client.patch(preview_path, headers=headers,
                        json={'accept_detected': True}).status_code == 200
    confirmed = client.post(f'{preview_path}/confirm', headers=headers)
    assert confirmed.status_code == 200, confirmed.get_json()
    credentials = confirmed.get_json()['imported']['new_judge_credentials']
    assert len(credentials) == 1
    assert 'password' not in credentials[0]
    token = credentials[0]['access_path'].split('#')[1]
    judge = db.session.execute(select(User).where(User.account_type == AccountType.JUDGE)).scalar_one()
    assert judge.judge_access_token_hash == token_digest(token)
    judge_client = app.test_client()
    assert enter(judge_client, token).status_code == 403  # Still a draft
    championship = db.session.execute(select(Championship)).scalar_one()
    championship.status = ChampionshipStatus.ACTIVE
    window = db.session.execute(select(JudgeAccessWindow)).scalar_one()
    starts_at = window.starts_at.replace(tzinfo=timezone.utc)
    db.session.commit()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return starts_at + timedelta(minutes=1)

    monkeypatch.setattr(access, 'datetime', Clock)
    assert enter(judge_client, token).status_code == 200
    assert judge_client.get('/api/v1/judge/contexts').status_code == 200
