from datetime import date

from app.extensions import db
from app.models import (
    AccountType,
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


def login(client):
    response = client.post('/api/v1/auth/login', json={
        'username': 'SUPER', 'password': PASSWORD,
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
    assert regenerated.get_json()['credentials']['password']

    disabled = client.delete(f'/api/v1/admin/judges/{judge_id}', headers=headers)
    assert disabled.status_code == 200
    assert disabled.get_json()['judge']['status'] == 'DISABLED'

    logs = client.get('/api/v1/admin/audit-logs')
    assert logs.status_code == 200
    assert {item['action'] for item in logs.get_json()['logs']} >= {
        'JUDGE_CREATED', 'JUDGE_CREDENTIALS_REGENERATED', 'JUDGE_DISABLED',
    }


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


def test_cloud_exports_use_normalized_results(app, client):
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
