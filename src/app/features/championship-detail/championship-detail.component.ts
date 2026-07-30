import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
    Component,
    OnInit
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import {
    MatSnackBar,
    MatSnackBarModule
} from '@angular/material/snack-bar';
import {
    ActivatedRoute,
    Router,
    RouterLink
} from '@angular/router';
import { firstValueFrom } from 'rxjs';
import Swal from 'sweetalert2';

import { ApiErrorBody } from '../../core/models/api-error.model';
import {
    ChampionshipStatus,
    CloudChampionship,
    CloudChampionshipDetail,
    CompetitionDay
} from '../../core/models/cloud.model';
import {
    CloudChampionshipApiService
} from '../../core/services/cloud-championship-api.service';
import { CloudAdministrationApiService } from '../../core/services/cloud-administration-api.service';

@Component({
    selector: 'app-championship-detail',
    standalone: true,
    imports: [
        CommonModule,
        MatButtonModule,
        MatCardModule,
        MatIconModule,
        MatProgressSpinnerModule,
        MatSnackBarModule,
        RouterLink
    ],
    templateUrl: './championship-detail.component.html',
    styleUrls: ['./championship-detail.component.scss']
})
export class ChampionshipDetailComponent implements OnInit {
    championship: CloudChampionshipDetail | null = null;
    competitionDays: CompetitionDay[] = [];
    loading = true;
    processing = false;
    errorMessage = '';

    private readonly championshipId =
        this.route.snapshot.paramMap.get('championshipId') ?? '';

    constructor(
        private readonly route: ActivatedRoute,
        private readonly router: Router,
        private readonly championshipsApi: CloudChampionshipApiService,
        private readonly administrationApi: CloudAdministrationApiService,
        private readonly snackBar: MatSnackBar
    ) { }

    ngOnInit(): void {
        this.load();
    }

    load(): void {
        if (!this.championshipId) {
            this.errorMessage = 'El identificador del campeonato no es válido.';
            this.loading = false;
            return;
        }

        this.loading = true;
        this.errorMessage = '';
        this.championshipsApi.get(this.championshipId).subscribe({
            next: (championship) => {
                this.championship = championship;
                this.loading = false;
                if (championship.counts.days > 0) {
                    this.loadCompetitionDays();
                }
            },
            error: (error) => {
                this.errorMessage = this.apiMessage(
                    error,
                    'No fue posible cargar el campeonato.'
                );
                this.loading = false;
            }
        });
    }

    async activate(): Promise<void> {
        if (!this.championship || this.processing) {
            return;
        }
        const confirmation = await Swal.fire({
            title: this.championship.status === 'PAUSED'
                ? '¿Reanudar campeonato?'
                : '¿Activar campeonato?',
            text:
                'Será el único campeonato visible públicamente. '
                + 'Si existe otro activo, primero debes pausarlo.',
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: this.championship.status === 'PAUSED'
                ? 'Reanudar'
                : 'Activar',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#4f46e5'
        });
        if (!confirmation.isConfirmed) {
            return;
        }
        await this.runLifecycle('activate');
    }

    async pause(): Promise<void> {
        if (!this.championship || this.processing) {
            return;
        }
        const confirmation = await Swal.fire({
            title: '¿Pausar campeonato?',
            text: 'La operación de jueces se detendrá hasta reanudarlo.',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Pausar',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#d97706'
        });
        if (confirmation.isConfirmed) {
            await this.runLifecycle('pause');
        }
    }

    async close(): Promise<void> {
        if (!this.championship || this.processing) {
            return;
        }
        const confirmation = await Swal.fire({
            title: 'Cerrar campeonato',
            html:
                'Dejará de estar operativo y no podrá reactivarse.<br>'
                + '<strong>Usa “Pausar” si la interrupción es temporal.</strong>',
            icon: 'warning',
            input: 'checkbox',
            inputPlaceholder: 'Comprendo que el cierre es definitivo',
            inputValidator: (checked) =>
                checked ? undefined : 'Debes confirmar el cierre definitivo',
            showCancelButton: true,
            confirmButtonText: 'Cerrar campeonato',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#dc2626'
        });
        if (confirmation.isConfirmed) {
            await this.runLifecycle('close');
        }
    }

