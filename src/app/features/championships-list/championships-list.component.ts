import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
    Component,
    OnInit
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import {
    MatSnackBar,
    MatSnackBarModule
} from '@angular/material/snack-bar';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import Swal from 'sweetalert2';

import { ApiErrorBody } from '../../core/models/api-error.model';
import {
    ChampionshipStatus,
    CloudChampionship
} from '../../core/models/cloud.model';
import {
    CloudChampionshipApiService
} from '../../core/services/cloud-championship-api.service';

@Component({
    selector: 'app-championships-list',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        MatButtonModule,
        MatCardModule,
        MatChipsModule,
        MatFormFieldModule,
        MatIconModule,
        MatInputModule,
        MatProgressSpinnerModule,
        MatSnackBarModule,
        RouterLink
    ],
    templateUrl: './championships-list.component.html',
    styleUrls: ['./championships-list.component.scss']
})
export class ChampionshipsListComponent implements OnInit {
    championships: CloudChampionship[] = [];
    filteredChampionships: CloudChampionship[] = [];
    searchTerm = '';
    loading = true;
    loadError = '';
    actionId: string | null = null;

    constructor(
        private readonly championshipsApi: CloudChampionshipApiService,
        private readonly snackBar: MatSnackBar
    ) { }

    ngOnInit(): void {
        this.loadChampionships();
    }

    loadChampionships(): void {
        this.loading = true;
        this.loadError = '';
        this.championshipsApi.list().subscribe({
            next: (championships) => {
                this.championships = championships;
                this.filterChampionships();
                this.loading = false;
            },
            error: () => {
                this.loadError =
                    'No fue posible cargar los campeonatos desde la nube.';
                this.loading = false;
            }
        });
    }

    filterChampionships(): void {
        const term = this.searchTerm.trim().toLocaleLowerCase('es-CL');
        this.filteredChampionships = !term
            ? [...this.championships]
            : this.championships.filter((championship) =>
                [
                    championship.name,
                    championship.kind,
                    championship.zone,
                    this.statusLabel(championship.status)
                ].some((value) =>
                    value.toLocaleLowerCase('es-CL').includes(term)
                )
            );
    }

    get activeChampionship(): CloudChampionship | null {
        return this.championships.find(
            (championship) => championship.status === 'ACTIVE'
        ) ?? null;
    }

    async activate(championship: CloudChampionship): Promise<void> {
        if (this.actionId || championship.status === 'ACTIVE') {
            return;
        }

        const currentActive = this.activeChampionship;
        if (currentActive && currentActive.id !== championship.id) {
            const confirmation = await Swal.fire({
                title: '¿Cambiar el campeonato activo?',
                html:
                    `Se pausará <strong>${this.escapeHtml(currentActive.name)}</strong> `
                    + `antes de activar <strong>${this.escapeHtml(championship.name)}</strong>.`,
                icon: 'warning',
                showCancelButton: true,
                confirmButtonText: 'Pausar y activar',
                cancelButtonText: 'Cancelar',
                confirmButtonColor: '#4f46e5'
            });
            if (!confirmation.isConfirmed) {
                return;
            }
        } else {
            const confirmation = await Swal.fire({
                title: championship.status === 'PAUSED'
                    ? '¿Reanudar campeonato?'
                    : '¿Activar campeonato?',
                text:
                    'Al activarlo será el único campeonato visible para el público.',
                icon: 'question',
                showCancelButton: true,
                confirmButtonText: championship.status === 'PAUSED'
                    ? 'Reanudar'
                    : 'Activar',
                cancelButtonText: 'Cancelar',
                confirmButtonColor: '#4f46e5'
            });
            if (!confirmation.isConfirmed) {
                return;
            }
        }

        this.actionId = championship.id;
        let previousWasPaused = false;
        try {
            const target = await firstValueFrom(
                this.championshipsApi.get(championship.id)
            );
            if (target.counts.categories === 0) {
                throw new Error('CHAMPIONSHIP_NOT_IMPORTED');
            }
            if (currentActive && currentActive.id !== championship.id) {
                const paused = await firstValueFrom(
                    this.championshipsApi.pause(currentActive.id)
                );
                this.replaceChampionship(paused);
                previousWasPaused = true;
            }
            const activated = await firstValueFrom(
                this.championshipsApi.activate(championship.id)
            );
            this.replaceChampionship(activated);
            this.snackBar.open(
                `${activated.name} quedó activo`,
                'Cerrar',
                { duration: 3500 }
            );
        } catch (error) {
            if (
                previousWasPaused
                && currentActive
                && currentActive.id !== championship.id
            ) {
                try {
                    const restored = await firstValueFrom(
                        this.championshipsApi.activate(currentActive.id)
                    );
                    this.replaceChampionship(restored);
                } catch {
                    // Reload below exposes the authoritative state if recovery fails.
                }
            }
            this.showApiError(
                error,
                error instanceof Error
                    && error.message === 'CHAMPIONSHIP_NOT_IMPORTED'
                    ? 'Primero carga y confirma el orden de paso.'
                    : 'No fue posible activar el campeonato.'
            );
            this.loadChampionships();
        } finally {
            this.actionId = null;
        }
    }

