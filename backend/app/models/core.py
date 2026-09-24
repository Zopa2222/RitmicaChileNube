import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.enums import (
    AccountType,
    Bench,
    CalculationStatus,
    ChampionshipStatus,
    CredentialEventType,
    FileKind,
    JudgeRole,
    PublicationMode,
    ResolutionSource,
    Session,
    SubmissionStatus,
    UserStatus,
)


def enum_type(enum_class, name):
    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        validate_strings=True,
        create_constraint=True,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = 'users'

    account_type: Mapped[AccountType] = mapped_column(
        enum_type(AccountType, 'account_type'),
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rut_normalized: Mapped[str | None] = mapped_column(String(16), unique=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    judge_access_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    judge_access_version: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus, 'user_status'),
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "account_type <> 'JUDGE' OR rut_normalized IS NOT NULL",
            name='ck_judge_requires_rut',
        ),
        Index(
            'uq_users_single_fixed_account_type',
            'account_type',
            unique=True,
            postgresql_where=text(
                "account_type IN ('SUPER_ADMIN', 'GLOBAL_ADMIN')"
            ),
            sqlite_where=text(
                "account_type IN ('SUPER_ADMIN', 'GLOBAL_ADMIN')"
            ),
        ),
    )


class SystemRole(CreatedAtMixin, db.Model):
    __tablename__ = 'system_roles'

    id: Mapped[int] = mapped_column(
        SmallInteger,
        primary_key=True,
        default=1,
        server_default='1',
    )
    super_admin_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='RESTRICT'),
        unique=True,
        nullable=False,
    )
    global_admin_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='RESTRICT'),
        unique=True,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint('id = 1', name='ck_system_roles_single_row'),
        CheckConstraint(
            'super_admin_user_id <> global_admin_user_id',
            name='ck_system_roles_distinct_users',
        ),
    )


class CredentialEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, db.Model):
    __tablename__ = 'credential_events'

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    event_type: Mapped[CredentialEventType] = mapped_column(
        enum_type(CredentialEventType, 'credential_event_type'),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False,
    )


class AuthRecoveryRequest(UUIDPrimaryKeyMixin, CreatedAtMixin, db.Model):
    __tablename__ = 'auth_recovery_requests'

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='RESTRICT'),
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Championship(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = 'championships'

    name: Mapped[str] = mapped_column(String(180), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    zone: Mapped[str] = mapped_column(String(120), nullable=False)
    qualifier_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64),
        default='America/Santiago',
        server_default='America/Santiago',
        nullable=False,
    )
    status: Mapped[ChampionshipStatus] = mapped_column(
        enum_type(ChampionshipStatus, 'championship_status'),
        default=ChampionshipStatus.DRAFT,
        server_default=ChampionshipStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    responsible_admin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            'uq_championships_single_active',
            'status',
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )


class FileObject(UUIDPrimaryKeyMixin, CreatedAtMixin, db.Model):
    __tablename__ = 'files'

    championship_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('championships.id', ondelete='CASCADE'),
        index=True,
    )
    kind: Mapped[FileKind] = mapped_column(
        enum_type(FileKind, 'file_kind'),
        nullable=False,
    )
    bucket_object: Mapped[str] = mapped_column(
        String(512),
        unique=True,
        nullable=False,
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class ImportPreview(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = 'import_previews'

    championship_draft_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('championships.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('files.id', ondelete='CASCADE'),
        nullable=False,
    )
    detected_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    decisions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class CompetitionDay(UUIDPrimaryKeyMixin, CreatedAtMixin, db.Model):
    __tablename__ = 'competition_days'

    championship_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('championships.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    competition_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_sheet_name: Mapped[str] = mapped_column(String(100), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            'championship_id',
            'sequence',
            name='uq_competition_days_sequence',
        ),
        UniqueConstraint(
            'championship_id',
            'competition_date',
            name='uq_competition_days_date',
        ),
        CheckConstraint('sequence >= 1', name='ck_competition_day_sequence'),
    )


class Category(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = 'categories'

    championship_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('championships.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    competition_day_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('competition_days.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    bench: Mapped[Bench] = mapped_column(
        enum_type(Bench, 'bench'),
        nullable=False,
    )
    session: Mapped[Session] = mapped_column(
        enum_type(Session, 'session'),
        nullable=False,
    )
    passing_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row: Mapped[int | None] = mapped_column(Integer)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            'competition_day_id',
            'bench',
            'session',
            'passing_order',
            name='uq_categories_passing_order',
        ),
        CheckConstraint('passing_order >= 0', name='ck_category_passing_order'),
        CheckConstraint(
            'source_row IS NULL OR source_row >= 1',
            name='ck_category_source_row',
        ),
    )


class Gymnast(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = 'gymnasts'

    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('categories.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(180), nullable=False)
    club_name: Mapped[str] = mapped_column(
        String(180),
        default='',
        server_default='',
        nullable=False,
    )
    passing_order: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
    )

    __table_args__ = (
        CheckConstraint('passing_order >= 0', name='ck_gymnast_passing_order'),
        Index(
            'uq_gymnasts_active_passing_order',
            'category_id',
            'passing_order',
            unique=True,
            postgresql_where=text('deleted_at IS NULL'),
            sqlite_where=text('deleted_at IS NULL'),
        ),
    )


class JudgeAssignment(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = 'judge_assignments'

    championship_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('championships.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    judge_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False,
        index=True,
    )
    competition_day_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('competition_days.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    bench: Mapped[Bench] = mapped_column(
        enum_type(Bench, 'assignment_bench'),
        nullable=False,
    )
    session: Mapped[Session] = mapped_column(
        enum_type(Session, 'assignment_session'),
        nullable=False,
    )
    role: Mapped[JudgeRole] = mapped_column(
        enum_type(JudgeRole, 'judge_role'),
        nullable=False,
    )
    effective_from_category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('categories.id', ondelete='RESTRICT'),
        nullable=False,
    )
    effective_to_category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('categories.id', ondelete='RESTRICT'),
    )
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False,
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            'ix_judge_assignments_scope',
            'championship_id',
            'competition_day_id',
            'bench',
            'session',
            'role',
        ),
        Index(
            'uq_judge_assignments_open_scope',
            'championship_id',
            'judge_user_id',
            'competition_day_id',
            'bench',
            'session',
            unique=True,
            postgresql_where=text('superseded_at IS NULL'),
            sqlite_where=text('superseded_at IS NULL'),
        ),
    )


