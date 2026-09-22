import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
    Bench,
    BenchActivation,
    CompetitionDayOperations,
    CreateJudgeAssignmentRequest,
    JudgeAssignment,
    ReassignJudgeRequest
} from '../models/cloud.model';

@Injectable({ providedIn: 'root' })
export class CloudOperationsApiService {
    private readonly apiUrl = `${environment.apiUrl}/api/v1/championships`;

    constructor(private readonly http: HttpClient) { }

    getCompetitionDay(
        championshipId: string,
        competitionDayId: string
    ): Observable<CompetitionDayOperations> {
        return this.http.get<CompetitionDayOperations>(
            `${this.apiUrl}/${championshipId}/competition-days`
            + `/${competitionDayId}/operations`
        );
    }

    activateGymnast(
        championshipId: string,
        competitionDayId: string,
        bench: Bench,
        gymnastId: string
    ): Observable<{ activation: BenchActivation; changed: boolean }> {
        return this.http.put<{
            activation: BenchActivation;
            changed: boolean;
        }>(
            `${this.apiUrl}/${championshipId}/competition-days`
            + `/${competitionDayId}/benches/${bench}/active-gymnast`,
            { gymnast_id: gymnastId }
        );
    }

    passNext(
        championshipId: string,
        competitionDayId: string,
        bench: Bench
    ): Observable<{
        publication: {
            id: string;
            category_id: string;
            gymnast_id: string;
            mode: 'UP_TO_GYMNAST';
            published_at: string;
            result_count: number;
        };
        next_activation: {
            id: string;
            gymnast_id: string;
            full_name: string;
            category_id: string;
        } | null;
    }> {
        return this.http.post<{
            publication: {
                id: string;
                category_id: string;
                gymnast_id: string;
                mode: 'UP_TO_GYMNAST';
                published_at: string;
                result_count: number;
            };
            next_activation: {
                id: string;
                gymnast_id: string;
                full_name: string;
                category_id: string;
            } | null;
        }>(
            `${this.apiUrl}/${championshipId}/competition-days`
            + `/${competitionDayId}/benches/${bench}/pass-next`,
            {}
        );
    }

    listAssignments(championshipId: string): Observable<JudgeAssignment[]> {
        return this.http.get<{ assignments: JudgeAssignment[] }>(
            `${this.apiUrl}/${championshipId}/judge-assignments`
        ).pipe(map((response) => response.assignments));
    }

    createAssignment(
        championshipId: string,
        request: CreateJudgeAssignmentRequest
    ): Observable<{
        assignment: JudgeAssignment;
        credentials: { username: string; password: string } | null;
    }> {
        return this.http.post<{
            assignment: JudgeAssignment;
            credentials: { username: string; password: string } | null;
        }>(`${this.apiUrl}/${championshipId}/judge-assignments`, request);
    }

    reassign(
        championshipId: string,
        assignmentId: string,
        request: ReassignJudgeRequest
    ): Observable<{
        assignment: JudgeAssignment;
        credentials: { username: string; password: string } | null;
    }> {
        return this.http.post<{
            assignment: JudgeAssignment;
            credentials: { username: string; password: string } | null;
        }>(
            `${this.apiUrl}/${championshipId}/judge-assignments/${assignmentId}/reassign`,
            request
        );
    }

    removeAssignment(
        championshipId: string,
        assignmentId: string
    ): Observable<{
        removed: boolean;
        effective_from_category: {
            id: string;
            name: string;
            passing_order: number;
        } | null;
    }> {
        return this.http.delete<{
            removed: boolean;
            effective_from_category: {
                id: string;
                name: string;
                passing_order: number;
            } | null;
        }>(
            `${this.apiUrl}/${championshipId}/judge-assignments/${assignmentId}`
        );
    }
}
