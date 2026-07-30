import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component } from '@angular/core';
import {
    FormBuilder,
    ReactiveFormsModule,
    Validators
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import {
    ActivatedRoute,
    Router,
    RouterLink
} from '@angular/router';
import { finalize } from 'rxjs';

import { AuthService } from '../../core/auth/auth.service';
import { ApiErrorBody } from '../../core/models/api-error.model';
import {
    AuthenticatedUser,
    JudgeAccessWindow,
    homeRouteForAccountType
} from '../../core/models/auth.model';

@Component({
    selector: 'app-login',
    standalone: true,
    imports: [
        CommonModule,
        MatButtonModule,
        MatCardModule,
        MatFormFieldModule,
        MatIconModule,
        MatInputModule,
        MatProgressSpinnerModule,
        ReactiveFormsModule,
        RouterLink
    ],
    templateUrl: './login.component.html',
    styleUrls: ['./login.component.scss']
})
export class LoginComponent {
    readonly form = this.formBuilder.nonNullable.group({
        username: ['', [Validators.required]],
        password: ['', [Validators.required]]
    });

    loading = false;
    hidePassword = true;
    errorMessage = '';
    nextAccessWindow: JudgeAccessWindow | null = null;
    readonly sessionExpired: boolean;
    readonly accessWindowClosed: boolean;

    constructor(
        private readonly formBuilder: FormBuilder,
        private readonly authService: AuthService,
        private readonly route: ActivatedRoute,
        private readonly router: Router
    ) {
        this.sessionExpired =
            this.route.snapshot.queryParamMap.get('sessionExpired') === 'true';
        this.accessWindowClosed =
            this.route.snapshot.queryParamMap.get('accessWindowClosed') === 'true';
    }

    submit(): void {
        if (this.form.invalid || this.loading) {
            this.form.markAllAsTouched();
            return;
        }

        this.loading = true;
        this.errorMessage = '';
        this.nextAccessWindow = null;

        this.authService.login({
            username: this.form.controls.username.value.trim().toUpperCase(),
            password: this.form.controls.password.value
        }).pipe(
            finalize(() => {
                this.loading = false;
            })
        ).subscribe({
            next: (user) => {
                void this.router.navigateByUrl(this.destinationFor(user));
            },
            error: (error: HttpErrorResponse) => {
                const body = error.error as Partial<ApiErrorBody> | null;
                this.errorMessage = this.messageFor(body?.code);
                this.nextAccessWindow = body?.next_access_window ?? null;
            }
        });
    }

    private destinationFor(user: AuthenticatedUser): string {
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');
        if (
            returnUrl
            && returnUrl.startsWith('/')
            && !returnUrl.startsWith('//')
            && returnUrl !== '/ingresar'
        ) {
            return returnUrl;
        }
        return homeRouteForAccountType(user.account_type);
    }

    private messageFor(code?: string): string {
        switch (code) {
            case 'INVALID_CREDENTIALS':
                return 'El usuario o la contraseña no son correctos.';
            case 'ACCOUNT_DISABLED':
                return 'Esta cuenta se encuentra deshabilitada.';
            case 'ACCESS_WINDOW_CLOSED':
                return 'Tu cuenta de juez no tiene una ventana de acceso vigente.';
            default:
                return 'No fue posible iniciar sesión. Revisa tu conexión e inténtalo nuevamente.';
        }
    }
}