class JudgeAccessWindow(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = 'judge_access_windows'

    judge_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    championship_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('championships.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    competition_day_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('competition_days.id', ondelete='CASCADE'),
        nullable=False,
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            'judge_user_id',
            'championship_id',
            'competition_day_id',
            name='uq_judge_access_window_day',
        ),
        CheckConstraint('ends_at > starts_at', name='ck_access_window_duration'),
    )


class BenchActivation(UUIDPrimaryKeyMixin, CreatedAtMixin, db.Model):
    __tablename__ = 'bench_activations'

    championship_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('championships.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    competition_day_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('competition_days.id', ondelete='CASCADE'),
        nullable=False,
    )
    bench: Mapped[Bench] = mapped_column(
        enum_type(Bench, 'activation_bench'),
        nullable=False,
    )
    gymnast_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('gymnasts.id', ondelete='RESTRICT'),
        nullable=False,
        index=True,
    )
    activated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False,
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    __table_args__ = (
        Index(
            'uq_bench_activations_open',
            'championship_id',
            'competition_day_id',
            'bench',
            unique=True,
            postgresql_where=text('deactivated_at IS NULL'),
            sqlite_where=text('deactivated_at IS NULL'),
        ),
    )


class ScoreEntry(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = 'score_entries'

    gymnast_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('gymnasts.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    judge_assignment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('judge_assignments.id', ondelete='RESTRICT'),
        nullable=False,
        index=True,
    )
    activation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('bench_activations.id', ondelete='RESTRICT'),
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal('0.00'),
        server_default='0.00',
        nullable=False,
    )
    submission_status: Mapped[SubmissionStatus] = mapped_column(
        enum_type(SubmissionStatus, 'submission_status'),
        default=SubmissionStatus.PENDING,
        server_default=SubmissionStatus.PENDING.value,
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_modified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
    )

    assignment: Mapped[JudgeAssignment] = relationship(lazy='joined')

    __table_args__ = (
        UniqueConstraint(
            'gymnast_id',
            'judge_assignment_id',
            name='uq_score_entries_gymnast_assignment',
        ),
        CheckConstraint(
            'value >= 0 AND value <= 20',
            name='ck_score_entry_value_range',
        ),
    )


