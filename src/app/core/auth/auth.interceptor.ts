import {
    HttpErrorResponse,
    HttpInterceptorFn
} from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { environment } from '../../../environments/environment';
import { ApiErrorBody } from '../models/api-error.model';
import { AuthStateService } from './auth-state.service';

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const AUTHENTICATION_ENDPOINTS = [
    '/api/v1/auth/login',
    '/api/v1/auth/me'
];

function readCookie(name: string): string | null {
    const encodedName = `${encodeURIComponent(name)}=`;
    const cookie = document.cookie
        .split(';')
        .map((part) => part.trim())
        .find((part) => part.startsWith(encodedName));

    if (!cookie) {
        return null;
    }

    const rawValue = cookie.slice(encodedName.length);
    try {
        return decodeURIComponent(rawValue);
    } catch {
        return rawValue;
    }
}

function isAuthenticationEndpoint(url: string): boolean {
    return AUTHENTICATION_ENDPOINTS.some((path) => url.includes(path));
}

function isBackendRequest(url: string): boolean {
    if (environment.apiUrl) {
        return url.startsWith(environment.apiUrl);
    }
    return url.startsWith('/api/');
}

export const cloudAuthInterceptor: HttpInterceptorFn = (request, next) => {
    if (!isBackendRequest(request.url)) {
        return next(request);
    }

    const authState = inject(AuthStateService);
    const router = inject(Router);
    const csrfToken = MUTATING_METHODS.has(request.method)
        ? readCookie('ritmica_csrf')
        : null;

    const authenticatedRequest = request.clone({
        withCredentials: true,
        setHeaders: csrfToken
            ? { 'X-CSRF-TOKEN': csrfToken }
            : {}
    });

    return next(authenticatedRequest).pipe(
        catchError((error: HttpErrorResponse) => {
            const body = error.error as Partial<ApiErrorBody> | null;

            if (
                error.status === 401
                && !isAuthenticationEndpoint(request.url)
            ) {
                authState.clear();
                void router.navigate(['/ingresar'], {
                    queryParams: {
                        returnUrl: router.url,
                        sessionExpired: true
                    }
                });
            } else if (
                error.status === 403
                && body?.code === 'JUDGE_ACCESS_NOT_AVAILABLE'
            ) {
                authState.clear();
                void router.navigate(['/ingresar'], {
                    queryParams: { judgeAccessUnavailable: true }
                });
            } else if (
                error.status === 403
                && body?.code === 'FORBIDDEN'
            ) {
                void router.navigate(['/sin-permiso']);
            }

            return throwError(() => error);
        })
    );
};
