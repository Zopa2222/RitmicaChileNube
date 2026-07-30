import {
    HttpClient,
    HttpParams
} from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
    CloudJudge,
    CreateJudgeAssignmentRequest,
    InitialCredentials,
    JudgeAssignment,
    JudgeIdentityInput,
    ReassignJudgeRequest
} from '../models/cloud.model';

export interface JudgeAssignmentResult {
    assignment: JudgeAssignment;
    credentials: InitialCredentials | null;
}

@Injectable({ providedIn: 'root' })
export class CloudJudgeApiService {
    private readonly apiUrl = `${environment.apiUrl}/api/v1`;

    constructor(private readonly http: HttpClient) { }

    search(query = ''): Observable<CloudJudge[]> {
        const params = query.trim()
            ? new HttpParams().set('query', query.trim())
            : undefined;
        return this.http
            .get<{ judges: CloudJudge[] }>(`${this.apiUrl}/judges`, { params })
            .pipe(map((response) => response.judges));
    }

    create(
        judge: JudgeIdentityInput
    ): Observable<{
        judge: CloudJudge;
        credentials: InitialCredentials;
    }> {
        return this.http.post<{
            judge: CloudJudge;
            credentials: InitialCredentials;
        }>(`${this.apiUrl}/judges`, judge);
    }

    listAssignments(
        championshipId: string,
        includeHistory = false
    ): Observable<JudgeAssignment[]> {
        const params = includeHistory
            ? new HttpParams().set('include_history', 'true')
            : undefined;
        return this.http
            .get<{ assignments: JudgeAssignment[] }>(
                `${this.apiUrl}/championships/${championshipId}/judge-assignments`,
                { params }
            )
            .pipe(map((response) => response.assignments));
    }

    assign(
        championshipId: string,
        request: CreateJudgeAssignmentRequest
    ): Observable<JudgeAssignmentResult> {
        return this.http.post<JudgeAssignmentResult>(
            `${this.apiUrl}/championships/${championshipId}/judge-assignments`,
            request
        );
    }

    reassign(
        championshipId: string,
        assignmentId: string,
        request: ReassignJudgeRequest
    ): Observable<JudgeAssignmentResult> {
        return this.http.post<JudgeAssignmentResult>(
            `${this.apiUrl}/championships/${championshipId}`
            + `/judge-assignments/${assignmentId}/reassign`,
            request
        );
    }
}
