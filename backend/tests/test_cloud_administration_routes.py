from datetime import date
import uuid

from app.extensions import db
from app.services import cloud_export_service
from app.models import (
    AccountType,
    AuditLog,
    Championship,
    ChampionshipStatus,
    CompetitionDay,
    Category,
    Gymnast,
    User,
    Bench,
    Session,
)
from app.security.passwords import hash_password
from app.security.judge_links import token_digest


PASSWORD = 'Clave-Segura-123'


def create_super():
    user = User(
        account_type=AccountType.SUPER_ADMIN,
        first_name='Super',
        last_name='Admin',
        username='SUPER',
        password_hash=hash_password(PASSWORD),
    )
    db.session.add(user)
    db.session.commit()
    return user


def create_global_admin():
    user = User(
        account_type=AccountType.GLOBAL_ADMIN,
        first_name='Global',
        last_name='Admin',
        username='ADMIN',
        password_hash=hash_password(PASSWORD),
    )
    db.session.add(user)
    db.session.commit()
    return user


def login(client, username='SUPER'):
    response = client.post('/api/v1/auth/login', json={
        'username': username, 'password': PASSWORD,
    })
    assert response.status_code == 200
    return {'X-CSRF-TOKEN': client.get_cookie('ritmica_csrf').value}


def test_super_admin_manages_judges_and_credentials(app, client):
    create_super()
    headers = login(client)

    created = client.post('/api/v1/admin/judges', headers=headers, json={
        'first_name': 'María', 'last_name': 'Pérez', 'rut': '12.345.678-5',
    })
    assert created.status_code == 201
    payload = created.get_json()
    judge_id = payload['judge']['id']
    assert payload['credentials']['username'] == 'MARIAPEREZ123456785'

    regenerated = client.post(
        f'/api/v1/admin/judges/{judge_id}/credentials/regenerate', headers=headers,
    )
    assert regenerated.status_code == 200
    assert regenerated.get_json()['credentials']['access_path']

    deactivated = client.post(
        f'/api/v1/admin/judges/{judge_id}/deactivate', headers=headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.get_json()['judge']['status'] == 'DISABLED'

    activated = client.post(
        f'/api/v1/admin/judges/{judge_id}/activate', headers=headers,
    )
    assert activated.status_code == 200
    assert activated.get_json()['judge']['status'] == 'ACTIVE'

    deleted = client.delete(f'/api/v1/admin/judges/{judge_id}', headers=headers)
    assert deleted.status_code == 204
    assert db.session.get(User, uuid.UUID(judge_id)) is None

    logs = client.get('/api/v1/admin/audit-logs')
    assert logs.status_code == 200
    assert {item['action'] for item in logs.get_json()['logs']} >= {
        'JUDGE_CREATED', 'JUDGE_CREDENTIALS_REGENERATED',
        'JUDGE_DEACTIVATED', 'JUDGE_ACTIVATED', 'JUDGE_DELETED',
    }


def test_global_admin_manages_judges_and_credentials(app, client):
    create_global_admin()
    headers = login(client, 'ADMIN')

    listed = client.get('/api/v1/admin/judges', headers=headers)
    assert listed.status_code == 200

    created = client.post('/api/v1/admin/judges', headers=headers, json={
        'first_name': 'Valentina', 'last_name': 'Rojas', 'rut': '12.345.678-5',
    })
    assert created.status_code == 201
    judge_id = created.get_json()['judge']['id']

    updated = client.patch(
        f'/api/v1/admin/judges/{judge_id}', headers=headers,
        json={'first_name': 'Vale'},
    )
    assert updated.status_code == 200
    assert updated.get_json()['judge']['first_name'] == 'Vale'

    regenerated = client.post(
        f'/api/v1/admin/judges/{judge_id}/credentials/regenerate', headers=headers,
    )
    assert regenerated.status_code == 200
    assert regenerated.get_json()['credentials']['access_path']

    deactivated = client.post(
        f'/api/v1/admin/judges/{judge_id}/deactivate', headers=headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.get_json()['judge']['status'] == 'DISABLED'

    activated = client.post(
        f'/api/v1/admin/judges/{judge_id}/activate', headers=headers,
    )
    assert activated.status_code == 200
    assert activated.get_json()['judge']['status'] == 'ACTIVE'

    batch = client.post(
        '/api/v1/admin/judges/credentials/regenerate-batch', headers=headers,
        json={'judge_ids': [judge_id]},
    )
    assert batch.status_code == 200
    assert batch.get_json()['items'][0]['judge']['id'] == judge_id

    deleted = client.delete(f'/api/v1/admin/judges/{judge_id}', headers=headers)
    assert deleted.status_code == 204


def test_audit_logs_include_the_championship_name(app, client):
    super_admin = create_super()
    championship = Championship(
        name='Final Nacional', kind='FINAL', zone='NACIONAL',
        start_date=date(2026, 8, 1), status=ChampionshipStatus.PAUSED,
        responsible_admin_id=super_admin.id,
    )
    db.session.add(championship)
    db.session.flush()
    db.session.add(AuditLog(
        actor_user_id=super_admin.id,
        action='CHAMPIONSHIP_PAUSED',
        championship_id=championship.id,
        entity_type='CHAMPIONSHIP',
        entity_id=championship.id,
    ))
    db.session.commit()
    headers = login(client)

    logs = client.get('/api/v1/admin/audit-logs', headers=headers)

    paused_log = next(
        log for log in logs.get_json()['logs']
        if log['action'] == 'CHAMPIONSHIP_PAUSED'
    )
    assert paused_log['championship'] == {
        'id': str(championship.id),
        'name': 'Final Nacional',
    }


def test_super_admin_regenerates_selected_judges_atomically(app, client):
    create_super()
    headers = login(client)
    first = client.post('/api/v1/admin/judges', headers=headers, json={
        'first_name': 'María', 'last_name': 'Pérez', 'rut': '12.345.678-5',
    }).get_json()
    second = client.post('/api/v1/admin/judges', headers=headers, json={
        'first_name': 'Ana', 'last_name': 'Soto', 'rut': '11.111.111-1',
    }).get_json()

    original_link = first['credentials']['access_path']
    first_id = first['judge']['id']
    second_id = second['judge']['id']
    invalid_batch = client.post(
        '/api/v1/admin/judges/credentials/regenerate-batch',
        headers=headers,
        json={'judge_ids': [first_id, str(uuid.uuid4())]},
    )
    assert invalid_batch.status_code == 404
    first_user = db.session.get(User, uuid.UUID(first_id))
    assert first_user.judge_access_token_hash == token_digest(original_link.split('#')[1])

    regenerated = client.post(
        '/api/v1/admin/judges/credentials/regenerate-batch',
        headers=headers,
        json={'judge_ids': [second_id, first_id]},
    )
    assert regenerated.status_code == 200
    items = regenerated.get_json()['items']
    assert [item['judge']['id'] for item in items] == [second_id, first_id]
    assert all(item['credentials']['access_path'] for item in items)
    assert not first_user.judge_access_token_hash == token_digest(original_link.split('#')[1])

    duplicate = client.post(
        '/api/v1/admin/judges/credentials/regenerate-batch',
        headers=headers,
        json={'judge_ids': [first_id, first_id]},
    )
    assert duplicate.status_code == 400


def test_championship_deletion_requires_three_confirmations_and_recovers(app, client):
    super_admin = create_super()
    championship = Championship(
        name='Final Centro', kind='FINAL', zone='CENTRO',
        start_date=date(2026, 8, 1), status=ChampionshipStatus.CLOSED,
        responsible_admin_id=super_admin.id,
    )
    db.session.add(championship)
    db.session.commit()
    headers = login(client)

    wrong_order = client.post(
        f'/api/v1/championships/{championship.id}/deletion-confirmations',
        headers=headers, json={'step': 2},
    )
    assert wrong_order.status_code == 409
    for step in (1, 2, 3):
        response = client.post(
            f'/api/v1/championships/{championship.id}/deletion-confirmations',
            headers=headers, json={'step': step},
        )
        assert response.status_code == 200
    assert response.get_json()['championship']['status'] == 'PENDING_DELETION'

    recovered = client.post(
        f'/api/v1/championships/{championship.id}/recover', headers=headers,
    )
    assert recovered.status_code == 200
    assert recovered.get_json()['championship']['status'] == 'CLOSED'


def test_cloud_exports_use_normalized_results(app, client, monkeypatch):
    super_admin = create_super()
    championship = Championship(
        name='Exportable', kind='FINAL', zone='CENTRO',
        start_date=date(2026, 8, 1), status=ChampionshipStatus.CLOSED,
        responsible_admin_id=super_admin.id,
    )
    db.session.add(championship)
    db.session.flush()
    day = CompetitionDay(
        championship_id=championship.id, sequence=1,
        competition_date=championship.start_date, source_sheet_name='SABADO',
    )
    db.session.add(day)
    db.session.flush()
    category = Category(
        championship_id=championship.id, competition_day_id=day.id,
        name='MINI', bench=Bench.A, session=Session.AM, passing_order=0,
    )
    db.session.add(category)
    db.session.flush()
    db.session.add(Gymnast(
        category_id=category.id, full_name='Gimnasta', club_name='Club',
        passing_order=0,
    ))
    db.session.commit()
    headers = login(client)

    captured_tables = []
    original_table = cloud_export_service.Table

    def capture_table(rows, *args, **kwargs):
        captured_tables.append(rows)
        return original_table(rows, *args, **kwargs)

    monkeypatch.setattr(cloud_export_service, 'Table', capture_table)

    excel = client.get(
        f'/api/v1/championships/{championship.id}/exports/excel', headers=headers,
    )
    pdf = client.get(
        f'/api/v1/championships/{championship.id}/exports/pdf', headers=headers,
    )
    assert excel.status_code == 200
    assert excel.mimetype.endswith('spreadsheetml.sheet')
    assert pdf.status_code == 200
    assert pdf.mimetype == 'application/pdf'
    assert captured_tables[0][0] == [
        'Pos.', 'Nombre', 'Club', 'DB', 'DA', 'Desc.', 'Total',
    ]
