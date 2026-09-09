import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import {
    CompetitionDay,
    CompetitionDayOperations,
    OperationCategory,
    OperationGymnast
} from '../../core/models/cloud.model';
import { CloudChampionshipApiService } from '../../core/services/cloud-championship-api.service';
import { CloudOperationsApiService } from '../../core/services/cloud-operations-api.service';
import { CloudScoringComponent } from '../cloud-scoring/cloud-scoring.component';

@Component({
    selector: 'app-operations',
    standalone: true,
    imports: [
        CommonModule, FormsModule, MatButtonModule, MatButtonToggleModule,
        MatCardModule, MatIconModule, MatSelectModule, RouterLink, CloudScoringComponent
    ],
    templateUrl: './operations.component.html',
    styleUrls: ['./operations.component.scss']
})
export class OperationsComponent implements OnInit, OnDestroy {
    readonly benches: Array<'A' | 'B'> = ['A', 'B'];
    readonly championshipId = this.route.snapshot.paramMap.get('championshipId') ?? '';
    days: CompetitionDay[] = [];
    operations: CompetitionDayOperations | null = null;
    selectedDayId = '';
    selectedBench: 'A' | 'B' = 'A';
    activatingGymnastId: string | null = null;
    loading = true;
    message = '';
    private refreshTimer: ReturnType<typeof setInterval> | null = null;

    constructor(
        private readonly route: ActivatedRoute,
        private readonly router: Router,
        private readonly championshipsApi: CloudChampionshipApiService,
        private readonly operationsApi: CloudOperationsApiService
    ) { }

    async ngOnInit(): Promise<void> {
        if (!this.championshipId) {
            await this.router.navigate(['/championships']);
            return;
        }
        try {
            const days = await firstValueFrom(
                this.championshipsApi.listCompetitionDays(this.championshipId)
            );
            this.days = days;
            this.selectedDayId = days[0]?.id ?? '';
            if (this.selectedDayId) {
                await this.loadDay();
                this.refreshTimer = setInterval(() => {
                    if (!this.activatingGymnastId) {
                        void this.loadDay(true);
                    }
                }, 3000);
            }
        } catch {
            this.message = 'No fue posible cargar la operación del campeonato.';
        } finally {
            this.loading = false;
        }
    }

    ngOnDestroy(): void {
        if (this.refreshTimer) clearInterval(this.refreshTimer);
    }

    async loadDay(silent = false): Promise<void> {
        if (!this.selectedDayId) return;
        const requestedDayId = this.selectedDayId;
        if (!silent) this.message = '';
        try {
            const operations = await firstValueFrom(
                this.operationsApi.getCompetitionDay(this.championshipId, requestedDayId)
            );
            if (this.selectedDayId === requestedDayId) this.operations = operations;
        } catch {
            if (!silent) this.message = 'No fue posible cargar el día seleccionado.';
        }
    }

    async activate(bench: 'A' | 'B', gymnastId: string): Promise<void> {
        if (!this.selectedDayId || this.activatingGymnastId) return;
        if (this.operations?.benches[bench].active?.gymnast_id === gymnastId) return;
        this.activatingGymnastId = gymnastId;
        this.message = '';
        try {
            await firstValueFrom(this.operationsApi.activateGymnast(
                this.championshipId, this.selectedDayId, bench, gymnastId
            ));
            await this.loadDay();
        } catch {
            this.message = 'No se pudo activar la gimnasta. El campeonato debe estar activo.';
        } finally {
            this.activatingGymnastId = null;
        }
    }

    selectBench(bench: 'A' | 'B'): void {
        this.selectedBench = bench;
    }

    trackCategory(_: number, category: OperationCategory): string { return category.id; }

    nextGymnast(bench: 'A' | 'B'): {
        gymnast: OperationGymnast;
        category: OperationCategory;
    } | null {
        const benchData = this.operations?.benches[bench];
        const activeId = benchData?.active?.gymnast_id;
        if (!benchData || !activeId) return null;
        const ordered = benchData.categories.flatMap((category) =>
            category.gymnasts.map((gymnast) => ({ gymnast, category }))
        );
        const activeIndex = ordered.findIndex(({ gymnast }) => gymnast.id === activeId);
        return activeIndex >= 0 ? ordered[activeIndex + 1] ?? null : null;
    }
}
