import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import {
    Observable,
    catchError,
    firstValueFrom,
    map,
    of,
    tap
} from 'rxjs';

import { environment } from '../../../environments/environment';
import {
    AuthResponse,
    AuthenticatedUser,
    LoginCredentials
} from '../models/auth.model';
import { AuthStateService } from './auth-state.service';

@Injectable({ providedIn: 'root' })
export class AuthService {
    private readonly apiUrl = `${environment.apiUrl}/api/v1/auth`;

    readonly user$ = this.authState.user$;

    constructor(
        private readonly http: HttpClient,
        private readonly authState: AuthStateService
    ) { }

    get currentUser(): AuthenticatedUser | null {
        return this.authState.user;
    }

    async restoreSession(): Promise<void> {
        const response = await firstValueFrom(
            this.http.get<AuthResponse>(`${this.apiUrl}/me`).pipe(
                catchError((error: HttpErrorResponse) => {
                    if (error.status !== 401) {
                        console.error('No fue posible restaurar la sesión', error);
                    }
                    return of(null);
                })
            )
        );

        if (response) {
            this.authState.setUser(response.user);
        } else {
            this.authState.clear();
        }
    }

    login(credentials: LoginCredentials): Observable<AuthenticatedUser> {
        return this.http
            .post<AuthResponse>(`${this.apiUrl}/login`, credentials)
            .pipe(
                tap((response) => this.authState.setUser(response.user)),
                map((response) => response.user)
            );
    }

    logout(): Observable<void> {
        return this.http.post<void>(`${this.apiUrl}/logout`, {}).pipe(
            tap(() => this.authState.clear())
        );
    }
}
