import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class CloudExportApiService {
    private readonly apiUrl = `${environment.apiUrl}/api/v1/championships`;

    constructor(private readonly http: HttpClient) { }

    download(championshipId: string, format: 'excel' | 'pdf'): Observable<Blob> {
        return this.http.get(
            `${this.apiUrl}/${championshipId}/exports/${format}`,
            { responseType: 'blob' }
        );
    }
}
