from datetime import datetime, timezone

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Gymnast,
    PublicationBatch,
    PublicationMode,
    PublishedResult,
)
from app.services.cloud_scoring_service import refresh_score_summary


def category_gymnasts_for_publication(category_id):
    return db.session.execute(
        select(Gymnast)
        .where(
            Gymnast.category_id == category_id,
            Gymnast.deleted_at.is_(None),
        )
        .order_by(Gymnast.passing_order, Gymnast.id)
        .with_for_update(of=Gymnast)
    ).scalars().all()


def publish_full_category(
    championship,
    category,
    published_by_user_id,
    published_at=None,
):
    """Create one immutable full-category snapshot for one explicit action."""
    timestamp = published_at or datetime.now(timezone.utc)
    gymnasts = category_gymnasts_for_publication(category.id)
    return _create_publication_snapshot(
        championship,
        category,
        gymnasts,
        published_by_user_id,
        PublicationMode.FULL_CATEGORY,
        None,
        timestamp,
    )


def publish_up_to_gymnast(
    championship,
    category,
    gymnast,
    published_by_user_id,
    published_at=None,
):
    """Snapshot the category through the active gymnast's passing order."""
    timestamp = published_at or datetime.now(timezone.utc)
    gymnasts = [
        candidate
        for candidate in category_gymnasts_for_publication(category.id)
        if candidate.passing_order <= gymnast.passing_order
    ]
    return _create_publication_snapshot(
        championship,
        category,
        gymnasts,
        published_by_user_id,
        PublicationMode.UP_TO_GYMNAST,
        gymnast.id,
        timestamp,
    )


def _create_publication_snapshot(
    championship,
    category,
    gymnasts,
    published_by_user_id,
    mode,
    up_to_gymnast_id,
    timestamp,
):
    summaries = {
        gymnast.id: refresh_score_summary(
            gymnast.id,
            timestamp,
        )
        for gymnast in gymnasts
    }
    ranked = sorted(
        gymnasts,
        key=lambda gymnast: (
            -summaries[gymnast.id].total_score,
            -summaries[gymnast.id].e_score,
            -summaries[gymnast.id].a_score,
            gymnast.passing_order,
            str(gymnast.id),
        ),
    )
    position_by_gymnast_id = {
        gymnast.id: position
        for position, gymnast in enumerate(ranked, start=1)
    }

    batch = PublicationBatch(
        championship_id=championship.id,
        category_id=category.id,
        mode=mode,
        up_to_gymnast_id=up_to_gymnast_id,
        published_by_user_id=published_by_user_id,
        published_at=timestamp,
    )
    db.session.add(batch)
    db.session.flush()

    results = []
    for gymnast in gymnasts:
        summary = summaries[gymnast.id]
        result = PublishedResult(
            publication_batch_id=batch.id,
            gymnast_id=gymnast.id,
            category_id=category.id,
            display_name=gymnast.full_name,
            club_name=gymnast.club_name,
            passing_order=gymnast.passing_order,
            db_score=summary.db_score,
            da_score=summary.da_score,
            discount=summary.discount,
            total_score=summary.total_score,
            e_score=summary.e_score,
            a_score=summary.a_score,
            display_position=position_by_gymnast_id[gymnast.id],
            published_at=timestamp,
        )
        db.session.add(result)
        results.append(result)
    db.session.flush()
    return batch, results


def latest_category_publication(championship_id, category_id):
    return db.session.execute(
        select(PublicationBatch)
        .where(
            PublicationBatch.championship_id == championship_id,
            PublicationBatch.category_id == category_id,
        )
        .order_by(
            PublicationBatch.published_at.desc(),
            PublicationBatch.created_at.desc(),
            PublicationBatch.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()


def results_for_publication(publication_batch_id):
    return db.session.execute(
        select(PublishedResult)
        .where(
            PublishedResult.publication_batch_id
            == publication_batch_id
        )
        .order_by(
            PublishedResult.passing_order,
            PublishedResult.id,
        )
    ).scalars().all()
