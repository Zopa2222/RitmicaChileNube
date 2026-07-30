from io import BytesIO

import openpyxl
from sqlalchemy import select

from app.extensions import db
from app.models import (
    AccountType,
    AuditLog,
    Category,
    CompetitionDay,
    Gymnast,
    User,
)
from app.security.passwords import hash_password


def create_admin():
    admin = User(
        account_type=AccountType.GLOBAL_ADMIN,
        first_name='Administrador',
        last_name='Global',
        username='ADMIN',
        password_hash=hash_password('Clave-Admin-123'),
    )
    db.session.add(admin)
    db.session.commit()
    return admin


def login_headers(client):
    response = client.post(
        '/api/v1/auth/login',
        json={'username': 'ADMIN', 'password': 'Clave-Admin-123'},
    )
    assert response.status_code == 200
    csrf_cookie = client.get_cookie('ritmica_csrf')
    return {'X-CSRF-TOKEN': csrf_cookie.value}


def small_excel():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = 'SABADO'
    sheet.append([
        'N', 'NOMBRE', 'CLUB', 'CATEGORIA',
        'N', 'NOMBRE', 'CLUB', 'CATEGORIA',
    ])
    sheet.append([
        1, 'Gimnasta A1', 'Club A', 'MINI A',
        1, 'Gimnasta B1', 'Club B', 'MINI B',
    ])
    sheet.append([
        2, 'Gimnasta A2', 'Club A', 'MINI A',
        2, 'Gimnasta B2', 'Club B', 'MINI B',
    ])
    sheet.append([
        'BREAK 1 HORA - PREMIACION - ALMUERZO JUECES',
        None, None, None, None, None, None, None,
    ])
    sheet.append([
        'N', 'NOMBRE', 'CLUB', 'CATEGORIA',
        'N', 'NOMBRE', 'CLUB', 'CATEGORIA',
    ])
    sheet.append([
        1, 'Gimnasta A3', 'Club A', 'JUNIOR A',
        1, 'Gimnasta B3', 'Club B', 'JUNIOR B',
    ])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    output.seek(0)
    return output


def test_admin_imports_preview_and_confirms_order_of_passage(app, client):
    create_admin()
    headers = login_headers(client)

    create_response = client.post(
        '/api/v1/championships',
        json={
            'name': 'Clasificatorio Centro',
            'kind': 'clasificatorio',
            'zone': 'centro',
            'start_date': '2026-08-01',
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    championship_id = create_response.get_json()['championship']['id']

    upload_response = client.post(
        f'/api/v1/championships/{championship_id}/import-previews',
        data={'file': (small_excel(), 'orden-centro.xlsx')},
        headers=headers,
        content_type='multipart/form-data',
    )
    assert upload_response.status_code == 201
    preview_payload = upload_response.get_json()
    preview_id = preview_payload['id']
    sheet = preview_payload['preview']['sheets'][0]
    assert sheet['detected_cutoff_row'] == 4
    assert sheet['selected_cutoff_row'] == 4
    assert not sheet['cutoff_confirmed']
    assert preview_payload['preview']['total_categories'] == 4
    assert preview_payload['preview']['total_gymnasts'] == 6

    premature = client.post(
        f'/api/v1/championships/{championship_id}'
        f'/import-previews/{preview_id}/confirm',
        headers=headers,
    )
    assert premature.status_code == 400
    assert premature.get_json()['code'] == 'UNCONFIRMED_CUTOFF'

    update_response = client.patch(
        f'/api/v1/championships/{championship_id}'
        f'/import-previews/{preview_id}',
        json={'accept_detected': True},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert (
        update_response.get_json()['preview']['sheets'][0]
        ['cutoff_confirmed']
    )

    confirmation = client.post(
        f'/api/v1/championships/{championship_id}'
        f'/import-previews/{preview_id}/confirm',
        headers=headers,
    )
    assert confirmation.status_code == 200
    assert confirmation.get_json()['imported'] == {
        'days': 1,
        'categories': 4,
        'gymnasts': 6,
    }
    assert db.session.execute(select(CompetitionDay)).scalars().all()
    assert len(db.session.execute(select(Category)).scalars().all()) == 4
    assert len(db.session.execute(select(Gymnast)).scalars().all()) == 6

    detail = client.get(
        f'/api/v1/championships/{championship_id}',
    )
    assert detail.status_code == 200
    assert detail.get_json()['championship']['counts'] == {
        'days': 1,
        'categories': 4,
        'gymnasts': 6,
    }

    actions = db.session.execute(
        select(AuditLog.action).order_by(AuditLog.occurred_at)
    ).scalars().all()
    assert actions == [
        'LOGIN_SUCCESS',
        'CHAMPIONSHIP_CREATED',
        'IMPORT_PREVIEW_CREATED',
        'IMPORT_CUTOFFS_UPDATED',
        'IMPORT_CONFIRMED',
    ]


def test_cloud_championship_routes_require_login(client):
    response = client.get('/api/v1/championships')

    assert response.status_code == 401
    assert response.get_json()['code'] == 'AUTHENTICATION_REQUIRED'
