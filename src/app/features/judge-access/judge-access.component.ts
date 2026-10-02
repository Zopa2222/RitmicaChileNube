import { CommonModule, Location } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { Subscription } from 'rxjs';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { AuthService } from '../../core/auth/auth.service';

@Component({
    selector: 'app-judge-access',
    standalone: true,
    imports: [CommonModule, RouterLink, MatButtonModule, MatProgressSpinnerModule],
    template: `
        <main>
            <img src="assets/logo.jpeg" alt="Rítmica Chile">
            <h1>Acceso de jueces</h1>
            <mat-spinner *ngIf="loading" diameter="40" aria-label="Ingresando"></mat-spinner>
            <p role="status" aria-live="polite">{{ message }}</p>
            <button *ngIf="token && !loading" mat-flat-button color="primary"
                type="button" (click)="enter()">Volver a intentar</button>
            <a mat-button routerLink="/">Ver resultados públicos</a>
        </main>
    `,
    styles: [`
        main { max-width: 440px; margin: 8vh auto; padding: 24px;
            text-align: center; color: #1e293b; }
        img { width: 100px; border-radius: 12px; }
        p { font-size: 1.1rem; line-height: 1.6; }
        mat-spinner { margin: 24px auto; }
        button, a { display: block; width: 100%; margin-top: 16px; min-height: 48px; }
    `]
})
export class JudgeAccessComponent implements OnInit, OnDestroy {
    loading = false;
    token = '';
    private fragmentSubscription?: Subscription;
    private accessSubscription?: Subscription;
    message = 'Abre el enlace personal que te entregó la organización. No necesitas usuario ni contraseña.';

    constructor(
        private readonly route: ActivatedRoute,
        private readonly router: Router,
        private readonly location: Location,
        private readonly auth: AuthService
    ) {}

    ngOnInit(): void {
        if (!this.route.snapshot.fragment && this.auth.currentUser?.account_type === 'JUDGE') {
            void this.router.navigateByUrl('/cabina-juez', { replaceUrl: true });
        }
        this.fragmentSubscription = this.route.fragment.subscribe((fragment) => {
            if (!fragment) return;
            this.accessSubscription?.unsubscribe();
            this.loading = false;
            this.token = fragment;
            // Remove the secret immediately and synchronize Router state so
            // reopening the same link on this page is processed again.
            this.location.replaceState('/acceso-juez');
            void this.router.navigateByUrl('/acceso-juez', { replaceUrl: true });
            this.enter();
        });
    }

    ngOnDestroy(): void {
        this.fragmentSubscription?.unsubscribe();
        this.accessSubscription?.unsubscribe();
        this.token = '';
    }

    enter(): void {
        if (this.loading || !this.token) return;
        this.loading = true;
        this.message = 'Abriendo tu cabina…';
        this.accessSubscription = this.auth.accessJudgeLink(this.token).subscribe({
            next: () => {
                this.token = '';
                void this.router.navigateByUrl('/cabina-juez', { replaceUrl: true });
            },
            error: (error: HttpErrorResponse) => {
                this.loading = false;
                switch (error.error?.code) {
                    case 'JUDGE_ACCESS_NOT_AVAILABLE':
                        this.message = 'Tu turno aún no está disponible o ya terminó. Puedes volver a abrir el mismo enlace durante tus días y horarios asignados. Si corresponde, consulta a la organización.';
                        break;
                    case 'ACCOUNT_DISABLED':
                        this.message = 'Tu acceso está desactivado. Consulta a la organización.';
                        this.token = '';
                        break;
                    case 'INVALID_JUDGE_LINK':
                        this.message = 'Este enlace no es válido o fue reemplazado. Solicita un nuevo enlace a la organización.';
                        this.token = '';
                        break;
                    case 'RATE_LIMIT_EXCEEDED':
                        this.message = 'Hubo demasiados intentos. Espera un momento antes de volver a intentar.';
                        break;
                    default:
                        this.message = 'No pudimos abrir tu cabina. Revisa tu conexión y vuelve a intentar.';
                }
            }
        });
    }
}
