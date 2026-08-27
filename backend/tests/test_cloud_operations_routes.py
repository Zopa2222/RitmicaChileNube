from datetime import date
import uuid

from sqlalchemy import select

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
    ScoreEntry,
    Session,
    User,
)
from app.security.passwords import hash_password


ADMIN_PASSWORD = 'Clave-Admin-123'


def create_user(account_type, username, rut=None):
    user = User(
        account_type=account_type,
        first_name='Nombre',
        last_name='Apellido',
        rut_normalized=rut,
        username=username,
        password_hash=hash_password(ADMIN_PASSWORD),
    )
    db.session.add(user)
    db.session.flush()
    return user


def login(client, username):
    response = client.post(
        '/api/v1/auth/login',
        json={'username': username, 'password': ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    csrf_cookie = client.get_cookie('ritmica_csrf')
    return {'X-CSRF-TOKEN': csrf_cookie.value}


def create_championship_context(admin, name='Clasificatorio Centro'):
    championship = Championship(
        name=name,
        kind='CLASIFICATORIO',
        zone='CENTRO',
        start_date=date(2026, 8, 1),
        status=ChampionshipStatus.DRAFT,
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

    categories = {}
    gymnasts = {}
    definitions = (
        ('A_AM_1', Bench.A, Session.AM, 0, 'MINI A'),
        ('A_AM_2', Bench.A, Session.AM, 1, 'INFANTIL A'),
        ('A_PM_1', Bench.A, Session.PM, 0, 'JUNIOR A'),
        ('B_AM_1', Bench.B, Session.AM, 0, 'MINI B'),
    )
    for key, bench, session, passing_order, category_name in definitions:
        category = Category(
            championship_id=championship.id,
            competition_day_id=competition_day.id,
            name=category_name,
            bench=bench,
            session=session,
            passing_order=passing_order,
        )
        db.session.add(category)
        db.session.flush()
        gymnast = Gymnast(
            category_id=category.id,
            full_name=f'Gimnasta {category_name}',
            club_name='Club',
            passing_order=0,
        )
        db.session.add(gymnast)
        db.session.flush()
        categories[key] = category
        gymnasts[key] = gymnast

    db.session.commit()
    return championship, competition_day, categories, gymnasts


def assignment_payload(day, judge_id, session='AM', role='A'):
    return {
        'competition_day_id': str(day.id),
        'bench': 'A',
        'session': session,
        'role': role,
        'judge_id': str(judge_id),
    }


def test_championship_lifecycle_enforces_single_active(app, client):
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    first, _, _, _ = create_championship_context(admin, 'Primero')
    second, _, _, _ = create_championship_context(admin, 'Segundo')
    headers = login(client, admin.username)

    activated = client.post(
        f'/api/v1/championships/{first.id}/activate',
        headers=headers,
    )
    assert activated.status_code == 200
    assert activated.get_json()['championship']['status'] == 'ACTIVE'

    conflict = client.post(
        f'/api/v1/championships/{second.id}/activate',
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.get_json()['code'] == 'ACTIVE_CHAMPIONSHIP_EXISTS'

    paused = client.post(
        f'/api/v1/championships/{first.id}/pause',
        headers=headers,
    )
    assert paused.status_code == 200
    assert paused.get_json()['championship']['status'] == 'PAUSED'

    second_activated = client.post(
        f'/api/v1/championships/{second.id}/activate',
        headers=headers,
    )
    assert second_activated.status_code == 200

    closed = client.post(
        f'/api/v1/championships/{second.id}/close',
        headers=headers,
    )
    assert closed.status_code == 200
    assert closed.get_json()['championship']['status'] == 'CLOSED'
    assert db.session.get(Championship, second.id).closed_at is not None


def test_admin_creates_judge_only_during_assignment_and_windows_expand(
    app,
    client,
):
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    championship, day, categories, gymnasts = create_championship_context(
        admin
    )
    headers = login(client, admin.username)

    days = client.get(
        f'/api/v1/championships/{championship.id}/competition-days'
    )
    assert days.status_code == 200
    assert days.get_json()['competition_days'][0]['id'] == str(day.id)

    forbidden = client.post(
        '/api/v1/judges',
        json={
            'first_name': 'María',
            'last_name': 'Pérez',
            'rut': '12.345.678-5',
        },
        headers=headers,
    )
    assert forbidden.status_code == 403

    created = client.post(
        f'/api/v1/championships/{championship.id}/judge-assignments',
        json={
            'competition_day_id': str(day.id),
            'bench': 'A',
            'session': 'AM',
            'role': 'DA',
            'judge': {
                'first_name': 'María',
                'last_name': 'Pérez',
                'rut': '12.345.678-5',
            },
        },
        headers=headers,
    )
    assert created.status_code == 201
    payload = created.get_json()
    judge_id = payload['assignment']['judge']['id']
    assert payload['credentials']['username'] == 'MARIAPEREZ123456785'
    assert payload['credentials']['password']
    assert (
        payload['assignment']['effective_from_category']['id']
        == str(categories['A_AM_1'].id)
    )
    assignment_id = uuid.UUID(payload['assignment']['id'])
    initialized_scores = db.session.execute(
        select(ScoreEntry).where(
            ScoreEntry.judge_assignment_id == assignment_id
        )
    ).scalars().all()
    assert {
        score.gymnast_id for score in initialized_scores
    } == {
        gymnasts['A_AM_1'].id,
        gymnasts['A_AM_2'].id,
    }

    judge_uuid = uuid.UUID(payload['assignment']['judge']['id'])
    window = db.session.execute(
        select(JudgeAccessWindow).where(
            JudgeAccessWindow.judge_user_id == judge_uuid
        )
    ).scalar_one()
    assert (window.ends_at - window.starts_at).total_seconds() == 8 * 3600

    second_assignment = client.post(
        f'/api/v1/championships/{championship.id}/judge-assignments',
        json=assignment_payload(day, judge_id, session='PM', role='E'),
        headers=headers,
    )
    assert second_assignment.status_code == 201
    assert second_assignment.get_json()['credentials'] is None
    second_assignment_id = uuid.UUID(
        second_assignment.get_json()['assignment']['id']
    )
    assert len(
        db.session.execute(
            select(ScoreEntry).where(
                ScoreEntry.judge_assignment_id == second_assignment_id
            )
        ).scalars().all()
    ) == 1

    line_assignment = client.post(
        f'/api/v1/championships/{championship.id}/judge-assignments',
        json={
            'competition_day_id': str(day.id),
            'bench': 'B',
            'session': 'AM',
            'role': 'L',
            'judge_id': judge_id,
        },
        headers=headers,
    )
    assert line_assignment.status_code == 201
    line_assignment_id = uuid.UUID(
        line_assignment.get_json()['assignment']['id']
    )
    assert db.session.execute(
        select(ScoreEntry).where(
            ScoreEntry.judge_assignment_id == line_assignment_id
        )
    ).scalar_one_or_none() is None

    db.session.refresh(window)
    assert (window.ends_at - window.starts_at).total_seconds() == 16 * 3600

    search = client.get('/api/v1/judges?query=12345678')
    assert search.status_code == 200
    assert search.get_json()['judges'][0]['id'] == judge_id


def test_super_admin_can_create_standalone_judge(app, client):
    super_admin = create_user(AccountType.SUPER_ADMIN, 'SUPER')
    db.session.commit()
    headers = login(client, super_admin.username)

    response = client.post(
        '/api/v1/judges',
        json={
            'first_name': 'María',
            'last_name': 'Pérez',
            'rut': '12.345.678-5',
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.get_json()['judge']['rut'] == '123456785'
    assert response.get_json()['credentials']['password']


def test_active_gymnast_is_independent_by_bench_and_refreshes_activation(
    app,
    client,
):
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    judge = create_user(
        AccountType.JUDGE,
        'JUEZA',
        rut='111111111',
    )
    championship, day, categories, gymnasts = create_championship_context(
        admin
    )
    assignment = JudgeAssignment(
        championship_id=championship.id,
        judge_user_id=judge.id,
        competition_day_id=day.id,
        bench=Bench.A,
        session=Session.AM,
        role=JudgeRole.A,
        effective_from_category_id=categories['A_AM_1'].id,
        assigned_by_user_id=admin.id,
    )
    db.session.add(assignment)
    db.session.commit()
    headers = login(client, admin.username)
    assert client.post(
        f'/api/v1/championships/{championship.id}/activate',
        headers=headers,
    ).status_code == 200

    endpoint = (
        f'/api/v1/championships/{championship.id}/competition-days/'
        f'{day.id}/benches/A/active-gymnast'
    )
    first = client.put(
        endpoint,
        json={'gymnast_id': str(gymnasts['A_AM_1'].id)},
        headers=headers,
    )
    assert first.status_code == 200
    first_activation_id = first.get_json()['activation']['id']
    assert first.get_json()['changed']
    score = db.session.execute(select(ScoreEntry)).scalar_one()
    assert str(score.activation_id) == first_activation_id

    same = client.put(
        endpoint,
        json={'gymnast_id': str(gymnasts['A_AM_1'].id)},
        headers=headers,
    )
    assert same.status_code == 200
    assert not same.get_json()['changed']
    assert len(
        db.session.execute(select(BenchActivation)).scalars().all()
    ) == 1

    switched = client.put(
        endpoint,
        json={'gymnast_id': str(gymnasts['A_AM_2'].id)},
        headers=headers,
    )
    assert switched.status_code == 200
    assert switched.get_json()['activation']['id'] != first_activation_id

    reactivated = client.put(
        endpoint,
        json={'gymnast_id': str(gymnasts['A_AM_1'].id)},
        headers=headers,
    )
    assert reactivated.status_code == 200
    new_activation_id = reactivated.get_json()['activation']['id']
    assert new_activation_id != first_activation_id
    db.session.refresh(score)
    assert str(score.activation_id) == new_activation_id

    wrong_bench = client.put(
        endpoint,
        json={'gymnast_id': str(gymnasts['B_AM_1'].id)},
        headers=headers,
    )
    assert wrong_bench.status_code == 400
    assert wrong_bench.get_json()['code'] == 'GYMNAST_SCOPE_MISMATCH'

    bench_b = client.put(
        (
            f'/api/v1/championships/{championship.id}/competition-days/'
            f'{day.id}/benches/B/active-gymnast'
        ),
        json={'gymnast_id': str(gymnasts['B_AM_1'].id)},
        headers=headers,
    )
    assert bench_b.status_code == 200
    assert len(
        db.session.execute(
            select(BenchActivation).where(
                BenchActivation.deactivated_at.is_(None)
            )
        ).scalars().all()
    ) == 2

    operations = client.get(
        f'/api/v1/championships/{championship.id}/competition-days/'
        f'{day.id}/operations'
    )
    assert operations.status_code == 200
    assert (
        operations.get_json()['benches']['A']['active']['gymnast_id']
        == str(gymnasts['A_AM_1'].id)
    )
    assert (
        operations.get_json()['benches']['B']['active']['gymnast_id']
        == str(gymnasts['B_AM_1'].id)
    )


def test_reassignment_starts_at_category_after_current_activation(app, client):
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    old_judge = create_user(
        AccountType.JUDGE,
        'JUEZ1',
        rut='111111111',
    )
    new_judge = create_user(
        AccountType.JUDGE,
        'JUEZ2',
        rut='222222222',
    )
    championship, day, categories, gymnasts = create_championship_context(
        admin
    )
    headers = login(client, admin.username)
    assigned = client.post(
        f'/api/v1/championships/{championship.id}/judge-assignments',
        json=assignment_payload(day, old_judge.id, role='E'),
        headers=headers,
    )
    assert assigned.status_code == 201
    assignment = db.session.get(
        JudgeAssignment,
        uuid.UUID(assigned.get_json()['assignment']['id']),
    )
    assert db.session.execute(
        select(JudgeAccessWindow).where(
            JudgeAccessWindow.judge_user_id == old_judge.id
        )
    ).scalar_one_or_none() is not None

    assert client.post(
        f'/api/v1/championships/{championship.id}/activate',
        headers=headers,
    ).status_code == 200
    assert client.put(
        f'/api/v1/championships/{championship.id}/competition-days/'
        f'{day.id}/benches/A/active-gymnast',
        json={'gymnast_id': str(gymnasts['A_AM_1'].id)},
        headers=headers,
    ).status_code == 200

    response = client.post(
        f'/api/v1/championships/{championship.id}/judge-assignments/'
        f'{assignment.id}/reassign',
        json={'judge_id': str(new_judge.id)},
        headers=headers,
    )
    assert response.status_code == 201
    replacement = response.get_json()['assignment']
    replacement_id = uuid.UUID(replacement['id'])
    assert (
        replacement['effective_from_category']['id']
        == str(categories['A_AM_2'].id)
    )
    db.session.refresh(assignment)
    assert (
        assignment.effective_to_category_id
        == categories['A_AM_1'].id
    )
    assert assignment.superseded_at is not None
    assert db.session.execute(
        select(JudgeAccessWindow).where(
            JudgeAccessWindow.judge_user_id == old_judge.id
        )
    ).scalar_one_or_none() is None
    assert db.session.execute(
        select(JudgeAccessWindow).where(
            JudgeAccessWindow.judge_user_id == new_judge.id
        )
    ).scalar_one_or_none() is not None

    previous_grid = client.get(
        f'/api/v1/championships/{championship.id}/categories/'
        f"{categories['A_AM_1'].id}/scoring",
        headers=headers,
    )
    next_grid = client.get(
        f'/api/v1/championships/{championship.id}/categories/'
        f"{categories['A_AM_2'].id}/scoring",
        headers=headers,
    )
    assert previous_grid.status_code == 200
    assert next_grid.status_code == 200
    assert (
        previous_grid.get_json()['assignments'][0]['judge']['id']
        == str(old_judge.id)
    )
    assert (
        next_grid.get_json()['assignments'][0]['judge']['id']
        == str(new_judge.id)
    )
    assert (
        next_grid.get_json()['assignments'][0]['id']
        == str(replacement_id)
    )

    old_future_score = db.session.execute(
        select(ScoreEntry).where(
            ScoreEntry.gymnast_id == gymnasts['A_AM_2'].id,
            ScoreEntry.judge_assignment_id == assignment.id,
        )
    ).scalar_one()
    stale_edit = client.put(
        f'/api/v1/championships/{championship.id}/score-entries/'
        f'{old_future_score.id}',
        json={'value': '4.20'},
        headers=headers,
    )
    assert stale_edit.status_code == 409
    assert stale_edit.get_json()['code'] == 'ASSIGNMENT_NOT_EFFECTIVE'

    added = client.post(
        f'/api/v1/championships/{championship.id}/categories/'
        f"{categories['A_AM_2'].id}/gymnasts",
        json={
            'full_name': 'Gimnasta incorporada',
            'club_name': 'Club nuevo',
        },
        headers=headers,
    )
    assert added.status_code == 201
    added_id = uuid.UUID(added.get_json()['gymnast']['id'])
    added_scores = db.session.execute(
        select(ScoreEntry).where(ScoreEntry.gymnast_id == added_id)
    ).scalars().unique().all()
    assert len(added_scores) == 1
    assert added_scores[0].judge_assignment_id == replacement_id

    actions = db.session.execute(
        select(AuditLog.action).where(
            AuditLog.championship_id == championship.id
        )
    ).scalars().all()
    assert 'JUDGE_REASSIGNED' in actions


def test_active_championship_can_add_assignment_from_next_category(
    app,
    client,
):
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    judge = create_user(
        AccountType.JUDGE,
        'JUEZ-NUEVO',
        rut='111111111',
    )
    championship, day, categories, gymnasts = create_championship_context(
        admin
    )
    headers = login(client, admin.username)

    assert client.post(
        f'/api/v1/championships/{championship.id}/activate',
        headers=headers,
    ).status_code == 200
    assert client.put(
        f'/api/v1/championships/{championship.id}/competition-days/'
        f'{day.id}/benches/A/active-gymnast',
        json={'gymnast_id': str(gymnasts['A_AM_1'].id)},
        headers=headers,
    ).status_code == 200

    response = client.post(
        f'/api/v1/championships/{championship.id}/judge-assignments',
        json=assignment_payload(day, judge.id, role='E'),
        headers=headers,
    )

    assert response.status_code == 201
    assignment = response.get_json()['assignment']
    assert (
        assignment['effective_from_category']['id']
        == str(categories['A_AM_2'].id)
    )
    assignment_id = uuid.UUID(assignment['id'])
    scores = db.session.execute(
        select(ScoreEntry).where(
            ScoreEntry.judge_assignment_id == assignment_id
        )
    ).scalars().all()
    assert [score.gymnast_id for score in scores] == [
        gymnasts['A_AM_2'].id
    ]


def test_admin_can_remove_draft_assignment_without_deleting_judge(
    app,
    client,
):
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    judge = create_user(
        AccountType.JUDGE,
        'JUEZ-ELIMINAR',
        rut='111111111',
    )
    championship, day, _, _ = create_championship_context(admin)
    headers = login(client, admin.username)
    created = client.post(
        f'/api/v1/championships/{championship.id}/judge-assignments',
        json=assignment_payload(day, judge.id, role='E'),
        headers=headers,
    )
    assignment_id = created.get_json()['assignment']['id']

    removed = client.delete(
        f'/api/v1/championships/{championship.id}/judge-assignments/'
        f'{assignment_id}',
        headers=headers,
    )

    assert removed.status_code == 200
    assert removed.get_json()['effective_from_category'] is None
    assert db.session.get(User, judge.id) is not None
    assert db.session.get(JudgeAssignment, uuid.UUID(assignment_id)) is None
    assert db.session.execute(
        select(ScoreEntry).where(
            ScoreEntry.judge_assignment_id == uuid.UUID(assignment_id)
        )
    ).scalar_one_or_none() is None
