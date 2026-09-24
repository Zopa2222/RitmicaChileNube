import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CredentialDeliveryService } from '../core/services/credential-delivery.service';

@Component({
    selector: 'app-judge-link-delivery',
    standalone: true,
    imports: [CommonModule, MatButtonModule, MatIconModule],
    template: `
        <section *ngIf="delivery.entries$ | async as entries">
            <ng-container *ngIf="entries.length">
                <header>
                    <h3>Enlaces de acceso para entregar ({{ entries.length }})</h3>
                    <div class="actions">
                        <button mat-stroked-button type="button" (click)="delivery.exportCredentials(entries)">Exportar enlaces a Excel</button>
                        <button *ngIf="collapsed" mat-button type="button" (click)="collapsed = false" aria-expanded="false">Mostrar enlaces</button>
                        <button *ngIf="!collapsed" mat-icon-button type="button" (click)="collapsed = true" aria-label="Cerrar listado de enlaces" title="Cerrar listado de enlaces" aria-expanded="true"><mat-icon>close</mat-icon></button>
                    </div>
                </header>
                <ng-container *ngIf="!collapsed">
                <p>Cada juez abre su enlace desde el celular, sin usuario ni contraseña.
                    Funciona durante sus días y turnos asignados. Compártelo sólo con esa persona.</p>
                <p>Copia los enlaces antes de recargar o cerrar sesión. Se muestran sólo en esta sesión.</p>
                <div class="entries" tabindex="0" role="region" aria-label="Listado de enlaces de jueces">
                <article *ngFor="let entry of entries">
                    <label><strong>{{ entry.firstName }} {{ entry.lastName }}</strong>
                        <input readonly [value]="entry.accessUrl" #link
                            (click)="link.select()" aria-label="Enlace personal de acceso">
                    </label>
                    <button mat-stroked-button type="button" (click)="copy(entry.accessUrl, link)">Copiar enlace</button>
                </article>
                </div>
                <p role="status" aria-live="polite">{{ message }}</p>
                </ng-container>
            </ng-container>
        </section>
    `,
    styles: [`
        section:has(header) { padding: 16px; margin: 16px 0; background: #ecfdf5;
            border: 1px solid #a7f3d0; border-radius: 12px; color: #1e293b; }
        h3 { margin-top: 0; } p { line-height: 1.5; }
        header, .actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
        header { justify-content: space-between; } header h3 { margin: 0; }
        .entries { max-height: min(45vh, 420px); overflow-y: auto; padding: 0 4px; }
        article { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin: 16px 0; }
        label { flex: 1; min-width: 0; display: grid; gap: 8px; }
        input { width: 100%; box-sizing: border-box; min-height: 44px; padding: 10px;
            border: 1px solid #94a3b8; border-radius: 6px; font-size: 16px; }
        button { min-height: 44px; }
    `]
})
export class JudgeLinkDeliveryComponent {
    message = '';
    collapsed = false;
    constructor(readonly delivery: CredentialDeliveryService) {
        delivery.entries$.pipe(takeUntilDestroyed()).subscribe(() => {
            this.collapsed = false;
            this.message = '';
        });
    }

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
