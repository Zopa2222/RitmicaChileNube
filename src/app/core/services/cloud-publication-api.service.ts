import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
    CategoryPublication,
    PublishedResult
} from '../models/cloud.model';

@Injectable({ providedIn: 'root' })
export class CloudPublicationApiService {
    private readonly apiUrl = `${environment.apiUrl}/api/v1/championships`;

    constructor(private readonly http: HttpClient) { }

    publishCategory(
        championshipId: string,
        categoryId: string
    ): Observable<{
        publication: CategoryPublication;
        results: PublishedResult[];
    }> {
        return this.http.post<{
            publication: CategoryPublication;
            results: PublishedResult[];
        }>(
            `${this.apiUrl}/${championshipId}/categories/${categoryId}/publish`,
            {}
        );
    }
}
