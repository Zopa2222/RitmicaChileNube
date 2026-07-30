import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
    JudgeContext,
    ScoreEntry
} from '../models/cloud.model';

@Injectable({ providedIn: 'root' })
export class JudgeCabinApiService {
    private readonly apiUrl = `${environment.apiUrl}/api/v1/judge`;

    constructor(private readonly http: HttpClient) { }

    getContexts(): Observable<{
        contexts: JudgeContext[];
        serverTime: string;
    }> {
        return this.http.get<{
            contexts: JudgeContext[];
            server_time: string;
        }>(`${this.apiUrl}/contexts`).pipe(
            map((response) => ({
                contexts: response.contexts,
                serverTime: response.server_time
            }))
        );
    }

    updateScore(
        scoreEntryId: string,
        activationId: string,
        value: string | number
    ): Observable<{
        score: ScoreEntry;
        changed: boolean;
        server_time: string;
    }> {
        return this.http.put<{
            score: ScoreEntry;
            changed: boolean;
            server_time: string;
        }>(
            `${this.apiUrl}/scores/${scoreEntryId}`,
            {
                activation_id: activationId,
                value
            }
        );
    }
}