    async pause(championship: CloudChampionship): Promise<void> {
        if (this.actionId || championship.status !== 'ACTIVE') {
            return;
        }
        const confirmation = await Swal.fire({
            title: '¿Pausar campeonato?',
            text:
                'Los jueces dejarán de registrar notas hasta que se reanude.',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Pausar',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#d97706'
        });
        if (!confirmation.isConfirmed) {
            return;
        }

        this.actionId = championship.id;
        try {
            const paused = await firstValueFrom(
                this.championshipsApi.pause(championship.id)
            );
            this.replaceChampionship(paused);
            this.snackBar.open('Campeonato pausado', 'Cerrar', {
                duration: 3000
            });
        } catch (error) {
            this.showApiError(error, 'No fue posible pausar el campeonato.');
        } finally {
            this.actionId = null;
        }
    }

    async close(championship: CloudChampionship): Promise<void> {
        if (this.actionId || championship.status === 'CLOSED') {
            return;
        }
        const confirmation = await Swal.fire({
            title: 'Cerrar campeonato',
            html:
                'El campeonato dejará de estar operativo y ya no podrá '
                + 'reactivarse.<br><strong>Esta acción no es una pausa.</strong>',
            icon: 'warning',
            input: 'checkbox',
            inputPlaceholder: 'Entiendo que el cierre es definitivo',
            inputValidator: (checked) =>
                checked ? undefined : 'Debes confirmar que comprendes el cierre',
            showCancelButton: true,
            confirmButtonText: 'Cerrar campeonato',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#dc2626'
        });
        if (!confirmation.isConfirmed) {
            return;
        }

        this.actionId = championship.id;
        try {
            const closed = await firstValueFrom(
                this.championshipsApi.close(championship.id)
            );
            this.replaceChampionship(closed);
            this.snackBar.open('Campeonato cerrado', 'Cerrar', {
                duration: 3500
            });
        } catch (error) {
            this.showApiError(error, 'No fue posible cerrar el campeonato.');
        } finally {
            this.actionId = null;
        }
    }

    statusLabel(status: ChampionshipStatus): string {
        const labels: Record<ChampionshipStatus, string> = {
            DRAFT: 'Borrador',
            ACTIVE: 'Activo',
            PAUSED: 'Pausado',
            CLOSED: 'Cerrado',
            PENDING_DELETION: 'Pendiente de eliminación',
            DELETED: 'Eliminado'
        };
        return labels[status];
    }

    private replaceChampionship(updated: CloudChampionship): void {
        this.championships = this.championships.map((championship) =>
            championship.id === updated.id ? updated : championship
        );
        this.filterChampionships();
    }

    private showApiError(error: unknown, fallback: string): void {
        const body = error instanceof HttpErrorResponse
            ? error.error as Partial<ApiErrorBody>
            : null;
        this.snackBar.open(body?.error || fallback, 'Cerrar', {
            duration: 6000
        });
    }

    private escapeHtml(value: string): string {
        const element = document.createElement('div');
        element.textContent = value;
        return element.innerHTML;
    }
}
