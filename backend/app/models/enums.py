from enum import Enum


class AccountType(str, Enum):
    SUPER_ADMIN = 'SUPER_ADMIN'
    GLOBAL_ADMIN = 'GLOBAL_ADMIN'
    JUDGE = 'JUDGE'


class UserStatus(str, Enum):
    ACTIVE = 'ACTIVE'
    DISABLED = 'DISABLED'
    LOCKED = 'LOCKED'


class CredentialEventType(str, Enum):
    CREATED = 'CREATED'
    DELIVERED = 'DELIVERED'
    REGENERATED = 'REGENERATED'


class ChampionshipStatus(str, Enum):
    DRAFT = 'DRAFT'
    ACTIVE = 'ACTIVE'
    PAUSED = 'PAUSED'
    CLOSED = 'CLOSED'
    PENDING_DELETION = 'PENDING_DELETION'
    DELETED = 'DELETED'


class FileKind(str, Enum):
    SOURCE_EXCEL = 'SOURCE_EXCEL'
    EXCEL_EXPORT = 'EXCEL_EXPORT'
    PDF_EXPORT = 'PDF_EXPORT'


class Bench(str, Enum):
    A = 'A'
    B = 'B'


class Session(str, Enum):
    AM = 'AM'
    PM = 'PM'


class JudgeRole(str, Enum):
    DA = 'DA'
    DB = 'DB'
    A = 'A'
    E = 'E'
    L = 'L'
    P = 'P'


class SubmissionStatus(str, Enum):
    PENDING = 'PENDING'
    SUBMITTED = 'SUBMITTED'


class ResolutionSource(str, Enum):
    AUTO = 'AUTO'
    ADMIN = 'ADMIN'


class CalculationStatus(str, Enum):
    PROVISIONAL = 'PROVISIONAL'
    COMPLETE = 'COMPLETE'


class PublicationMode(str, Enum):
    UP_TO_GYMNAST = 'UP_TO_GYMNAST'
    FULL_CATEGORY = 'FULL_CATEGORY'
