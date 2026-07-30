from datetime import date
from decimal import Decimal

import pytest

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
    ResolutionSource,
    RoleScoreResolution,
    ScoreEntry,
    ScoreSummary,
    Session,
    User,
)
from app.services.cloud_scoring_service import (
    ScoreValidationError,
    acknowledge_role_resolution,
    calculate_total_score,
    has_area_difference,
    parse_score_value,
    submit_judge_score,
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


def create_da_context():
    admin = create_user(AccountType.GLOBAL_ADMIN, 'ADMIN')
    judge_one = create_user(AccountType.JUDGE, 'JUEZ1', '111111111')
    judge_two = create_user(AccountType.JUDGE, 'JUEZ2', '222222222')
    championship = Championship(
        name='Final Nacional',
        kind='FINAL',
        zone='NACIONAL',
        start_date=date(2026, 10, 1),
        status=ChampionshipStatus.ACTIVE,
        responsible_admin_id=admin.id,
    )
    db.session.add(championship)
    db.session.flush()
    day = CompetitionDay(
        championship_id=championship.id,
        sequence=1,
        competition_date=championship.start_date,
        source_sheet_name='DIA 1',
    )
    db.session.add(day)
    db.session.flush()
    category = Category(
        championship_id=championship.id,
        competition_day_id=day.id,
        name='SENIOR',
        bench=Bench.A,
        session=Session.AM,
        passing_order=0,
    )
    db.session.add(category)
    db.session.flush()
    gymnast = Gymnast(
        category_id=category.id,
        full_name='Gimnasta',
        club_name='Club',
        passing_order=0,
    )
    db.session.add(gymnast)
    db.session.flush()

    assignments = []
    entries = []
    for judge in (judge_one, judge_two):
        assignment = JudgeAssignment(
            championship_id=championship.id,
            judge_user_id=judge.id,
            competition_day_id=day.id,
            bench=Bench.A,
            session=Session.AM,
            role=JudgeRole.DA,
            effective_from_category_id=category.id,
            assigned_by_user_id=admin.id,
        )
        db.session.add(assignment)
        db.session.flush()
        entry = ScoreEntry(
            gymnast_id=gymnast.id,
            judge_assignment_id=assignment.id,
        )
        db.session.add(entry)
        assignments.append(assignment)
        entries.append(entry)

    activation = BenchActivation(
        championship_id=championship.id,
        competition_day_id=day.id,
        bench=Bench.A,
        gymnast_id=gymnast.id,
        activated_by_user_id=admin.id,
    )
    db.session.add(activation)
    db.session.commit()

    return {
        'admin': admin,
        'judges': (judge_one, judge_two),
        'entries': entries,
        'activation': activation,
    }


@pytest.mark.parametrize(
    ('raw_value', 'expected'),
    [
        ('0', Decimal('0.00')),
        ('1,15', Decimal('1.15')),
        (1.15, Decimal('1.15')),
        ('20.00', Decimal('20.00')),
    ],
)
def test_score_parser_accepts_confirmed_format(raw_value, expected):
    assert parse_score_value(raw_value) == expected


@pytest.mark.parametrize(
    'raw_value',
    ['-0.01', '20.01', '1.155', '', 'texto', None, True],
)
def test_score_parser_rejects_invalid_values(raw_value):
    with pytest.raises(ScoreValidationError):
        parse_score_value(raw_value)


def test_pending_zero_values_participate_in_provisional_total():
    total = calculate_total_score(
        Decimal('0'),
        Decimal('0'),
        [Decimal('0'), Decimal('0')],
        [Decimal('0'), Decimal('0')],
        Decimal('0'),
    )

    assert total == Decimal('20.00')


def test_area_warning_uses_canonical_rule():
    assert not has_area_difference(['1.00', '1.60'])
    assert has_area_difference(['1.00', '1.61'])
    assert not has_area_difference(['1.00', '1.60', '2.20'])
    assert has_area_difference(['1.00', '1.61', '2.20'])
    assert not has_area_difference(['0.00', '1.00', '1.50', '3.00'])
    assert has_area_difference(['0.00', '1.00', '1.61', '3.00'])


def test_da_discrepancy_keeps_first_value_until_admin_decides(app):
    context = create_da_context()
    first_entry, second_entry = context['entries']
    first_judge, second_judge = context['judges']
    activation = context['activation']

    submit_judge_score(
        first_entry,
        '5.20',
        first_judge.id,
        activation.id,
    )
    submit_judge_score(
        second_entry,
        '5.40',
        second_judge.id,
        activation.id,
    )
    resolution = db.session.get(
        RoleScoreResolution,
        (first_entry.gymnast_id, JudgeRole.DA),
    )

    assert resolution.effective_value == Decimal('5.20')
    assert resolution.first_received_value == Decimal('5.20')
    assert resolution.warning_active
    summary = db.session.get(ScoreSummary, first_entry.gymnast_id)
    assert summary.da_score == Decimal('5.20')
    assert summary.total_score == Decimal('5.20')

    acknowledge_role_resolution(resolution, context['admin'].id)
    assert resolution.source == ResolutionSource.ADMIN
    assert not resolution.warning_active

    submit_judge_score(
        second_entry,
        '5.60',
        second_judge.id,
        activation.id,
    )

    assert resolution.effective_value == Decimal('5.20')
    assert resolution.warning_active
