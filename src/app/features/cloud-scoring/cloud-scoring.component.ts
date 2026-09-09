import { CommonModule } from '@angular/common';
import { Component, OnInit, OnDestroy, Input, Output, EventEmitter, ElementRef } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import {
    CdkDragDrop,
    DragDropModule,
    moveItemInArray
} from '@angular/cdk/drag-drop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import Swal from 'sweetalert2';

import { CategoryScoring, ScoringGymnast } from '../../core/models/cloud.model';
import { CloudPublicationApiService } from '../../core/services/cloud-publication-api.service';
import { CloudScoringApiService } from '../../core/services/cloud-scoring-api.service';

@Component({
    selector: 'app-cloud-scoring',
    standalone: true,
    imports: [
        CommonModule, FormsModule, MatButtonModule, MatIconModule,
        DragDropModule, RouterLink
    ],
    templateUrl: './cloud-scoring.component.html',
    styleUrls: ['./cloud-scoring.component.scss']
})
export class CloudScoringComponent implements OnInit, OnDestroy {
    @Input() championshipId = this.route.snapshot.paramMap.get('championshipId') ?? '';
    @Input() categoryId = this.route.snapshot.paramMap.get('categoryId') ?? '';
    @Input() embedded = false;
    @Input() activeGymnastId: string | null = null;
    @Input() activationPending = false;
    @Output() activateGymnast = new EventEmitter<string>();
    @Output() scoresChanged = new EventEmitter<void>();
    private timer?: ReturnType<typeof setInterval>;
    private refreshing = false;
    scoring: CategoryScoring | null = null;
    draftValues: Record<string, string> = {};
    roleDraftValues: Record<string, string> = {};
    message = '';
    loading = true;
    savingId: string | null = null;
    savingRoleKey: string | null = null;
    reordering = false;
    dragging = false;

    constructor(
        private readonly route: ActivatedRoute,
        private readonly element: ElementRef<HTMLElement>,
        private readonly scoringApi: CloudScoringApiService,
        private readonly publicationApi: CloudPublicationApiService
    ) { }

    async ngOnInit(): Promise<void> {
        await this.load();
        if (this.embedded) this.timer = setInterval(() => {
            if (!this.refreshing && !this.savingId && !this.savingRoleKey && !this.dragging &&
                !this.element.nativeElement.contains(document.activeElement)) void this.load(true);
        }, 3000);
    }

    ngOnDestroy(): void { if (this.timer) clearInterval(this.timer); }
    trackGymnast(_: number, gymnast: ScoringGymnast): string { return gymnast.id; }

    async load(silent = false): Promise<void> {
        if (!this.championshipId || !this.categoryId) return;
        this.refreshing = true;
        if (!silent) { this.loading = true; this.message = ''; }
        try {
            const result = await firstValueFrom(this.scoringApi.getCategory(
                this.championshipId, this.categoryId
            ));
            if (silent && this.element.nativeElement.contains(document.activeElement)) return;
            this.scoring = result;
            this.draftValues = {};
            this.roleDraftValues = {};
            for (const gymnast of this.scoring.gymnasts) {
                for (const score of gymnast.scores) this.draftValues[score.id] = score.value;
                this.roleDraftValues[this.roleKey(gymnast.id, 'DA')] = gymnast.summary.da_score;
                this.roleDraftValues[this.roleKey(gymnast.id, 'DB')] = gymnast.summary.db_score;
            }
            if (!silent) this.scoresChanged.emit();
        } catch {
            this.message = 'No fue posible cargar la planilla cloud.';
        } finally { this.loading = false; this.refreshing = false; }
    }

    async saveScore(scoreId: string): Promise<void> {
        const value = this.draftValues[scoreId];
        this.savingId = scoreId;
        try {
            await firstValueFrom(this.scoringApi.updateScore(this.championshipId, scoreId, value));
            await this.load();
        } catch {
            this.message = 'La nota debe estar entre 0 y 20, con hasta dos decimales.';
        } finally { this.savingId = null; }
    }

    async setDiscount(gymnast: ScoringGymnast, value: string): Promise<void> {
        try {
            await firstValueFrom(this.scoringApi.updateDiscount(this.championshipId, gymnast.id, value));
            await this.load();
        } catch { this.message = 'No fue posible actualizar el descuento.'; }
    }

    roleKey(gymnastId: string, role: 'DA' | 'DB'): string {
        return `${gymnastId}:${role}`;
    }

