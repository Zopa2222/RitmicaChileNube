from datetime import date, datetime, timedelta, timezone
import uuid

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    AccountType,
    AuditLog,
    Bench,
    BenchActivation,
    Category,
    Championship,
    ChampionshipStatus,
    CompetitionDay,
    Gymnast,
    JudgeAccessWindow,
    JudgeAssignment,
    JudgeRole,
    PublicationBatch,
    PublishedResult,
    ScoreEntry,
    Session,
    SubmissionStatus,
    User,
)
from app.security.passwords import hash_password
from app.services.cloud_scoring_service import submit_administrator_score


PASSWORD = 'Clave-Admin-123'


def create_user(account_type, username):
    rut = (
        f'{10_000_000 + int(username.removeprefix("JUEZ"))}'
        if account_type == AccountType.JUDGE
        else None
    )
    user = User(
        account_type=account_type,
        first_name=username,
        last_name='Prueba',
        rut_normalized=rut,
        username=username,
        password_hash=hash_password(PASSWORD),
    )
    db.session.add(user)
    db.session.flush()
    return user


def login(client, username):
    response = client.post(
        '/api/v1/auth/login',
        json={'username': username, 'password': PASSWORD},
    )
    assert response.status_code == 200
    return {'X-CSRF-TOKEN': client.get_cookie('ritmica_csrf').value}


def create_scoring_context():
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
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
    day = CompetitionDay(
        championship_id=championship.id,
        sequence=1,
        competition_date=championship.start_date,
        source_sheet_name='SABADO',
    )
    db.session.add(day)
    db.session.flush()
    category = Category(
        championship_id=championship.id,
        competition_day_id=day.id,
        name='JUNIOR A',
        bench=Bench.A,
        session=Session.AM,
        passing_order=0,
    )
    db.session.add(category)
    db.session.flush()
    gymnasts = []
    for passing_order, name in enumerate(('Gimnasta Uno', 'Gimnasta Dos')):
        gymnast = Gymnast(
            category_id=category.id,
            full_name=name,
            club_name='Club Prueba',
            passing_order=passing_order,
        )
        db.session.add(gymnast)
        db.session.flush()
        gymnasts.append(gymnast)

    assignments = []
    for index, role in enumerate((
        JudgeRole.DA,
        JudgeRole.DA,
        JudgeRole.DB,
        JudgeRole.DB,
        JudgeRole.A,
        JudgeRole.A,
        JudgeRole.E,
        JudgeRole.E,
    )):
        judge = create_user(AccountType.JUDGE, f'JUEZ{index + 1}')
        assignment = JudgeAssignment(
            championship_id=championship.id,
            judge_user_id=judge.id,
            competition_day_id=day.id,
            bench=Bench.A,
            session=Session.AM,
            role=role,
            effective_from_category_id=category.id,
            assigned_by_user_id=admin.id,
        )
        db.session.add(assignment)
        db.session.flush()
        assignments.append(assignment)
        for gymnast in gymnasts:
            db.session.add(
                ScoreEntry(
                    gymnast_id=gymnast.id,
                    judge_assignment_id=assignment.id,
                )
            )
    db.session.commit()

    entries = db.session.execute(
        select(ScoreEntry)
        .where(ScoreEntry.gymnast_id == gymnasts[0].id)
        .order_by(ScoreEntry.created_at, ScoreEntry.id)
    ).scalars().unique().all()
    entries_by_role = {}
    for entry in entries:
        entries_by_role.setdefault(entry.assignment.role, []).append(entry)

    submitted_values = {
        JudgeRole.DA: ('5.20', '5.40'),
        JudgeRole.DB: ('3.10', '3.10'),
        JudgeRole.A: ('1.00', '1.61'),
        JudgeRole.E: ('2.00',),
    }
    minute = 0
    for role, values in submitted_values.items():
        for entry, value in zip(entries_by_role[role], values):
            submit_administrator_score(
                entry,
                value,
                admin.id,
                submitted_at=datetime(
                    2026,
                    8,
                    1,
                    12,
                    minute,
                    tzinfo=timezone.utc,
                ),
            )
            minute += 1
    db.session.commit()
    return {
        'admin': admin,
        'championship': championship,
        'day': day,
        'category': category,
        'gymnasts': gymnasts,
        'entries_by_role': entries_by_role,
    }


