import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
    CloudChampionship,
    CloudChampionshipDetail,
    CompetitionDay,
    CreateChampionshipRequest,
    ImportCutoffDecision,
    ImportPreview
} from '../models/cloud.model';

@Injectable({ providedIn: 'root' })
export class CloudChampionshipApiService {
    private readonly apiUrl = `${environment.apiUrl}/api/v1/championships`;

    constructor(private readonly http: HttpClient) { }

    list(): Observable<CloudChampionship[]> {
        return this.http
            .get<{ championships: CloudChampionship[] }>(this.apiUrl)
            .pipe(map((response) => response.championships));
    }

    get(championshipId: string): Observable<CloudChampionshipDetail> {
        return this.http
            .get<{ championship: CloudChampionshipDetail }>(
                `${this.apiUrl}/${championshipId}`
            )
            .pipe(map((response) => response.championship));
    }

    create(
        request: CreateChampionshipRequest
    ): Observable<CloudChampionship> {
        return this.http
            .post<{ championship: CloudChampionship }>(this.apiUrl, request)
            .pipe(map((response) => response.championship));
    }

    validateDayFile(file: File): Observable<{ valid: boolean }> {
        const data = new FormData();
        data.append('file', file);
        return this.http.post<{ valid: boolean }>(`${this.apiUrl}/validate-day-file`, data);
    }

    createImportPreview(
        championshipId: string,
        file: File,
        competitionDate?: string
    ): Observable<ImportPreview> {
        const formData = new FormData();
        formData.append('file', file);
        if (competitionDate) formData.append('competition_date', competitionDate);
        return this.http.post<ImportPreview>(
            `${this.apiUrl}/${championshipId}/import-previews`,
            formData
        );
    }

    getImportPreview(
        championshipId: string,
        previewId: string
    ): Observable<ImportPreview> {
        return this.http.get<ImportPreview>(
            `${this.apiUrl}/${championshipId}/import-previews/${previewId}`
        );
    }

    updateImportPreview(
        championshipId: string,
        previewId: string,
        request: {
            accept_detected?: boolean;
            sheets?: ImportCutoffDecision[];
        }
    ): Observable<ImportPreview> {
        return this.http.patch<ImportPreview>(
            `${this.apiUrl}/${championshipId}/import-previews/${previewId}`,
            request
        );
    }

    confirmImport(
        championshipId: string,
        previewId: string
    ): Observable<{
        championship: CloudChampionship;
        imported: {
            days: number;
            categories: number;
            gymnasts: number;
            new_judge_credentials?: Array<{ judge: string; username: string; access_path: string }>;
        };
    }> {
        return this.http.post<{
            championship: CloudChampionship;
            imported: {
            days: number;
            categories: number;
            gymnasts: number;
            new_judge_credentials?: Array<{ judge: string; username: string; access_path: string }>;
            };
        }>(
            `${this.apiUrl}/${championshipId}/import-previews/${previewId}/confirm`,
            {}
        );
    }

    addCompetitionDay(
        championshipId: string,
        file: File,
        competitionDate: string
    ): Observable<ImportPreview> {
        return this.createImportPreview(championshipId, file, competitionDate);
    }

    listCompetitionDays(championshipId: string): Observable<CompetitionDay[]> {
        return this.http
            .get<{ competition_days: CompetitionDay[] }>(
                `${this.apiUrl}/${championshipId}/competition-days`
            )
            .pipe(map((response) => response.competition_days));
    }

    activate(championshipId: string): Observable<CloudChampionship> {
        return this.lifecycleAction(championshipId, 'activate');
    }

    pause(championshipId: string): Observable<CloudChampionship> {
        return this.lifecycleAction(championshipId, 'pause');
    }

    close(championshipId: string): Observable<CloudChampionship> {
        return this.lifecycleAction(championshipId, 'close');
    }

    private lifecycleAction(
        championshipId: string,
        action: 'activate' | 'pause' | 'close'
    ): Observable<CloudChampionship> {
        return this.http
            .post<{ championship: CloudChampionship; changed: boolean }>(
                `${this.apiUrl}/${championshipId}/${action}`,
                {}
            )
            .pipe(map((response) => response.championship));
    }
}
