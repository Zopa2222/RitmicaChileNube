import { JudgeAccessWindow } from './auth.model';

export type ChampionshipStatus =
    | 'DRAFT'
    | 'ACTIVE'
    | 'PAUSED'
    | 'CLOSED'
    | 'PENDING_DELETION'
    | 'DELETED';
export type Bench = 'A' | 'B';
export type CompetitionSession = 'AM' | 'PM';
export type JudgeRole = 'DA' | 'DB' | 'A' | 'E' | 'L' | 'P';
export type SubmissionStatus = 'PENDING' | 'SUBMITTED';
export type CalculationStatus = 'PROVISIONAL' | 'COMPLETE';

export interface CloudChampionship {
    id: string;
    name: string;
    kind: string;
    zone: string;
    start_date: string;
    timezone: string;
    status: ChampionshipStatus;
    responsible_admin_id: string;
    created_at: string;
}

export interface ChampionshipCounts {
    days: number;
    categories: number;
    gymnasts: number;
}

export interface CloudChampionshipDetail extends CloudChampionship {
    counts: ChampionshipCounts;
}

export interface CreateChampionshipRequest {
    name: string;
    kind: string;
    zone: string;
    start_date: string;
}

export interface CompetitionDay {
    id: string;
    sequence: number;
    date: string;
    sheet_name: string;
}

export interface ImportMarker {
    row: number;
    text: string;
    kinds: string[];
    duration_minutes: number | null;
    primary_candidate: boolean;
    eligible_cutoff: boolean;
}

export interface ImportGymnast {
    full_name: string;
    club_name: string;
    passing_order: number;
    source_row: number;
}

export interface ImportCategory {
    name: string;
    bench: Bench;
    session: CompetitionSession | null;
    passing_order: number;
    first_row: number;
    gymnast_count: number;
    gymnasts?: ImportGymnast[];
}

export interface ImportScopeSummary {
    categories: number;
    gymnasts: number;
}

export type ImportSheetSummary = Record<
    Bench,
    Record<CompetitionSession, ImportScopeSummary>
>;

export interface ImportPreviewSheet {
    sequence: number;
    name: string;
    max_content_row: number;
    markers: ImportMarker[];
    detected_cutoff_row: number | null;
    selected_cutoff_row: number | null;
    cutoff_confirmed: boolean;
    requires_manual_decision: boolean;
    summary: ImportSheetSummary;
    categories: ImportCategory[];
}

export interface ImportPreviewData {
    version: number;
    total_days: number;
    total_categories: number;
    total_gymnasts: number;
    sheets: ImportPreviewSheet[];
}

export interface ImportCutoffDecision {
    sequence: number;
    cutoff_row: number;
    confirmed?: boolean;
}

export interface ImportPreview {
    id: string;
    championship_id: string;
    expires_at: string;
    decisions: {
        sheets: Record<
            string,
            {
                cutoff_row: number;
                confirmed: boolean;
                source: 'AUTO' | 'MANUAL';
            }
        >;
        import_confirmed_at?: string;
        confirmed_by_user_id?: string;
    };
    preview: ImportPreviewData;
}

export interface CloudJudge {
    id: string;
    first_name: string;
    last_name: string;
    rut: string;
    username: string;
    status: 'ACTIVE' | 'DISABLED' | 'LOCKED';
    last_login_at?: string | null;
}

export interface JudgeIdentityInput {
    first_name: string;
    last_name: string;
    rut: string;
}

export interface InitialCredentials {
    username: string;
    password: string;
}

export interface CategoryReference {
    id: string;
    name: string;
    passing_order: number;
}

export interface JudgeAssignment {
    id: string;
    judge: CloudJudge;
    competition_day: CompetitionDay;
    bench: Bench;
    session: CompetitionSession;
    role: JudgeRole;
    effective_from_category: CategoryReference;
    effective_to_category: CategoryReference | null;
    superseded_at: string | null;
    access_window: Pick<JudgeAccessWindow, 'starts_at' | 'ends_at'> | null;
}

export interface CreateJudgeAssignmentRequest {
    competition_day_id: string;
    bench: Bench;
    session: CompetitionSession;
    role: JudgeRole;
    judge_id?: string;
    judge?: JudgeIdentityInput;
}