class RoleScoreResolution(TimestampMixin, db.Model):
    __tablename__ = 'role_score_resolutions'

    gymnast_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('gymnasts.id', ondelete='CASCADE'),
        primary_key=True,
    )
    role: Mapped[JudgeRole] = mapped_column(
        enum_type(JudgeRole, 'resolution_role'),
        primary_key=True,
    )
    effective_value: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal('0.00'),
        server_default='0.00',
        nullable=False,
    )
    first_received_value: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    first_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    source: Mapped[ResolutionSource] = mapped_column(
        enum_type(ResolutionSource, 'resolution_source'),
        default=ResolutionSource.AUTO,
        server_default=ResolutionSource.AUTO.value,
        nullable=False,
    )
    has_discrepancy: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text('false'),
        nullable=False,
    )
    discrepancy_revision: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default='0',
        nullable=False,
    )
    acknowledged_revision: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default='0',
        nullable=False,
    )
    values_fingerprint: Mapped[str | None] = mapped_column(String(64))
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
    )

    __table_args__ = (
        CheckConstraint("role IN ('DA', 'DB')", name='ck_resolution_role'),
        CheckConstraint(
            'effective_value >= 0 AND effective_value <= 20',
            name='ck_resolution_effective_value_range',
        ),
        CheckConstraint(
            'first_received_value IS NULL OR '
            '(first_received_value >= 0 AND first_received_value <= 20)',
            name='ck_resolution_first_value_range',
        ),
        CheckConstraint(
            'discrepancy_revision >= acknowledged_revision',
            name='ck_resolution_revisions',
        ),
    )

    @property
    def warning_active(self):
        return (
            self.has_discrepancy
            and self.discrepancy_revision > self.acknowledged_revision
        )


class ScoreSummary(TimestampMixin, db.Model):
    __tablename__ = 'score_summaries'

    gymnast_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('gymnasts.id', ondelete='CASCADE'),
        primary_key=True,
    )
    da_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal('0.00'),
        server_default='0.00',
        nullable=False,
    )
    db_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal('0.00'),
        server_default='0.00',
        nullable=False,
    )
    a_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal('10.00'),
        server_default='10.00',
        nullable=False,
    )
    e_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal('10.00'),
        server_default='10.00',
        nullable=False,
    )
    discount: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal('0.00'),
        server_default='0.00',
        nullable=False,
    )
    total_score: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        default=Decimal('20.00'),
        server_default='20.00',
        nullable=False,
    )
    calculation_status: Mapped[CalculationStatus] = mapped_column(
        enum_type(CalculationStatus, 'calculation_status'),
        default=CalculationStatus.PROVISIONAL,
        server_default=CalculationStatus.PROVISIONAL.value,
        nullable=False,
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            'da_score BETWEEN 0 AND 20 AND db_score BETWEEN 0 AND 20',
            name='ck_summary_difficulty_ranges',
        ),
        CheckConstraint(
            'a_score BETWEEN -10 AND 10 AND e_score BETWEEN -10 AND 10',
            name='ck_summary_area_ranges',
        ),
        CheckConstraint(
            'discount BETWEEN 0 AND 20',
            name='ck_summary_discount_range',
        ),
        CheckConstraint(
            'total_score BETWEEN 0 AND 60',
            name='ck_summary_total_range',
        ),
    )


class PublicationBatch(UUIDPrimaryKeyMixin, CreatedAtMixin, db.Model):
    __tablename__ = 'publication_batches'

    championship_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('championships.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('categories.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    mode: Mapped[PublicationMode] = mapped_column(
        enum_type(PublicationMode, 'publication_mode'),
        nullable=False,
    )
    up_to_gymnast_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('gymnasts.id', ondelete='SET NULL'),
    )
    published_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False,
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        CheckConstraint(
            "(mode = 'UP_TO_GYMNAST' AND up_to_gymnast_id IS NOT NULL) OR "
            "(mode = 'FULL_CATEGORY' AND up_to_gymnast_id IS NULL)",
            name='ck_publication_batch_target',
        ),
    )


class PublishedResult(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = 'published_results'

    publication_batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('publication_batches.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    gymnast_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('gymnasts.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('categories.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    club_name: Mapped[str] = mapped_column(String(180), nullable=False)
    passing_order: Mapped[int] = mapped_column(Integer, nullable=False)
    db_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    da_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    discount: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    total_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    e_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    a_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    display_position: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint(
            'publication_batch_id',
            'gymnast_id',
            name='uq_published_results_batch_gymnast',
        ),
        CheckConstraint('passing_order >= 0', name='ck_published_passing_order'),
        CheckConstraint(
            'total_score BETWEEN 0 AND 60',
            name='ck_published_total_range',
        ),
    )


class AuditLog(UUIDPrimaryKeyMixin, db.Model):
    __tablename__ = 'audit_logs'

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    championship_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('championships.id', ondelete='SET NULL'),
        index=True,
    )
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index(
            'ix_audit_logs_championship_occurred',
            'championship_id',
            'occurred_at',
        ),
    )


class ChampionshipDeletionConfirmation(
    UUIDPrimaryKeyMixin,
    CreatedAtMixin,
    db.Model,
):
    __tablename__ = 'championship_deletion_confirmations'

    championship_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('championships.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    confirmed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False,
    )
    confirmation_step: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            'championship_id',
            'confirmation_step',
            name='uq_deletion_confirmation_step',
        ),
        CheckConstraint(
            'confirmation_step BETWEEN 1 AND 3',
            name='ck_deletion_confirmation_step',
        ),
    )
