from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models import (
    AccountType,
    Bench,
    BenchActivation,
    CalculationStatus,
    Category,
    Championship,
    ChampionshipStatus,
    CompetitionDay,
    Gymnast,
    JudgeAccessWindow,
    JudgeAssignment,
    JudgeRole,
    ScoreEntry,
    ScoreSummary,
    Session,
    User,
)
from app.security.passwords import hash_password
from app.services.championship_operations_service import activate_gymnast


JUDGE_PASSWORD = 'Clave-Juez-123'


def create_user(account_type, username, rut=None):
    user = User(
        account_type=account_type,
        first_name='Nombre',
        last_name='Apellido',
        rut_normalized=rut,
        username=username,
        password_hash=hash_password(JUDGE_PASSWORD),
    )
    db.session.add(user)
    db.session.flush()
    return user


def login_judge(client, username):
    response = client.post(
        '/api/v1/auth/login',
        json={'username': username, 'password': JUDGE_PASSWORD},
    )
    assert response.status_code == 200
    csrf_cookie = client.get_cookie('ritmica_csrf')
    return {'X-CSRF-TOKEN': csrf_cookie.value}


def create_cabin_context():
    now = datetime.now(timezone.utc)
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    judge_a = create_user(AccountType.JUDGE, 'JUEZA', '111111111')
    judge_e = create_user(AccountType.JUDGE, 'JUEZE', '222222222')
    championship = Championship(
        name='Final Nacional',
        kind='FINAL',
        zone='NACIONAL',
        start_date=date.today(),
        status=ChampionshipStatus.ACTIVE,
        responsible_admin_id=admin.id,
    )
    db.session.add(championship)
    db.session.flush()
    competition_day = CompetitionDay(
        championship_id=championship.id,
        sequence=1,
        competition_date=championship.start_date,
        source_sheet_name='DIA 1',
    )
    db.session.add(competition_day)
    db.session.flush()

    category_am = Category(
        championship_id=championship.id,
        competition_day_id=competition_day.id,
        name='SENIOR AM',
        bench=Bench.A,
        session=Session.AM,
        passing_order=0,
    )
    category_pm = Category(
        championship_id=championship.id,
        competition_day_id=competition_day.id,
        name='SENIOR PM',
        bench=Bench.A,
        session=Session.PM,
        passing_order=0,
    )
    db.session.add_all([category_am, category_pm])
    db.session.flush()
    gymnast_one = Gymnast(
        category_id=category_am.id,
        full_name='Gimnasta Uno',
        club_name='Club Uno',
        passing_order=0,
    )
    gymnast_two = Gymnast(
        category_id=category_am.id,
        full_name='Gimnasta Dos',
        club_name='Club Dos',
        passing_order=1,
    )
    db.session.add_all([gymnast_one, gymnast_two])
    db.session.flush()

    assignment_a = JudgeAssignment(
        championship_id=championship.id,
        judge_user_id=judge_a.id,
        competition_day_id=competition_day.id,
        bench=Bench.A,
        session=Session.AM,
        role=JudgeRole.A,
        effective_from_category_id=category_am.id,
        assigned_by_user_id=admin.id,
    )
    assignment_e = JudgeAssignment(
        championship_id=championship.id,
        judge_user_id=judge_e.id,
        competition_day_id=competition_day.id,
        bench=Bench.A,
        session=Session.AM,
        role=JudgeRole.E,
        effective_from_category_id=category_am.id,
        assigned_by_user_id=admin.id,
    )
    assignment_plan = JudgeAssignment(
        championship_id=championship.id,
        judge_user_id=judge_a.id,
        competition_day_id=competition_day.id,
        bench=Bench.A,
        session=Session.PM,
        role=JudgeRole.P,
        effective_from_category_id=category_pm.id,
        assigned_by_user_id=admin.id,
    )
    db.session.add_all([assignment_a, assignment_e, assignment_plan])
    db.session.flush()

    for judge in (judge_a, judge_e):
        db.session.add(
            JudgeAccessWindow(
                judge_user_id=judge.id,
                championship_id=championship.id,
                competition_day_id=competition_day.id,
                starts_at=now - timedelta(hours=1),
                ends_at=now + timedelta(hours=1),
            )
        )

    activation = BenchActivation(
        championship_id=championship.id,
        competition_day_id=competition_day.id,
        bench=Bench.A,
        gymnast_id=gymnast_one.id,
        activated_by_user_id=admin.id,
        activated_at=now,
    )
    db.session.add(activation)
    db.session.flush()
    entry_a = ScoreEntry(
        gymnast_id=gymnast_one.id,
        judge_assignment_id=assignment_a.id,
        activation_id=activation.id,
    )
    entry_e = ScoreEntry(
        gymnast_id=gymnast_one.id,
        judge_assignment_id=assignment_e.id,
        activation_id=activation.id,
    )
    db.session.add_all([entry_a, entry_e])
    db.session.commit()
    return {
        'admin': admin,
        'judge_a': judge_a,
        'judge_e': judge_e,
        'championship': championship,
        'day': competition_day,
        'category_am': category_am,
        'gymnast_one': gymnast_one,
        'gymnast_two': gymnast_two,
        'assignment_a': assignment_a,
        'assignment_e': assignment_e,
        'assignment_plan': assignment_plan,
        'activation': activation,
        'entry_a': entry_a,
        'entry_e': entry_e,
    }


