from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AccountType,
    Bench,
    BenchActivation,
    Category,
    Championship,
    ChampionshipStatus,
    CompetitionDay,
    Gymnast,
    JudgeAssignment,
    JudgeRole,
    ScoreEntry,
    Session,
    SubmissionStatus,
    User,
)


def create_user(account_type, username, rut=None):
    user = User(
        account_type=account_type,
        first_name='Nombre',
        last_name='Apellido',
        rut_normalized=rut,
        username=username,
        password_hash='hash-de-prueba',
    )
    db.session.add(user)
    db.session.flush()
    return user


def create_scoring_context():
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    judge = create_user(AccountType.JUDGE, 'JUEZ1', '111111111')
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

    category = Category(
        championship_id=championship.id,
        competition_day_id=competition_day.id,
        name='MINI F',
        bench=Bench.A,
        session=Session.AM,
        passing_order=0,
        source_row=10,
    )
    db.session.add(category)
    db.session.flush()

    gymnast = Gymnast(
        category_id=category.id,
        full_name='Gimnasta Uno',
        club_name='Club',
        passing_order=0,
    )
    db.session.add(gymnast)
    db.session.flush()

    assignment = JudgeAssignment(
        championship_id=championship.id,
        judge_user_id=judge.id,
        competition_day_id=competition_day.id,
        bench=Bench.A,
        session=Session.AM,
        role=JudgeRole.A,
        effective_from_category_id=category.id,
        assigned_by_user_id=admin.id,
    )
    db.session.add(assignment)
    db.session.flush()

    return {
        'admin': admin,
        'judge': judge,
        'championship': championship,
        'day': competition_day,
        'category': category,
        'gymnast': gymnast,
        'assignment': assignment,
    }


def test_only_one_fixed_account_per_type(app):
    create_user(AccountType.GLOBAL_ADMIN, 'ADMIN1')
    db.session.commit()

    db.session.add(
        User(
            account_type=AccountType.GLOBAL_ADMIN,
            first_name='Otro',
            last_name='Administrador',
            username='ADMIN2',
            password_hash='hash-de-prueba',
        )
    )

    with pytest.raises(IntegrityError):
        db.session.commit()


def test_only_one_championship_can_be_active(app):
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    db.session.add(
        Championship(
            name='Primero',
            kind='CLASIFICATORIO',
            zone='CENTRO',
            start_date=date(2026, 8, 1),
            status=ChampionshipStatus.ACTIVE,
            responsible_admin_id=admin.id,
        )
    )
    db.session.commit()

    db.session.add(
        Championship(
            name='Segundo',
            kind='FINAL',
            zone='NACIONAL',
            start_date=date(2026, 9, 1),
            status=ChampionshipStatus.ACTIVE,
            responsible_admin_id=admin.id,
        )
    )

    with pytest.raises(IntegrityError):
        db.session.commit()


def test_score_defaults_to_pending_zero_and_enforces_range(app):
    context = create_scoring_context()
    score = ScoreEntry(
        gymnast_id=context['gymnast'].id,
        judge_assignment_id=context['assignment'].id,
    )
    db.session.add(score)
    db.session.commit()

    assert score.value == Decimal('0.00')
    assert score.submission_status == SubmissionStatus.PENDING

    score.value = Decimal('20.01')
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_only_one_open_activation_exists_per_day_and_bench(app):
    context = create_scoring_context()
    first = BenchActivation(
        championship_id=context['championship'].id,
        competition_day_id=context['day'].id,
        bench=Bench.A,
        gymnast_id=context['gymnast'].id,
        activated_by_user_id=context['admin'].id,
    )
    db.session.add(first)
    db.session.commit()

    second = BenchActivation(
        championship_id=context['championship'].id,
        competition_day_id=context['day'].id,
        bench=Bench.A,
        gymnast_id=context['gymnast'].id,
        activated_by_user_id=context['admin'].id,
    )
    db.session.add(second)

    with pytest.raises(IntegrityError):
        db.session.commit()


def test_judge_cannot_have_two_open_roles_in_same_scope(app):
    context = create_scoring_context()
    db.session.commit()

    db.session.add(
        JudgeAssignment(
            championship_id=context['championship'].id,
            judge_user_id=context['judge'].id,
            competition_day_id=context['day'].id,
            bench=Bench.A,
            session=Session.AM,
            role=JudgeRole.E,
            effective_from_category_id=context['category'].id,
            assigned_by_user_id=context['admin'].id,
        )
    )

    with pytest.raises(IntegrityError):
        db.session.commit()


def test_readiness_uses_sql_database(client):
    response = client.get('/health/ready')

    assert response.status_code == 200
    assert response.get_json() == {
        'status': 'ok',
        'database': 'available',
    }
