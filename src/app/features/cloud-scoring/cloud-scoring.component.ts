import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import Swal from 'sweetalert2';

import { CategoryScoring, ScoringGymnast } from '../../core/models/cloud.model';
import { CloudPublicationApiService } from '../../core/services/cloud-publication-api.service';
import { CloudScoringApiService } from '../../core/services/cloud-scoring-api.service';

@Component({
    selector: 'app-cloud-scoring',
    standalone: true,
    imports: [CommonModule, FormsModule, MatButtonModule, MatIconModule, RouterLink],
    templateUrl: './cloud-scoring.component.html',
    styleUrls: ['./cloud-scoring.component.scss']
})
export class CloudScoringComponent implements OnInit {
    readonly championshipId = this.route.snapshot.paramMap.get('championshipId') ?? '';
    readonly categoryId = this.route.snapshot.paramMap.get('categoryId') ?? '';
    scoring: CategoryScoring | null = null;
    draftValues: Record<string, string> = {};
    message = '';
    loading = true;
    savingId: string | null = null;

    constructor(
        private readonly route: ActivatedRoute,
        private readonly scoringApi: CloudScoringApiService,
        private readonly publicationApi: CloudPublicationApiService
    ) { }

    async ngOnInit(): Promise<void> { await this.load(); }

    async load(): Promise<void> {
        if (!this.championshipId || !this.categoryId) return;
        this.loading = true;
        this.message = '';
        try {
            this.scoring = await firstValueFrom(this.scoringApi.getCategory(
                this.championshipId, this.categoryId
            ));
            this.draftValues = {};
            for (const gymnast of this.scoring.gymnasts) {
                for (const score of gymnast.scores) this.draftValues[score.id] = score.value;
            }
        } catch {
            this.message = 'No fue posible cargar la planilla cloud.';
        } finally { this.loading = false; }
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

    async resolve(gymnast: ScoringGymnast, role: 'DA' | 'DB'): Promise<void> {
        const result = await Swal.fire({
            title: `Resolver valor ${role}`,
            text: 'Deja vacío para confirmar el valor visible.',
            input: 'text',
            inputPlaceholder: 'Ejemplo: 8.50',
            inputAttributes: { inputmode: 'decimal', maxlength: '5' },
            showCancelButton: true,
            confirmButtonText: 'Confirmar valor',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#4f46e5'
        });
        if (!result.isConfirmed) return;
        const value = String(result.value ?? '');
        try {
            await firstValueFrom(this.scoringApi.resolveRole(
                this.championshipId, gymnast.id, role, value.trim() || undefined
            ));
            await this.load();
        } catch { this.message = 'No fue posible resolver la discrepancia.'; }
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
        return assignment ? `${assignment.role} · ${assignment.judge.first_name}` : score.role ?? 'Nota';
    }
}