export interface ReassignJudgeRequest {
    judge_id?: string;
    judge?: JudgeIdentityInput;
}

export interface OperationGymnast {
    id: string;
    full_name: string;
    club_name: string;
    passing_order: number;
}

export interface OperationCategory {
    id: string;
    name: string;
    session: CompetitionSession;
    passing_order: number;
    gymnasts: OperationGymnast[];
}

export interface ActiveGymnast {
    activation_id: string;
    gymnast_id: string;
    full_name: string;
    activated_at: string;
}

export interface BenchOperations {
    active: ActiveGymnast | null;
    categories: OperationCategory[];
}

export interface CompetitionDayOperations {
    championship: CloudChampionship;
    competition_day: CompetitionDay;
    benches: Record<Bench, BenchOperations>;
}

export interface BenchActivation {
    id: string;
    championship_id: string;
    competition_day_id: string;
    bench: Bench;
    gymnast: {
        id: string;
        full_name: string;
        club_name: string;
    };
    category: {
        id: string;
        name: string;
        session: CompetitionSession;
    };
    activated_at: string;
}

export interface ScoreEntry {
    id: string;
    assignment_id?: string;
    role?: JudgeRole;
    value: string;
    submission_status: SubmissionStatus;
    submitted_at: string | null;
    last_modified_by_user_id?: string | null;
}

export interface ScoreSummary {
    da_score: string;
    db_score: string;
    a_score: string;
    e_score: string;
    discount: string;
    total_score: string;
    calculation_status: CalculationStatus;
    calculated_at: string | null;
}

export interface RoleResolution {
    role: 'DA' | 'DB';
    effective_value: string;
    first_received_value: string | null;
    source: 'AUTO' | 'ADMIN';
    has_discrepancy: boolean;
    warning_active: boolean;
    discrepancy_revision: number;
    acknowledged_revision: number;
}

export interface ScoringAssignment {
    id: string;
    role: JudgeRole;
    scoring: boolean;
    judge: {
        id: string;
        first_name: string;
        last_name: string;
    };
}

export interface ScoringGymnast extends OperationGymnast {
    is_active: boolean;
    activation_id: string | null;
    scores: ScoreEntry[];
    pending_count: number;
    area_warnings: Record<'A' | 'E', boolean>;
    role_resolutions: Record<'DA' | 'DB', RoleResolution>;
    summary: ScoreSummary;
}

export interface CategoryScoring {
    championship: Pick<CloudChampionship, 'id' | 'name' | 'status'>;
    competition_day: Omit<CompetitionDay, 'sheet_name'>;
    category: {
        id: string;
        name: string;
        bench: Bench;
        session: CompetitionSession;
        passing_order: number;
    };
    assignments: ScoringAssignment[];
    gymnasts: ScoringGymnast[];
}

export type JudgeContextState =
    | 'WAITING_FOR_CHAMPIONSHIP'
    | 'WAITING_FOR_GYMNAST'
    | 'WAITING_FOR_SESSION'
    | 'WAITING_FOR_EFFECTIVE_CATEGORY'
    | 'SCORE_NOT_INITIALIZED'
    | 'ACTIVE';

export interface JudgeContext {
    assignment_id: string;
    championship: Pick<CloudChampionship, 'id' | 'name'>;
    competition_day: Omit<CompetitionDay, 'sheet_name'>;
    bench: Bench;
    session: CompetitionSession;
    role: JudgeRole;
    can_score: boolean;
    state: JudgeContextState;
    active: {
        activation_id: string;
        gymnast: Pick<OperationGymnast, 'id' | 'full_name' | 'club_name'>;
        category: Pick<OperationCategory, 'id' | 'name'>;
        score: ScoreEntry | null;
    } | null;
}

export interface CategoryPublication {
    id: string;
    championship_id: string;
    category_id: string;
    mode: 'FULL_CATEGORY';
    published_at: string;
    result_count: number;
}

export interface PublishedResult {
    gymnast_id: string;
    display_name: string;
    club_name: string;
    passing_order: number;
    total_score: string;
    display_position: number;
}

export interface AuditLogEntry {
    id: string;
    occurred_at: string;
    actor_user_id: string | null;
    action: string;
    championship_id: string | null;
    championship: { id: string; name: string } | null;
    entity_type: string | null;
    entity_id: string | null;
    details: Record<string, unknown>;
}
