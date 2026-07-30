import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
    PublicCatalogResponse,
    PublicCategoryResultsResponse,
    PublicSortMode
} from '../models/public-results.model';

@Injectable({
    providedIn: 'root'
})
export class PublicResultsService {
    private readonly publicApiUrl =
        `${environment.apiUrl}/api/v1/public/championships/active`;

    constructor(private readonly http: HttpClient) { }

    getActiveChampionship(query = ''): Observable<PublicCatalogResponse> {
        let params = new HttpParams();
        if (query.trim()) {
            params = params.set('query', query.trim());
        }
        return this.http.get<PublicCatalogResponse>(
            this.publicApiUrl,
            { params }
        );
    }

    getCategoryResults(
        categoryId: string,
        sort: PublicSortMode,
        query = ''
    ): Observable<PublicCategoryResultsResponse> {
        let params = new HttpParams().set('sort', sort);
        if (query.trim()) {
            params = params.set('query', query.trim());
        }
        return this.http.get<PublicCategoryResultsResponse>(
            `${this.publicApiUrl}/categories/${categoryId}/results`,
            { params }
        );
    }
}