def test_context_only_exposes_own_assignment_and_active_gymnast(app, client):
    context = create_cabin_context()
    login_judge(client, context['judge_a'].username)

    response = client.get('/api/v1/judge/contexts')

    assert response.status_code == 200
    contexts = response.get_json()['contexts']
    assert len(contexts) == 2
    am_context = next(
        item for item in contexts if item['session'] == 'AM'
    )
    pm_context = next(
        item for item in contexts if item['session'] == 'PM'
    )
    assert am_context['state'] == 'ACTIVE'
    assert am_context['role'] == 'A'
    assert (
        am_context['active']['gymnast']['id']
        == str(context['gymnast_one'].id)
    )
    assert am_context['active']['score']['id'] == str(context['entry_a'].id)
    assert pm_context['state'] == 'WAITING_FOR_SESSION'
    assert pm_context['active'] is None

    serialized = response.get_data(as_text=True)
    assert str(context['entry_e'].id) not in serialized
    assert context['judge_e'].username not in serialized
    assert 'total_score' not in serialized


def test_score_put_is_exact_idempotent_and_recalculates_summary(app, client):
    context = create_cabin_context()
    headers = login_judge(client, context['judge_a'].username)
    endpoint = f'/api/v1/judge/scores/{context["entry_a"].id}'
    body = {
        'activation_id': str(context['activation'].id),
        'value': '1,15',
    }

    first = client.put(endpoint, json=body, headers=headers)

    assert first.status_code == 200
    assert first.get_json()['changed']
    assert first.get_json()['score']['value'] == '1.15'
    submitted_at = first.get_json()['score']['submitted_at']
    summary = db.session.get(ScoreSummary, context['gymnast_one'].id)
    assert summary.a_score == Decimal('8.85')
    assert summary.e_score == Decimal('10.00')
    assert summary.total_score == Decimal('18.85')
    assert summary.calculation_status == CalculationStatus.PROVISIONAL

    retry = client.put(endpoint, json=body, headers=headers)

    assert retry.status_code == 200
    assert not retry.get_json()['changed']
    assert retry.get_json()['score']['submitted_at'] == submitted_at

    invalid = client.put(
        endpoint,
        json={
            'activation_id': str(context['activation'].id),
            'value': '1.155',
        },
        headers=headers,
    )
    assert invalid.status_code == 400
    assert invalid.get_json()['code'] == 'INVALID_SCORE'
    db.session.refresh(context['entry_a'])
    assert context['entry_a'].value == Decimal('1.15')

    other_judge_score = client.put(
        f'/api/v1/judge/scores/{context["entry_e"].id}',
        json={
            'activation_id': str(context['activation'].id),
            'value': '2.00',
        },
        headers=headers,
    )
    assert other_judge_score.status_code == 404
    assert other_judge_score.get_json()['code'] == 'SCORE_ENTRY_NOT_FOUND'