    async requestDeletion(): Promise<void> {
        if (!this.championship || this.processing) return;
        const messages = [
            'Esta acción ocultará el campeonato y comenzará un período de recuperación de 14 días.',
            'Las planillas, resultados y archivos quedarán pendientes de eliminación definitiva.',
            'Confirmo solicitar la eliminación recuperable del campeonato.'
        ];
        this.processing = true;
        try {
            let updated: CloudChampionship | null = null;
            for (const [index, text] of messages.entries()) {
                const result = await Swal.fire({
                    title: `Confirmación ${index + 1} de 3`, text, icon: 'warning',
                    showCancelButton: true, confirmButtonText: 'Confirmar', cancelButtonText: 'Cancelar',
                    confirmButtonColor: '#dc2626'
                });
                if (!result.isConfirmed) return;
                updated = await firstValueFrom(this.administrationApi.confirmDeletion(
                    this.championship.id, (index + 1) as 1 | 2 | 3
                ));
            }
            this.championship = { ...this.championship, ...updated! };
            this.snackBar.open('Campeonato pendiente de eliminación hasta dentro de 14 días.', 'Cerrar', { duration: 5500 });
        } catch {
            this.snackBar.open('No fue posible solicitar la eliminación.', 'Cerrar', { duration: 4500 });
        } finally { this.processing = false; }
    }

    async recover(): Promise<void> {
        if (!this.championship || this.processing) return;
        this.processing = true;
        try {
            const updated = await firstValueFrom(
                this.administrationApi.recoverChampionship(this.championship.id)
            );
            this.championship = { ...this.championship, ...updated };
            this.snackBar.open('Campeonato recuperado y cerrado.', 'Cerrar', { duration: 4500 });
        } catch {
            this.snackBar.open('No fue posible recuperar el campeonato.', 'Cerrar', { duration: 4500 });
        } finally { this.processing = false; }
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

    private loadCompetitionDays(): void {
        this.championshipsApi
            .listCompetitionDays(this.championshipId)
            .subscribe({
                next: (days) => {
                    this.competitionDays = days;
                },
                error: () => {
                    this.snackBar.open(
                        'No fue posible cargar el detalle de los días.',
                        'Cerrar',
                        { duration: 4500 }
                    );
                }
            });
    }

    private async runLifecycle(
        action: 'activate' | 'pause' | 'close'
    ): Promise<void> {
        if (!this.championship) {
            return;
        }
        this.processing = true;
        try {
            const operation = action === 'activate'
                ? this.championshipsApi.activate(this.championship.id)
                : action === 'pause'
                    ? this.championshipsApi.pause(this.championship.id)
                    : this.championshipsApi.close(this.championship.id);
            const updated = await firstValueFrom(operation);
            this.championship = {
                ...this.championship,
                ...updated
            };
            this.snackBar.open(
                action === 'activate'
                    ? 'Campeonato activo'
                    : action === 'pause'
                        ? 'Campeonato pausado'
                        : 'Campeonato cerrado',
                'Cerrar',
                { duration: 3500 }
            );
        } catch (error) {
            const body = error instanceof HttpErrorResponse
                ? error.error as Partial<ApiErrorBody> & {
                    active_championship?: CloudChampionship;
                }
                : null;
            const activeName = body?.active_championship?.name;
            this.snackBar.open(
                activeName
                    ? `Primero pausa el campeonato activo: ${activeName}`
                    : body?.error || 'No fue posible cambiar el estado.',
                activeName ? 'Ver lista' : 'Cerrar',
                { duration: 6500 }
            ).onAction().subscribe(() => {
                void this.router.navigate(['/championships']);
            });
        } finally {
            this.processing = false;
        }
    }

    private apiMessage(error: unknown, fallback: string): string {
        if (error instanceof HttpErrorResponse) {
            const body = error.error as Partial<ApiErrorBody>;
            return body?.error || fallback;
        }
        return fallback;
    }
}
