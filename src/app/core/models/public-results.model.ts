export interface PublicChampionship {
    id: string;
    name: string;
    kind: string;
    zone: string;
    qualifier_number?: 1 | 2 | null;
    start_date: string;
}

export interface PublicCompetitionDay {
    id: string;
    sequence: number;
    date: string;
}

export interface PublicPublication {
    id: string;
    published_at: string;
}

export interface PublicCategorySummary {
    id: string;
    name: string;
    bench: 'A' | 'B';
    session: 'AM' | 'PM';
    passing_order: number;
    gymnast_count: number;
    competition_day: PublicCompetitionDay;
    publication: PublicPublication | null;
}

export interface PublicCatalogResponse {
    championship: PublicChampionship;
    query: string;
    categories: PublicCategorySummary[];
}

export interface PublicResult {
    gymnast_id: string;
    display_name: string;
    club_name: string;
    passing_order: number;
    total_score: string;
    display_position: number;
    is_published: boolean;
}

export type PublicSortMode = 'passing_order' | 'score';

export interface PublicCategoryResultsResponse {
    championship: Omit<PublicChampionship, 'start_date'>;
    category: Pick<
        PublicCategorySummary,
        'id' | 'name' | 'bench' | 'session'
    >;
    publication: PublicPublication | null;
    query: string;
    sort: PublicSortMode;
    results: PublicResult[];
}
