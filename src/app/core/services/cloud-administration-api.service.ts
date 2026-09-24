import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
    AuditLogEntry,
    CloudChampionship,
    CloudJudge,
    InitialCredentials
} from '../models/cloud.model';

@Injectable({ providedIn: 'root' })
export class CloudAdministrationApiService {
    private readonly apiUrl = `${environment.apiUrl}/api/v1`;

    constructor(private readonly http: HttpClient) { }

    judges(query = ''): Observable<CloudJudge[]> {
        return this.http.get<{ judges: CloudJudge[] }>(
            `${this.apiUrl}/admin/judges`, { params: { query } }
        ).pipe(map((response) => response.judges));
    }

    createJudge(request: {
        first_name: string; last_name: string; rut: string;
    }): Observable<{
        judge: CloudJudge;
        credentials: InitialCredentials;
    }> {
        return this.http.post<{
            judge: CloudJudge;
            credentials: InitialCredentials;
        }>(`${this.apiUrl}/admin/judges`, request);
    }

    updateJudge(
        judgeId: string,
        request: Partial<Pick<CloudJudge, 'first_name' | 'last_name' | 'status'>> & { rut?: string }
    ): Observable<CloudJudge> {
        return this.http.patch<{ judge: CloudJudge }>(
            `${this.apiUrl}/admin/judges/${judgeId}`, request
        ).pipe(map((response) => response.judge));
    }

    deleteJudge(judgeId: string): Observable<void> {
        return this.http.delete<void>(
            `${this.apiUrl}/admin/judges/${judgeId}`
        );
    }

    deactivateJudge(judgeId: string): Observable<CloudJudge> {
        return this.http.post<{ judge: CloudJudge }>(
            `${this.apiUrl}/admin/judges/${judgeId}/deactivate`, {}
        ).pipe(map((response) => response.judge));
    }

    activateJudge(judgeId: string): Observable<CloudJudge> {
        return this.http.post<{ judge: CloudJudge }>(
            `${this.apiUrl}/admin/judges/${judgeId}/activate`, {}
        ).pipe(map((response) => response.judge));
    }

    regenerateCredentials(judgeId: string): Observable<{
        judge: CloudJudge;
        credentials: InitialCredentials;
    }> {
        return this.http.post<{
            judge: CloudJudge;
            credentials: InitialCredentials;
        }>(`${this.apiUrl}/admin/judges/${judgeId}/access-link`, {});
    }

    regenerateCredentialsBatch(judgeIds: string[]): Observable<Array<{
        judge: CloudJudge;
        credentials: InitialCredentials;
    }>> {
        return this.http.post<{
            items: Array<{ judge: CloudJudge; credentials: InitialCredentials }>;
        }>(`${this.apiUrl}/admin/judges/access-links`, {
            judge_ids: judgeIds
        }).pipe(map((response) => response.items));
    }

    recoverGlobalAdministrator(newPassword: string): Observable<void> {
        return this.http.post<void>(`${this.apiUrl}/admin/global-admin/recovery`, {
            new_password: newPassword
        });
    }

    auditLogs(championshipId?: string): Observable<AuditLogEntry[]> {
        const params = championshipId ? { championship_id: championshipId } : {};
        return this.http.get<{ logs: AuditLogEntry[] }>(
            `${this.apiUrl}/admin/audit-logs`, { params }
        ).pipe(map((response) => response.logs));
    }

    confirmDeletion(championshipId: string, step: 1 | 2 | 3): Observable<CloudChampionship> {
        return this.http.post<{ championship: CloudChampionship }>(
            `${this.apiUrl}/championships/${championshipId}/deletion-confirmations`, { step }
        ).pipe(map((response) => response.championship));
    }

    recoverChampionship(championshipId: string): Observable<CloudChampionship> {
        return this.http.post<{ championship: CloudChampionship }>(
            `${this.apiUrl}/championships/${championshipId}/recover`, {}
        ).pipe(map((response) => response.championship));
    }
}
