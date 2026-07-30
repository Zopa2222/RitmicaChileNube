import { AsyncPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import {
    MatSnackBar,
    MatSnackBarModule
} from '@angular/material/snack-bar';
import { MatToolbarModule } from '@angular/material/toolbar';
import {
    Router,
    RouterLink,
    RouterOutlet
} from '@angular/router';

import { AuthService } from './core/auth/auth.service';
import {
    accountTypeLabel,
    homeRouteForAccountType
} from './core/models/auth.model';

@Component({
    selector: 'app-root',
    standalone: true,
    imports: [
        AsyncPipe,
        MatButtonModule,
        MatIconModule,
        MatSnackBarModule,
        MatToolbarModule,
        RouterLink,
        RouterOutlet
    ],
    template: `
        @if (user$ | async; as user) {
            <mat-toolbar class="session-toolbar">
                <a
                    class="toolbar-brand brand-lockup"
                    [routerLink]="homeRoute(user.account_type)"
                    aria-label="Rítmica Chile, volver al inicio">
                    <img
                        src="assets/logo.jpeg"
                        alt=""
                        class="brand-lockup__logo">
                    <span class="brand-lockup__copy">
                        <strong class="brand-lockup__name">Rítmica Chile</strong>
                        <small class="brand-lockup__subtitle">
                            Sistema oficial de puntajes
                        </small>
                    </span>
                </a>
                <span class="toolbar-spacer"></span>
                <div class="identity">
                    <span class="identity-name">
                        {{ user.first_name }} {{ user.last_name }}
                    </span>
                    <span class="identity-role">
                        {{ roleLabel(user.account_type) }}
                    </span>
                </div>
                <button
                    mat-button
                    type="button"
                    (click)="logout()"
                    [disabled]="loggingOut">
                    <mat-icon>logout</mat-icon>
                    <span class="logout-label">
                        {{ loggingOut ? 'Saliendo…' : 'Cerrar sesión' }}
                    </span>
                </button>
            </mat-toolbar>
        }
        <router-outlet></router-outlet>
    `,
    styles: [`
        .session-toolbar {
            position: sticky;
            top: 0;
            z-index: 1000;
            min-height: 76px;
            padding: 0 clamp(1rem, 3vw, 2.5rem);
            background: rgba(255, 255, 255, 0.96);
            border-bottom: 1px solid #e2e8f0;
            box-shadow: 0 2px 10px rgba(15, 23, 42, 0.06);
        }
        .toolbar-brand {
            --brand-logo-size: 52px;
        }
        .toolbar-spacer { flex: 1; }
        .identity {
            display: grid;
            justify-items: end;
            margin-right: 0.75rem;
            line-height: 1.2;
        }
        .identity-name {
            color: #1e293b;
            font-size: 0.88rem;
            font-weight: 700;
        }
        .identity-role {
            color: #64748b;
            font-size: 0.72rem;
        }
        @media (max-width: 640px) {
            .session-toolbar {
                min-height: 68px;
                padding: 0 1rem;
            }
            .toolbar-brand {
                --brand-logo-size: 46px;
            }
            .toolbar-brand .brand-lockup__subtitle,
            .identity,
            .logout-label {
                display: none;
            }
        }
    `]
})
export class AppComponent {
    title = 'Gymnastics Scoring System';
    readonly user$ = this.authService.user$;
    readonly roleLabel = accountTypeLabel;
    readonly homeRoute = homeRouteForAccountType;
    loggingOut = false;

    constructor(
        private readonly authService: AuthService,
        private readonly router: Router,
        private readonly snackBar: MatSnackBar
    ) { }

    logout(): void {
        if (this.loggingOut) {
            return;
        }
        this.loggingOut = true;
        this.authService.logout().subscribe({
            next: () => {
                this.loggingOut = false;
                void this.router.navigate(['/']);
            },
            error: (error: HttpErrorResponse) => {
                this.loggingOut = false;
                if (error.status === 401) {
                    void this.router.navigate(['/']);
                    return;
                }
                this.snackBar.open(
                    'No fue posible cerrar la sesión. Revisa tu conexión.',
                    'Cerrar',
                    { duration: 5000 }
                );
            }
        });
    }
}
