import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import {
    CompetitionDay,
    CompetitionDayOperations
} from '../../core/models/cloud.model';
import { CloudChampionshipApiService } from '../../core/services/cloud-championship-api.service';
import { CloudOperationsApiService } from '../../core/services/cloud-operations-api.service';

@Component({
    selector: 'app-operations',
    standalone: true,
    imports: [
        CommonModule, FormsModule, MatButtonModule, MatCardModule, MatIconModule,
        MatSelectModule, RouterLink
    ],
    templateUrl: './operations.component.html',
    styleUrls: ['./operations.component.scss']
})
export class OperationsComponent implements OnInit {
    readonly benches: Array<'A' | 'B'> = ['A', 'B'];
    readonly championshipId = this.route.snapshot.paramMap.get('championshipId') ?? '';
    days: CompetitionDay[] = [];
    operations: CompetitionDayOperations | null = null;
    selectedDayId = '';
    loading = true;
    message = '';

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
            }
        } catch {
            this.message = 'No fue posible cargar la operación del campeonato.';
        } finally {
            this.loading = false;
        }
    }

    async loadDay(): Promise<void> {
        if (!this.selectedDayId) return;
        this.message = '';
        try {
            this.operations = await firstValueFrom(
                this.operationsApi.getCompetitionDay(this.championshipId, this.selectedDayId)
            );
        } catch {
            this.message = 'No fue posible cargar el día seleccionado.';
        }
    }

    async activate(bench: 'A' | 'B', gymnastId: string): Promise<void> {
        if (!this.selectedDayId) return;
        try {
            await firstValueFrom(this.operationsApi.activateGymnast(
                this.championshipId, this.selectedDayId, bench, gymnastId
            ));
            await this.loadDay();
        } catch {
            this.message = 'No se pudo activar la gimnasta. El campeonato debe estar activo.';
        }
    }

}