def submit_gymnast_scores(gymnast, admin, values_by_role):
    entries = db.session.execute(
        select(ScoreEntry)
        .where(ScoreEntry.gymnast_id == gymnast.id)
        .order_by(ScoreEntry.created_at, ScoreEntry.id)
    ).scalars().unique().all()
    entries_by_role = {}
    for entry in entries:
        entries_by_role.setdefault(entry.assignment.role, []).append(entry)
    for role, values in values_by_role.items():
        for entry, value in zip(entries_by_role[role], values):
            submit_administrator_score(entry, value, admin.id)
    db.session.commit()


def test_category_grid_exposes_pending_warnings_and_provisional_total(
    app,
    client,
):
    context = create_scoring_context()
    headers = login(client, context['admin'].username)

    response = client.get(
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/scoring",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['category']['bench'] == 'A'
    assert len(payload['assignments']) == 8
    assert all(item['scoring'] for item in payload['assignments'])
    first, second = payload['gymnasts']
    assert first['full_name'] == 'Gimnasta Uno'
    assert first['pending_count'] == 1
    assert first['area_warnings'] == {'A': True, 'E': False}
    assert first['role_resolutions']['DA'] == {
        'role': 'DA',
        'effective_value': '5.20',
        'first_received_value': '5.20',
        'source': 'AUTO',
        'has_discrepancy': True,
        'warning_active': True,
        'discrepancy_revision': 1,
        'acknowledged_revision': 0,
    }
    assert first['summary']['total_score'] == '26.00'
    assert first['summary']['calculation_status'] == 'PROVISIONAL'
    assert second['pending_count'] == 8
    assert second['summary']['total_score'] == '20.00'
    assert second['summary']['calculation_status'] == 'PROVISIONAL'


def test_admin_correction_zero_discount_and_idempotency(app, client):
    context = create_scoring_context()
    headers = login(client, context['admin'].username)
    pending_entry = context['entries_by_role'][JudgeRole.E][1]
    audit_count = db.session.scalar(select(func.count(AuditLog.id)))

    corrected = client.put(
        f"/api/v1/championships/{context['championship'].id}/"
        f'score-entries/{pending_entry.id}',
        json={'value': '0.00'},
        headers=headers,
    )
    assert corrected.status_code == 200
    assert corrected.get_json()['changed']
    assert corrected.get_json()['score']['submission_status'] == 'SUBMITTED'
    assert corrected.get_json()['summary']['total_score'] == '26.00'
    assert (
        corrected.get_json()['summary']['calculation_status']
        == 'COMPLETE'
    )

    repeated = client.put(
        f"/api/v1/championships/{context['championship'].id}/"
        f'score-entries/{pending_entry.id}',
        json={'value': 0},
        headers=headers,
    )
    assert repeated.status_code == 200
    assert not repeated.get_json()['changed']

    invalid = client.put(
        f"/api/v1/championships/{context['championship'].id}/"
        f'score-entries/{pending_entry.id}',
        json={'value': '1.155'},
        headers=headers,
    )
    assert invalid.status_code == 400
    assert invalid.get_json()['code'] == 'INVALID_SCORE'

    discount = client.put(
        f"/api/v1/championships/{context['championship'].id}/gymnasts/"
        f"{context['gymnasts'][0].id}/discount",
        json={'value': '1,15'},
        headers=headers,
    )
    assert discount.status_code == 200
    assert discount.get_json()['changed']
    assert discount.get_json()['summary']['discount'] == '1.15'
    assert discount.get_json()['summary']['total_score'] == '24.85'

    repeated_discount = client.put(
        f"/api/v1/championships/{context['championship'].id}/gymnasts/"
        f"{context['gymnasts'][0].id}/discount",
        json={'value': 1.15},
        headers=headers,
    )
    assert repeated_discount.status_code == 200
    assert not repeated_discount.get_json()['changed']

    invalid_discount = client.put(
        f"/api/v1/championships/{context['championship'].id}/gymnasts/"
        f"{context['gymnasts'][0].id}/discount",
        json={'value': 20.01},
        headers=headers,
    )
    assert invalid_discount.status_code == 400
    assert invalid_discount.get_json()['code'] == 'INVALID_DISCOUNT'
    assert db.session.scalar(select(func.count(AuditLog.id))) == audit_count


def test_admin_acknowledges_and_updates_da_discrepancy(app, client):
    context = create_scoring_context()
    headers = login(client, context['admin'].username)
    base = (
        f"/api/v1/championships/{context['championship'].id}/gymnasts/"
        f"{context['gymnasts'][0].id}/role-resolutions"
    )

    acknowledged = client.put(f'{base}/DA', json={}, headers=headers)
    assert acknowledged.status_code == 200
    assert acknowledged.get_json()['changed']
    assert acknowledged.get_json()['resolution']['source'] == 'ADMIN'
    assert not acknowledged.get_json()['resolution']['warning_active']
    assert (
        acknowledged.get_json()['resolution']['effective_value']
        == '5.20'
    )

    repeated = client.put(f'{base}/DA', json={}, headers=headers)
    assert repeated.status_code == 200
    assert not repeated.get_json()['changed']

    second_da = context['entries_by_role'][JudgeRole.DA][1]
    new_discrepancy = client.put(
        f"/api/v1/championships/{context['championship'].id}/"
        f'score-entries/{second_da.id}',
        json={'value': '5.60'},
        headers=headers,
    )
    assert new_discrepancy.status_code == 200

    resolved = client.put(
        f'{base}/DA',
        json={'value': '5.30'},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.get_json()['resolution']['effective_value'] == '5.30'
    assert not resolved.get_json()['resolution']['warning_active']
    assert resolved.get_json()['summary']['da_score'] == '5.30'
    assert resolved.get_json()['summary']['total_score'] == '26.10'

    no_discrepancy = client.put(f'{base}/DB', json={}, headers=headers)
    assert no_discrepancy.status_code == 409
    assert no_discrepancy.get_json()['code'] == 'NO_ROLE_DISCREPANCY'

    invalid_role = client.put(f'{base}/A', json={}, headers=headers)
    assert invalid_role.status_code == 400
    assert invalid_role.get_json()['code'] == 'INVALID_RESOLUTION_ROLE'


def test_scoring_grid_permissions_and_closed_championship_is_read_only(
    app,
    client,
):
    context = create_scoring_context()
    grid_url = (
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/scoring"
    )
    assert client.get(grid_url).status_code == 401

    judge = db.session.execute(
        select(User).where(User.account_type == AccountType.JUDGE)
    ).scalars().first()
    now = datetime.now(timezone.utc)
    db.session.add(
        JudgeAccessWindow(
            judge_user_id=judge.id,
            championship_id=context['championship'].id,
            competition_day_id=context['day'].id,
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
        )
    )
    db.session.commit()
    judge_headers = login(client, judge.username)
    assert client.get(grid_url, headers=judge_headers).status_code == 403
    assert client.post(
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/gymnasts",
        json={'full_name': 'Sin permiso'},
        headers=judge_headers,
    ).status_code == 403

    admin_headers = login(client, context['admin'].username)
    context['championship'].status = ChampionshipStatus.CLOSED
    db.session.commit()
    assert client.get(grid_url, headers=admin_headers).status_code == 200

    pending_entry = context['entries_by_role'][JudgeRole.E][1]
    read_only = client.put(
        f"/api/v1/championships/{context['championship'].id}/"
        f'score-entries/{pending_entry.id}',
        json={'value': '1.00'},
        headers=admin_headers,
    )
    assert read_only.status_code == 409
    assert read_only.get_json()['code'] == 'CHAMPIONSHIP_SCORES_READ_ONLY'
    db.session.refresh(pending_entry)
    assert pending_entry.submission_status == SubmissionStatus.PENDING

    cannot_add = client.post(
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/gymnasts",
        json={'full_name': 'Nueva Gimnasta'},
        headers=admin_headers,
    )
    assert cannot_add.status_code == 409
    assert (
        cannot_add.get_json()['code']
        == 'CHAMPIONSHIP_GYMNASTS_READ_ONLY'
    )


def test_admin_adds_gymnast_and_initializes_all_scoring_roles(app, client):
    context = create_scoring_context()
    headers = login(client, context['admin'].username)
    base = (
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/gymnasts"
    )

    created = client.post(
        base,
        json={
            'full_name': '  Gimnasta Nueva  ',
            'club_name': '  Club Nuevo  ',
            'passing_order': 1,
        },
        headers=headers,
    )

    assert created.status_code == 201
    payload = created.get_json()
    assert payload['gymnast']['full_name'] == 'Gimnasta Nueva'
    assert payload['gymnast']['club_name'] == 'Club Nuevo'
    assert payload['gymnast']['passing_order'] == 1
    assert payload['initialized_scores'] == 8
    assert payload['summary']['total_score'] == '20.00'
    assert payload['summary']['calculation_status'] == 'PROVISIONAL'

    gymnast_id = uuid.UUID(payload['gymnast']['id'])
    initialized = db.session.execute(
        select(ScoreEntry).where(
            ScoreEntry.gymnast_id == gymnast_id
        )
    ).scalars().unique().all()
    assert len(initialized) == 8
    assert all(
        entry.submission_status == SubmissionStatus.PENDING
        and entry.value == 0
        for entry in initialized
    )
    active = db.session.execute(
        select(Gymnast)
        .where(
            Gymnast.category_id == context['category'].id,
            Gymnast.deleted_at.is_(None),
        )
        .order_by(Gymnast.passing_order)
    ).scalars().all()
    assert [gymnast.full_name for gymnast in active] == [
        'Gimnasta Uno',
        'Gimnasta Nueva',
        'Gimnasta Dos',
    ]
    assert [gymnast.passing_order for gymnast in active] == [0, 1, 2]

    invalid = client.post(
        base,
        json={
            'full_name': 'Otra',
            'passing_order': 4,
        },
        headers=headers,
    )
    assert invalid.status_code == 400
    assert invalid.get_json()['code'] == 'INVALID_PASSING_ORDER'


def test_manual_reorder_requires_complete_unique_category_list(app, client):
    context = create_scoring_context()
    headers = login(client, context['admin'].username)
    endpoint = (
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/gymnasts/order"
    )
    first, second = context['gymnasts']

    reordered = client.put(
        endpoint,
        json={'gymnast_ids': [str(second.id), str(first.id)]},
        headers=headers,
    )
    assert reordered.status_code == 200
    assert reordered.get_json()['changed']
    assert [
        item['id'] for item in reordered.get_json()['gymnasts']
    ] == [str(second.id), str(first.id)]
    assert [
        item['passing_order']
        for item in reordered.get_json()['gymnasts']
    ] == [0, 1]

    repeated = client.put(
        endpoint,
        json={'gymnast_ids': [str(second.id), str(first.id)]},
        headers=headers,
    )
    assert repeated.status_code == 200
    assert not repeated.get_json()['changed']

    incomplete = client.put(
        endpoint,
        json={'gymnast_ids': [str(second.id)]},
        headers=headers,
    )
    assert incomplete.status_code == 400
    assert incomplete.get_json()['code'] == 'GYMNAST_ORDER_MISMATCH'

    duplicated = client.put(
        endpoint,
        json={'gymnast_ids': [str(second.id), str(second.id)]},
        headers=headers,
    )
    assert duplicated.status_code == 400
    assert duplicated.get_json()['code'] == 'GYMNAST_ORDER_MISMATCH'


def test_score_order_uses_total_then_e_then_a(app, client):
    context = create_scoring_context()
    headers = login(client, context['admin'].username)
    first, second = context['gymnasts']
    submit_gymnast_scores(
        second,
        context['admin'],
        {
            JudgeRole.DA: ('5.20', '5.20'),
            JudgeRole.DB: ('3.10', '3.10'),
            JudgeRole.A: ('1.20', '1.20'),
            JudgeRole.E: ('1.10', '1.10'),
        },
    )
    base = (
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/gymnasts"
    )
    created = client.post(
        base,
        json={'full_name': 'Gimnasta Tres'},
        headers=headers,
    )
    assert created.status_code == 201
    third = db.session.get(
        Gymnast,
        uuid.UUID(created.get_json()['gymnast']['id']),
    )
    submit_gymnast_scores(
        third,
        context['admin'],
        {
            JudgeRole.DA: ('5.10', '5.10'),
            JudgeRole.DB: ('3.10', '3.10'),
            JudgeRole.A: ('1.20', '1.20'),
            JudgeRole.E: ('1.00', '1.00'),
        },
    )

    ranked = client.post(
        f'{base}/order-by-score',
        headers=headers,
    )

    assert ranked.status_code == 200
    assert ranked.get_json()['changed']
    rows = ranked.get_json()['gymnasts']
    assert [row['id'] for row in rows] == [
        str(third.id),
        str(first.id),
        str(second.id),
    ]
    assert [row['total_score'] for row in rows] == [
        '26.00',
        '26.00',
        '26.00',
    ]
    assert [row['e_score'] for row in rows] == [
        '9.00',
        '9.00',
        '8.90',
    ]
    assert rows[0]['a_score'] == '8.80'
    assert rows[1]['a_score'] == '8.70'


def test_deleting_active_gymnast_closes_activation_and_preserves_scores(
    app,
    client,
):
    context = create_scoring_context()
    headers = login(client, context['admin'].username)
    first, second = context['gymnasts']
    activation_endpoint = (
        f"/api/v1/championships/{context['championship'].id}/"
        f"competition-days/{context['day'].id}/benches/A/active-gymnast"
    )
    activated = client.put(
        activation_endpoint,
        json={'gymnast_id': str(first.id)},
        headers=headers,
    )
    assert activated.status_code == 200
    score_count = db.session.scalar(
        select(func.count(ScoreEntry.id)).where(
            ScoreEntry.gymnast_id == first.id
        )
    )

    deleted = client.delete(
        f"/api/v1/championships/{context['championship'].id}/gymnasts/"
        f'{first.id}',
        headers=headers,
    )

    assert deleted.status_code == 200
    assert deleted.get_json()['active_activation_cleared']
    assert deleted.get_json()['gymnasts'] == [{
        'id': str(second.id),
        'full_name': second.full_name,
        'club_name': second.club_name,
        'passing_order': 0,
    }]
    db.session.refresh(first)
    assert first.deleted_at is not None
    assert first.deleted_by_user_id == context['admin'].id
    assert db.session.execute(
        select(BenchActivation).where(
            BenchActivation.gymnast_id == first.id,
            BenchActivation.deactivated_at.is_(None),
        )
    ).scalar_one_or_none() is None
    assert db.session.scalar(
        select(func.count(ScoreEntry.id)).where(
            ScoreEntry.gymnast_id == first.id
        )
    ) == score_count
    assert db.session.execute(
        select(AuditLog).where(
            AuditLog.action == 'GYMNAST_DELETED',
            AuditLog.entity_id == first.id,
        )
    ).scalar_one().details['category_id'] == str(context['category'].id)

    grid = client.get(
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/scoring",
        headers=headers,
    )
    assert grid.status_code == 200
    assert [
        row['id'] for row in grid.get_json()['gymnasts']
    ] == [str(second.id)]


def test_full_category_publication_snapshots_every_gymnast_including_zero(
    app,
    client,
):
    context = create_scoring_context()
    headers = login(client, context['admin'].username)
    first, second = context['gymnasts']
    discount = client.put(
        f"/api/v1/championships/{context['championship'].id}/gymnasts/"
        f'{second.id}/discount',
        json={'value': '20.00'},
        headers=headers,
    )
    assert discount.status_code == 200
    assert discount.get_json()['summary']['total_score'] == '0.00'

    published = client.post(
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/publish",
        headers=headers,
    )

    assert published.status_code == 201
    payload = published.get_json()
    assert payload['publication']['mode'] == 'FULL_CATEGORY'
    assert payload['publication']['result_count'] == 2
    assert {
        row['gymnast_id']: row['total_score']
        for row in payload['results']
    } == {
        str(first.id): '26.00',
        str(second.id): '0.00',
    }
    assert db.session.scalar(
        select(func.count(PublicationBatch.id))
    ) == 1
    assert db.session.scalar(
        select(func.count(PublishedResult.id))
    ) == 2
    audit = db.session.execute(
        select(AuditLog).where(
            AuditLog.action == 'CATEGORY_PUBLISHED'
        )
    ).scalar_one()
    assert audit.details == {
        'category_id': str(context['category'].id),
        'mode': 'FULL_CATEGORY',
        'result_count': 2,
    }

    public = client.get(
        f"/api/v1/public/championships/active/categories/"
        f"{context['category'].id}/results"
    )
    assert public.status_code == 200
    public_rows = public.get_json()['results']
    assert {
        row['gymnast_id']: row['total_score']
        for row in public_rows
    } == {
        str(first.id): '26.00',
        str(second.id): '0.00',
    }
    assert all(row['is_published'] for row in public_rows)
    assert all(
        'scores' not in row
        and 'a_score' not in row
        and 'e_score' not in row
        and 'submission_status' not in row
        for row in public_rows
    )


def test_corrections_stay_private_until_manual_republication(app, client):
    context = create_scoring_context()
    headers = login(client, context['admin'].username)
    publish_url = (
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/publish"
    )
    public_url = (
        f"/api/v1/public/championships/active/categories/"
        f"{context['category'].id}/results"
    )
    first_id = str(context['gymnasts'][0].id)

    first_publication = client.post(publish_url, headers=headers)
    assert first_publication.status_code == 201
    assert {
        row['gymnast_id']: row['total_score']
        for row in client.get(public_url).get_json()['results']
    }[first_id] == '26.00'

    corrected_entry = context['entries_by_role'][JudgeRole.E][1]
    corrected = client.put(
        f"/api/v1/championships/{context['championship'].id}/"
        f'score-entries/{corrected_entry.id}',
        json={'value': '1.00'},
        headers=headers,
    )
    assert corrected.status_code == 200
    assert corrected.get_json()['summary']['total_score'] == '25.50'
    assert {
        row['gymnast_id']: row['total_score']
        for row in client.get(public_url).get_json()['results']
    }[first_id] == '26.00'
    assert db.session.scalar(
        select(func.count(PublicationBatch.id))
    ) == 1

    second_publication = client.post(publish_url, headers=headers)
    assert second_publication.status_code == 201
    assert (
        second_publication.get_json()['publication']['id']
        != first_publication.get_json()['publication']['id']
    )
    assert {
        row['gymnast_id']: row['total_score']
        for row in client.get(public_url).get_json()['results']
    }[first_id] == '25.50'

    third_publication = client.post(publish_url, headers=headers)
    assert third_publication.status_code == 201
    assert (
        third_publication.get_json()['publication']['id']
        != second_publication.get_json()['publication']['id']
    )
    assert db.session.scalar(
        select(func.count(PublicationBatch.id))
    ) == 3
    historic_totals = db.session.execute(
        select(PublishedResult.total_score)
        .where(
            PublishedResult.gymnast_id
            == context['gymnasts'][0].id
        )
        .order_by(PublishedResult.published_at)
    ).scalars().all()
    assert [
        format(total, '.2f')
        for total in historic_totals
    ] == ['26.00', '25.50', '25.50']


def test_public_results_hide_deleted_and_show_new_unpublished_as_zero(
    app,
    client,
):
    context = create_scoring_context()
    headers = login(client, context['admin'].username)
    first, second = context['gymnasts']
    assert client.post(
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/publish",
        headers=headers,
    ).status_code == 201

    assert client.delete(
        f"/api/v1/championships/{context['championship'].id}/gymnasts/"
        f'{first.id}',
        headers=headers,
    ).status_code == 200
    added = client.post(
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/gymnasts",
        json={'full_name': 'Incorporación posterior'},
        headers=headers,
    )
    assert added.status_code == 201
    added_id = added.get_json()['gymnast']['id']

    public = client.get(
        f"/api/v1/public/championships/active/categories/"
        f"{context['category'].id}/results"
    )

    assert public.status_code == 200
    rows = {
        row['gymnast_id']: row
        for row in public.get_json()['results']
    }
    assert str(first.id) not in rows
    assert rows[str(second.id)]['is_published']
    assert rows[added_id]['total_score'] == '0.00'
    assert not rows[added_id]['is_published']


def test_public_catalog_search_and_result_sorting(app, client):
    context = create_scoring_context()
    headers = login(client, context['admin'].username)
    first, second = context['gymnasts']
    reordered = client.put(
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/gymnasts/order",
        json={'gymnast_ids': [str(second.id), str(first.id)]},
        headers=headers,
    )
    assert reordered.status_code == 200
    assert client.post(
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/publish",
        headers=headers,
    ).status_code == 201

    catalog = client.get(
        '/api/v1/public/championships/active',
        query_string={'query': 'gimnasta dos'},
    )
    assert catalog.status_code == 200
    assert catalog.get_json()['championship']['name'] == (
        context['championship'].name
    )
    assert [
        category['id']
        for category in catalog.get_json()['categories']
    ] == [str(context['category'].id)]
    category_payload = catalog.get_json()['categories'][0]
    assert category_payload['gymnast_count'] == 2
    assert category_payload['publication'] is not None
    assert 'gymnasts' not in category_payload
    assert client.get(
        '/api/v1/public/championships/active',
        query_string={'query': 'sin coincidencias'},
    ).get_json()['categories'] == []

    results_url = (
        f"/api/v1/public/championships/active/categories/"
        f"{context['category'].id}/results"
    )
    passing_order = client.get(results_url)
    assert [
        result['gymnast_id']
        for result in passing_order.get_json()['results']
    ] == [str(second.id), str(first.id)]

    score_order = client.get(
        results_url,
        query_string={'sort': 'score'},
    )
    assert score_order.status_code == 200
    assert [
        result['gymnast_id']
        for result in score_order.get_json()['results']
    ] == [str(first.id), str(second.id)]
    assert [
        result['display_position']
        for result in score_order.get_json()['results']
    ] == [1, 2]

    gymnast_search = client.get(
        results_url,
        query_string={'query': 'DOS'},
    )
    assert [
        result['gymnast_id']
        for result in gymnast_search.get_json()['results']
    ] == [str(second.id)]
    category_search = client.get(
        results_url,
        query_string={'query': 'junior a'},
    )
    assert len(category_search.get_json()['results']) == 2
    invalid_sort = client.get(
        results_url,
        query_string={'sort': 'private_notes'},
    )
    assert invalid_sort.status_code == 400
    assert invalid_sort.get_json()['code'] == 'INVALID_PUBLIC_SORT'


def test_full_publication_requires_admin_and_active_championship(
    app,
    client,
):
    context = create_scoring_context()
    publish_url = (
        f"/api/v1/championships/{context['championship'].id}/categories/"
        f"{context['category'].id}/publish"
    )
    public_url = (
        f"/api/v1/public/championships/active/categories/"
        f"{context['category'].id}/results"
    )
    assert client.post(publish_url).status_code == 401

    judge = db.session.execute(
        select(User).where(User.account_type == AccountType.JUDGE)
    ).scalars().first()
    now = datetime.now(timezone.utc)
    db.session.add(
        JudgeAccessWindow(
            judge_user_id=judge.id,
            championship_id=context['championship'].id,
            competition_day_id=context['day'].id,
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
        )
    )
    db.session.commit()
    judge_headers = login(client, judge.username)
    assert client.post(publish_url, headers=judge_headers).status_code == 403

    admin_headers = login(client, context['admin'].username)
    context['championship'].status = ChampionshipStatus.PAUSED
    db.session.commit()
    paused = client.post(publish_url, headers=admin_headers)
    assert paused.status_code == 409
    assert paused.get_json()['code'] == 'CHAMPIONSHIP_NOT_ACTIVE'
    assert client.get(public_url).status_code == 404
