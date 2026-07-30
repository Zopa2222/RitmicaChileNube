import { Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, RouterLink } from '@angular/router';

@Component({
    selector: 'app-access-denied',
    standalone: true,
    imports: [MatButtonModule, MatIconModule, RouterLink],
    template: `
        <main class="denied">
            <mat-icon>lock</mat-icon>
            <h1>Acceso restringido</h1>
            <p>
                Tu cuenta está activa, pero no tiene permisos para abrir esta
                sección.
            </p>
            <a mat-flat-button color="primary" [routerLink]="home">
                Volver a mi inicio
            </a>
        </main>
    `,
    styles: [`
        .denied {
            min-height: calc(100vh - 64px);
            padding: 2rem;
            display: grid;
            place-content: center;
            justify-items: center;
            gap: 1rem;
            text-align: center;
            background: #f8fafc;
        }
        .denied > mat-icon {
            width: 72px;
            height: 72px;
            font-size: 72px;
            color: #dc2626;
        }
        h1 { margin: 0; color: #1e293b; }
        p { max-width: 480px; color: #64748b; line-height: 1.6; }
    `]
})
export class AccessDeniedComponent {
    readonly home =
        this.route.snapshot.queryParamMap.get('home') || '/';

    constructor(private readonly route: ActivatedRoute) { }
}
