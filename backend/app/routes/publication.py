import uuid
import unicodedata
from decimal import Decimal

from flask import Blueprint, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AccountType,
    AuditLog,
    Category,
    Championship,
    ChampionshipStatus,
    CompetitionDay,
    Gymnast,
)
from app.routes.cloud_championships import (
    get_championship_or_404,
    validation_error,
)
from app.security.permissions import account_types_required
from app.services.publication_service import (
    latest_category_publication,
    publish_full_category,
    results_for_publication,
)


bp = Blueprint('publication', __name__, url_prefix='/api/v1')
ADMIN_ACCOUNT_TYPES = (
    AccountType.SUPER_ADMIN,
    AccountType.GLOBAL_ADMIN,
)


class PublicationError(ValueError):
    def __init__(self, message, code='PUBLICATION_ERROR', status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def parse_uuid_value(raw_value, field_name):
    try:
        return uuid.UUID(str(raw_value))
    except (TypeError, ValueError, AttributeError):
        raise PublicationError(
            f'{field_name} no es válido',
            code='INVALID_IDENTIFIER',
            status=400,
        ) from None


def decimal_response(value):
    return format(Decimal(value), '.2f')


def normalized_search_text(value):
    decomposed = unicodedata.normalize('NFD', str(value or '').casefold())
    return ''.join(
        character
        for character in decomposed
        if unicodedata.category(character) != 'Mn'
    ).strip()


def get_category(championship, category_id):
    category = db.session.get(
        Category,
        parse_uuid_value(category_id, 'category_id'),
    )
    if (
        category is None
        or category.championship_id != championship.id
        or category.deleted_at is not None
    ):
        raise PublicationError(
            'Categoría no encontrada',
            code='CATEGORY_NOT_FOUND',
            status=404,
        )
    return category


def error_response(error):
    return jsonify({
        'error': str(error),
        'code': error.code,
    }), error.status


def published_result_response(result):
    return {
        'gymnast_id': str(result.gymnast_id),
        'display_name': result.display_name,
        'club_name': result.club_name,
        'passing_order': result.passing_order,
        'total_score': decimal_response(result.total_score),
        'display_position': result.display_position,
    }


@bp.post(
    '/championships/<championship_id>/categories/'
    '<category_id>/publish'
)
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def publish_category(current_user, championship_id, category_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    try:
        category = get_category(championship, category_id)
        championship = db.session.execute(
            select(Championship)
            .where(Championship.id == championship.id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).scalar_one()
        if championship.status != ChampionshipStatus.ACTIVE:
            raise PublicationError(
                'Solo se publican categorías del campeonato activo',
                code='CHAMPIONSHIP_NOT_ACTIVE',
                status=409,
            )
        category = db.session.execute(
            select(Category)
            .where(Category.id == category.id)
            .execution_options(populate_existing=True)
            .with_for_update(of=Category)
        ).scalar_one()
        batch, results = publish_full_category(
            championship,
            category,
            current_user.id,
        )
        db.session.add(
            AuditLog(
                actor_user_id=current_user.id,
                action='CATEGORY_PUBLISHED',
                championship_id=championship.id,
                entity_type='PUBLICATION_BATCH',
                entity_id=batch.id,
                details={
                    'category_id': str(category.id),
                    'mode': 'FULL_CATEGORY',
                    'result_count': len(results),
                },
            )
        )
        db.session.commit()
    except PublicationError as error:
        db.session.rollback()
        return error_response(error)
    except IntegrityError:
        db.session.rollback()
        return validation_error(
            'La categoría no pudo publicarse por un cambio simultáneo',
            code='PUBLICATION_CONFLICT',
            status=409,
        )
    return jsonify({
        'publication': {
            'id': str(batch.id),
            'championship_id': str(championship.id),
            'category_id': str(category.id),
            'mode': batch.mode.value,
            'published_at': batch.published_at.isoformat(),
            'result_count': len(results),
        },
        'results': [
            published_result_response(result)
            for result in results
        ],
    }), 201


@bp.get(
    '/public/championships/active'
)
def public_active_championship():
    championship = db.session.execute(
        select(Championship).where(
            Championship.status == ChampionshipStatus.ACTIVE
        )
    ).scalar_one_or_none()
    if championship is None:
        return validation_error(
            'No existe un campeonato activo',
            code='ACTIVE_CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )

    search_term = normalized_search_text(request.args.get('query'))
    categories = db.session.execute(
        select(Category)
        .where(
            Category.championship_id == championship.id,
            Category.deleted_at.is_(None),
        )
        .order_by(
            Category.competition_day_id,
            Category.bench,
            Category.session,
            Category.passing_order,
            Category.id,
        )
    ).scalars().all()
    day_by_id = {
        day.id: day
        for day in db.session.execute(
            select(CompetitionDay).where(
                CompetitionDay.championship_id == championship.id
            )
        ).scalars()
    }
    category_payload = []
    for category in categories:
        gymnasts = db.session.execute(
            select(Gymnast)
            .where(
                Gymnast.category_id == category.id,
                Gymnast.deleted_at.is_(None),
            )
            .order_by(Gymnast.passing_order, Gymnast.id)
        ).scalars().all()
        if search_term:
            searchable_values = [
                category.name,
                *[
                    value
                    for gymnast in gymnasts
                    for value in (
                        gymnast.full_name,
                        gymnast.club_name,
                    )
                ],
            ]
            if not any(
                search_term in normalized_search_text(value)
                for value in searchable_values
            ):
                continue
        batch = latest_category_publication(
            championship.id,
            category.id,
        )
        day = day_by_id[category.competition_day_id]
        category_payload.append({
            'id': str(category.id),
            'name': category.name,
            'bench': category.bench.value,
            'session': category.session.value,
            'passing_order': category.passing_order,
            'gymnast_count': len(gymnasts),
            'competition_day': {
                'id': str(day.id),
                'sequence': day.sequence,
                'date': day.competition_date.isoformat(),
            },
            'publication': (
                {
                    'id': str(batch.id),
                    'published_at': batch.published_at.isoformat(),
                }
                if batch else None
            ),
        })
    category_payload.sort(
        key=lambda category: (
            category['competition_day']['sequence'],
            category['bench'],
            category['session'],
            category['passing_order'],
            category['id'],
        )
    )
    return jsonify({
        'championship': {
            'id': str(championship.id),
            'name': championship.name,
            'kind': championship.kind,
            'zone': championship.zone,
            'qualifier_number': championship.qualifier_number,
            'start_date': championship.start_date.isoformat(),
        },
        'query': request.args.get('query', '').strip(),
        'categories': category_payload,
    })


@bp.get(
    '/public/championships/active/categories/'
    '<category_id>/results'
)
def public_category_results(category_id):
    championship = db.session.execute(
        select(Championship).where(
            Championship.status == ChampionshipStatus.ACTIVE
        )
    ).scalar_one_or_none()
    if championship is None:
        return validation_error(
            'No existe un campeonato activo',
            code='ACTIVE_CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    try:
        category = get_category(championship, category_id)
    except PublicationError as error:
        return error_response(error)
    sort_mode = request.args.get('sort', 'passing_order').strip().lower()
    if sort_mode not in {'passing_order', 'score'}:
        return error_response(
            PublicationError(
                'El orden público debe ser passing_order o score',
                code='INVALID_PUBLIC_SORT',
                status=400,
            )
        )
    search_term = normalized_search_text(request.args.get('query'))

    gymnasts = db.session.execute(
        select(Gymnast)
        .where(
            Gymnast.category_id == category.id,
            Gymnast.deleted_at.is_(None),
        )
        .order_by(Gymnast.passing_order, Gymnast.id)
    ).scalars().all()
    batch = latest_category_publication(
        championship.id,
        category.id,
    )
    published_by_gymnast_id = {
        result.gymnast_id: result
        for result in (
            results_for_publication(batch.id)
            if batch else []
        )
    }
    public_results = []
    for gymnast in gymnasts:
        published = published_by_gymnast_id.get(gymnast.id)
        public_results.append({
            'gymnast_id': str(gymnast.id),
            'display_name': (
                published.display_name
                if published else gymnast.full_name
            ),
            'club_name': (
                published.club_name
                if published else gymnast.club_name
            ),
            'passing_order': (
                published.passing_order
                if published else gymnast.passing_order
            ),
            'total_score': (
                decimal_response(published.total_score)
                if published else '0.00'
            ),
            'display_position': (
                published.display_position
                if published else None
            ),
            'is_published': published is not None,
        })
    ranked_results = sorted(
        public_results,
        key=lambda result: (
            -Decimal(result['total_score']),
            (
                result['display_position']
                if result['display_position'] is not None
                else len(public_results) + result['passing_order'] + 1
            ),
            result['passing_order'],
            result['gymnast_id'],
        ),
    )
    rank_by_gymnast_id = {
        result['gymnast_id']: position
        for position, result in enumerate(ranked_results, start=1)
    }
    for result in public_results:
        result['display_position'] = rank_by_gymnast_id[
            result['gymnast_id']
        ]
    if search_term and (
        search_term not in normalized_search_text(category.name)
    ):
        public_results = [
            result
            for result in public_results
            if (
                search_term
                in normalized_search_text(result['display_name'])
                or search_term
                in normalized_search_text(result['club_name'])
            )
        ]
    if sort_mode == 'score':
        public_results.sort(
            key=lambda result: (
                result['display_position'],
                result['passing_order'],
                result['gymnast_id'],
            )
        )
    else:
        public_results.sort(
            key=lambda result: (
                result['passing_order'],
                result['gymnast_id'],
            )
        )
    return jsonify({
        'championship': {
            'id': str(championship.id),
            'name': championship.name,
            'kind': championship.kind,
            'zone': championship.zone,
            'qualifier_number': championship.qualifier_number,
        },
        'category': {
            'id': str(category.id),
            'name': category.name,
            'bench': category.bench.value,
            'session': category.session.value,
        },
        'publication': (
            {
                'id': str(batch.id),
                'mode': batch.mode.value,
                'published_at': batch.published_at.isoformat(),
            }
            if batch else None
        ),
        'query': request.args.get('query', '').strip(),
        'sort': sort_mode,
        'results': public_results,
    })