def test_zero_submission_changes_pending_zero_to_submitted(app, client):
    context = create_cabin_context()
    headers = login_judge(client, context['judge_a'].username)
    endpoint = f'/api/v1/judge/scores/{context["entry_a"].id}'
    body = {
        'activation_id': str(context['activation'].id),
        'value': 0,
    }

    response = client.put(endpoint, json=body, headers=headers)

    assert response.status_code == 200
    assert response.get_json()['changed']
    assert response.get_json()['score']['value'] == '0.00'
    assert (
        response.get_json()['score']['submission_status']
        == 'SUBMITTED'
    )


def test_old_activation_is_rejected_after_switching_away_and_back(app, client):
    context = create_cabin_context()
    headers = login_judge(client, context['judge_a'].username)
    old_activation_id = context['activation'].id

    activate_gymnast(
        context['championship'],
        context['day'],
        Bench.A,
        context['gymnast_two'],
        context['admin'].id,
    )
    db.session.commit()
    new_activation, changed, _ = activate_gymnast(
        context['championship'],
        context['day'],
        Bench.A,
        context['gymnast_one'],
        context['admin'].id,
    )
    assert changed
    db.session.commit()

    stale = client.put(
        f'/api/v1/judge/scores/{context["entry_a"].id}',
        json={
            'activation_id': str(old_activation_id),
            'value': '1.20',
        },
        headers=headers,
    )
    assert stale.status_code == 409
    assert stale.get_json()['code'] == 'STALE_ACTIVATION'

    current = client.put(
        f'/api/v1/judge/scores/{context["entry_a"].id}',
        json={
            'activation_id': str(new_activation.id),
            'value': '1.20',
        },
        headers=headers,
    )
    assert current.status_code == 200
    assert current.get_json()['changed']


def test_open_window_in_another_assignment_does_not_authorize_score(
    app,
    client,
):
    context = create_cabin_context()
    headers = login_judge(client, context['judge_a'].username)
    now = datetime.now(timezone.utc)
    second_day = CompetitionDay(
        championship_id=context['championship'].id,
        sequence=2,
        competition_date=context['championship'].start_date + timedelta(days=1),
        source_sheet_name='DIA 2',
    )
    db.session.add(second_day)
    db.session.flush()
    category = Category(
        championship_id=context['championship'].id,
        competition_day_id=second_day.id,
        name='JUNIOR',
        bench=Bench.B,
        session=Session.AM,
        passing_order=0,
    )
    db.session.add(category)
    db.session.flush()
    gymnast = Gymnast(
        category_id=category.id,
        full_name='Gimnasta Día Dos',
        club_name='Club',
        passing_order=0,
    )
    db.session.add(gymnast)
    db.session.flush()
    assignment = JudgeAssignment(
        championship_id=context['championship'].id,
        judge_user_id=context['judge_a'].id,
        competition_day_id=second_day.id,
        bench=Bench.B,
        session=Session.AM,
        role=JudgeRole.DA,
        effective_from_category_id=category.id,
        assigned_by_user_id=context['admin'].id,
    )
    db.session.add(assignment)
    db.session.flush()
    activation = BenchActivation(
        championship_id=context['championship'].id,
        competition_day_id=second_day.id,
        bench=Bench.B,
        gymnast_id=gymnast.id,
        activated_by_user_id=context['admin'].id,
    )
    db.session.add(activation)
    db.session.flush()
    score_entry = ScoreEntry(
        gymnast_id=gymnast.id,
        judge_assignment_id=assignment.id,
        activation_id=activation.id,
    )
    db.session.add(score_entry)
    db.session.add(
        JudgeAccessWindow(
            judge_user_id=context['judge_a'].id,
            championship_id=context['championship'].id,
            competition_day_id=second_day.id,
            starts_at=now - timedelta(hours=3),
            ends_at=now - timedelta(hours=2),
        )
    )
    db.session.commit()

    response = client.put(
        f'/api/v1/judge/scores/{score_entry.id}',
        json={
            'activation_id': str(activation.id),
            'value': '5.00',
        },
        headers=headers,
    )

    assert response.status_code == 403
    assert (
        response.get_json()['code']
        == 'ASSIGNMENT_ACCESS_WINDOW_CLOSED'
    )
