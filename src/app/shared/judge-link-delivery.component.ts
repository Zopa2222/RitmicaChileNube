import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { CredentialDeliveryService } from '../core/services/credential-delivery.service';

@Component({
    selector: 'app-judge-link-delivery',
    standalone: true,
    imports: [CommonModule, MatButtonModule],
    template: `
        <section *ngIf="delivery.entries$ | async as entries">
            <ng-container *ngIf="entries.length">
                <h3>Enlaces de acceso para entregar</h3>
                <p>Cada juez abre su enlace desde el celular, sin usuario ni contraseña.
                    Funciona durante sus días y turnos asignados. Compártelo sólo con esa persona.</p>
                <p>Copia los enlaces antes de recargar o cerrar sesión. Se muestran sólo en esta sesión.</p>
                <article *ngFor="let entry of entries">
                    <label><strong>{{ entry.firstName }} {{ entry.lastName }}</strong>
                        <input readonly [value]="entry.accessUrl" #link
                            (click)="link.select()" aria-label="Enlace personal de acceso">
                    </label>
                    <button mat-stroked-button type="button" (click)="copy(entry.accessUrl, link)">Copiar enlace</button>
                </article>
                <p role="status" aria-live="polite">{{ message }}</p>
            </ng-container>
        </section>
    `,
    styles: [`
        section:has(article) { padding: 16px; margin: 16px 0; background: #ecfdf5;
            border: 1px solid #a7f3d0; border-radius: 12px; color: #1e293b; }
        h3 { margin-top: 0; } p { line-height: 1.5; }
        article { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin: 16px 0; }
        label { flex: 1; min-width: 0; display: grid; gap: 8px; }
        input { width: 100%; box-sizing: border-box; min-height: 44px; padding: 10px;
            border: 1px solid #94a3b8; border-radius: 6px; font-size: 16px; }
        button { min-height: 44px; }
    `]
})
export class JudgeLinkDeliveryComponent {
    message = '';
    constructor(readonly delivery: CredentialDeliveryService) {}

    async copy(url: string, input: HTMLInputElement): Promise<void> {
        try {
            await navigator.clipboard.writeText(url);
            this.message = 'Enlace copiado. Puedes enviarlo al juez.';
        } catch {
            input.focus();
            input.select();
            this.message = 'Seleccionamos el enlace. Usa Copiar en tu dispositivo.';
        }
    }
}