    async saveRoleValue(gymnast: ScoringGymnast, role: 'DA' | 'DB'): Promise<void> {
        const key = this.roleKey(gymnast.id, role);
        const value = this.roleDraftValues[key]?.trim();
        if (!value) {
            this.roleDraftValues[key] = role === 'DA'
                ? gymnast.summary.da_score
                : gymnast.summary.db_score;
            this.message = `Ingresa un valor válido para ${role}.`;
            return;
        }
        this.savingRoleKey = key;
        try {
            await firstValueFrom(this.scoringApi.resolveRole(
                this.championshipId, gymnast.id, role, value
            ));
            await this.load();
        } catch {
            this.roleDraftValues[key] = role === 'DA'
                ? gymnast.summary.da_score
                : gymnast.summary.db_score;
            this.message = `No fue posible guardar el valor de ${role}.`;
        } finally {
            this.savingRoleKey = null;
        }
    }

    async addGymnast(): Promise<void> {
        const result = await Swal.fire({
            title: 'Agregar gimnasta o conjunto',
            html: `
                <input id="gymnast-full-name" class="swal2-input" placeholder="Nombre completo">
                <input id="gymnast-club-name" class="swal2-input" placeholder="Club (opcional)">
            `,
            focusConfirm: false,
            showCancelButton: true,
            confirmButtonText: 'Agregar',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#4f46e5',
            preConfirm: () => {
                const fullName = (document.getElementById('gymnast-full-name') as HTMLInputElement)
                    ?.value.trim();
                const clubName = (document.getElementById('gymnast-club-name') as HTMLInputElement)
                    ?.value.trim() ?? '';
                if (!fullName) {
                    Swal.showValidationMessage('Ingresa el nombre de la gimnasta o conjunto');
                    return;
                }
                return { fullName, clubName };
            }
        });
        if (!result.isConfirmed || !result.value) return;
        try {
            await firstValueFrom(this.scoringApi.addGymnast(
                this.championshipId,
                this.categoryId,
                {
                    full_name: result.value.fullName,
                    club_name: result.value.clubName
                }
            ));
            await this.load();
        } catch { this.message = 'No fue posible agregar la gimnasta.'; }
    }

    async removeGymnast(gymnast: ScoringGymnast): Promise<void> {
        const confirmation = await Swal.fire({
            title: '¿Eliminar gimnasta?',
            text: `Eliminarás a ${gymnast.full_name}. Esta acción quedará trazada.`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Eliminar',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#dc2626'
        });
        if (!confirmation.isConfirmed) return;
        try {
            await firstValueFrom(this.scoringApi.removeGymnast(this.championshipId, gymnast.id));
            await this.load();
        } catch { this.message = 'No fue posible eliminar la gimnasta.'; }
    }

    async orderByScore(): Promise<void> {
        try {
            await firstValueFrom(this.scoringApi.orderGymnastsByScore(this.championshipId, this.categoryId));
            await this.load();
        } catch { this.message = 'No fue posible ordenar los resultados.'; }
    }

    async reorderGymnasts(event: CdkDragDrop<ScoringGymnast[]>): Promise<void> {
        this.dragging = false;
        if (!this.scoring || event.previousIndex === event.currentIndex || this.reordering) return;

        moveItemInArray(
            this.scoring.gymnasts,
            event.previousIndex,
            event.currentIndex
        );
        this.reordering = true;
        try {
            await firstValueFrom(this.scoringApi.reorderGymnasts(
                this.championshipId,
                this.categoryId,
                this.scoring.gymnasts.map(gymnast => gymnast.id)
            ));
            await this.load();
        } catch {
            this.message = 'No fue posible guardar el nuevo orden de las gimnastas.';
            await this.load();
        } finally {
            this.reordering = false;
        }
    }

    async publish(): Promise<void> {
        const confirmation = await Swal.fire({
            title: '¿Publicar categoría?',
            text: 'El público verá esta nueva fotografía de resultados.',
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: 'Publicar',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#4f46e5'
        });
        if (!confirmation.isConfirmed) return;
        try {
            await firstValueFrom(this.publicationApi.publishCategory(this.championshipId, this.categoryId));
            this.message = 'Categoría publicada correctamente.';
        } catch { this.message = 'Solo se puede publicar una categoría del campeonato activo.'; }
    }

    roleLabel(score: { role?: string; assignment_id?: string }): string {
        const assignment = this.scoring?.assignments.find((item) => item.id === score.assignment_id);
        return assignment ? this.assignmentLabel(assignment) : score.role ?? 'Nota';
    }

    readonly scoreAreas = ['DB', 'DA', 'A', 'E'];

    assignmentsForRole(role: string) {
        return this.scoring?.assignments.filter(item => item.role === role) ?? [];
    }

    scoresForRole(gymnast: ScoringGymnast, role: string) {
        const assignments = this.assignmentsForRole(role);
        return assignments.flatMap(assignment => gymnast.scores.filter(score => score.assignment_id === assignment.id));
    }

    assignmentLabel(assignment: { id: string; role: string }): string {
        const peers = this.scoring?.assignments.filter(item => item.role === assignment.role) ?? [];
        return `${assignment.role}${peers.findIndex(item => item.id === assignment.id) + 1}`;
    }
}
