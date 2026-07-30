import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
    CategoryScoring,
    OperationGymnast,
    RoleResolution,
    ScoreEntry,
    ScoreSummary
} from '../models/cloud.model';

interface ChangeResponse {
    changed: boolean;
}

@Injectable({ providedIn: 'root' })
export class CloudScoringApiService {
    private readonly apiUrl = `${environment.apiUrl}/api/v1/championships`;

    constructor(private readonly http: HttpClient) { }

    getCategory(
        championshipId: string,
        categoryId: string
    ): Observable<CategoryScoring> {
        return this.http.get<CategoryScoring>(
            `${this.apiUrl}/${championshipId}/categories/${categoryId}/scoring`
        );
    }

    addGymnast(
        championshipId: string,
        categoryId: string,
        request: {
            full_name: string;
            club_name?: string;
            passing_order?: number;
        }
    ): Observable<{
        gymnast: OperationGymnast;
        initialized_scores: number;
        summary: ScoreSummary;
        changed: boolean;
    }> {
        return this.http.post<{
            gymnast: OperationGymnast;
            initialized_scores: number;
            summary: ScoreSummary;
            changed: boolean;
        }>(
            `${this.apiUrl}/${championshipId}/categories/${categoryId}/gymnasts`,
            request
        );
    }

    removeGymnast(
        championshipId: string,
        gymnastId: string
    ): Observable<{
        gymnast_id: string;
        active_activation_cleared: boolean;
        gymnasts: OperationGymnast[];
        changed: boolean;
    }> {
        return this.http.delete<{
            gymnast_id: string;
            active_activation_cleared: boolean;
            gymnasts: OperationGymnast[];
            changed: boolean;
        }>(`${this.apiUrl}/${championshipId}/gymnasts/${gymnastId}`);
    }

    reorderGymnasts(
        championshipId: string,
        categoryId: string,
        gymnastIds: string[]
    ): Observable<{
        order_mode: 'MANUAL';
        gymnasts: OperationGymnast[];
        changed: boolean;
    }> {
        return this.http.put<{
            order_mode: 'MANUAL';
            gymnasts: OperationGymnast[];
            changed: boolean;
        }>(
            `${this.apiUrl}/${championshipId}/categories`
            + `/${categoryId}/gymnasts/order`,
            { gymnast_ids: gymnastIds }
        );
    }

    orderGymnastsByScore(
        championshipId: string,
        categoryId: string
    ): Observable<{
        order_mode: 'SCORE';
        gymnasts: Array<OperationGymnast & {
            total_score: string;
            e_score: string;
            a_score: string;
        }>;
        changed: boolean;
    }> {
        return this.http.post<{
            order_mode: 'SCORE';
            gymnasts: Array<OperationGymnast & {
                total_score: string;
                e_score: string;
                a_score: string;
            }>;
            changed: boolean;
        }>(
            `${this.apiUrl}/${championshipId}/categories`
            + `/${categoryId}/gymnasts/order-by-score`,
            {}
        );
    }

    updateScore(
        championshipId: string,
        scoreEntryId: string,
        value: string | number
    ): Observable<ChangeResponse & {
        score: ScoreEntry;
        summary: ScoreSummary;
    }> {
        return this.http.put<ChangeResponse & {
            score: ScoreEntry;
            summary: ScoreSummary;
        }>(
            `${this.apiUrl}/${championshipId}/score-entries/${scoreEntryId}`,
            { value }
        );
    }

    updateDiscount(
        championshipId: string,
        gymnastId: string,
        value: string | number
    ): Observable<ChangeResponse & { summary: ScoreSummary }> {
        return this.http.put<ChangeResponse & { summary: ScoreSummary }>(
            `${this.apiUrl}/${championshipId}/gymnasts/${gymnastId}/discount`,
            { value }
        );
    }

    resolveRole(
        championshipId: string,
        gymnastId: string,
        role: 'DA' | 'DB',
        value?: string | number
    ): Observable<ChangeResponse & {
        resolution: RoleResolution;
        summary: ScoreSummary;
    }> {
        const request = value === undefined ? {} : { value };
        return this.http.put<ChangeResponse & {
            resolution: RoleResolution;
            summary: ScoreSummary;
        }>(
            `${this.apiUrl}/${championshipId}/gymnasts/${gymnastId}`
            + `/role-resolutions/${role}`,
            request
        );
    }
}
