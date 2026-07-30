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
    CompetitionDayOperations,
    JudgeAssignment,
    CloudJudge
} from '../../core/models/cloud.model';
import { CloudChampionshipApiService } from '../../core/services/cloud-championship-api.service';
import { CloudJudgeApiService } from '../../core/services/cloud-judge-api.service';
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
    assignments: JudgeAssignment[] = [];
    judges: CloudJudge[] = [];
    selectedDayId = '';
    assignmentDraft: {
        bench: 'A' | 'B'; session: 'AM' | 'PM'; role: 'DA' | 'DB' | 'A' | 'E' | 'L' | 'P';
        judgeId: string; firstName: string; lastName: string; rut: string;
    } = { bench: 'A', session: 'AM', role: 'DA', judgeId: '', firstName: '', lastName: '', rut: '' };
    loading = true;
    message = '';

    constructor(
        private readonly route: ActivatedRoute,
        private readonly router: Router,
        private readonly championshipsApi: CloudChampionshipApiService,
        private readonly operationsApi: CloudOperationsApiService,
        private readonly judgesApi: CloudJudgeApiService
    ) { }

    async ngOnInit(): Promise<void> {
        if (!this.championshipId) {
            await this.router.navigate(['/championships']);
            return;
        }
        try {
            const [days, assignments] = await Promise.all([
                firstValueFrom(this.championshipsApi.listCompetitionDays(this.championshipId)),
                firstValueFrom(this.operationsApi.listAssignments(this.championshipId)),
                this.refreshJudges()
            ]);
            this.days = days;
            this.assignments = assignments;
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

    assignmentsForDay(): JudgeAssignment[] {
        return this.assignments.filter((assignment) =>
            assignment.competition_day.id === this.selectedDayId
        );
    }

    async refreshJudges(): Promise<void> {
        this.judges = await firstValueFrom(this.judgesApi.search(''));
    }

    async createAssignment(): Promise<void> {
        if (!this.selectedDayId) return;
        const draft = this.assignmentDraft;
        try {
            const request = {
                competition_day_id: this.selectedDayId,
                bench: draft.bench,
                session: draft.session,
                role: draft.role,
                ...(draft.judgeId ? { judge_id: draft.judgeId } : {
                    judge: {
                        first_name: draft.firstName,
                        last_name: draft.lastName,
                        rut: draft.rut
                    }
                })
            };
            const result = await firstValueFrom(
                this.operationsApi.createAssignment(this.championshipId, request)
            );
            this.message = result.credentials
                ? `Asignación creada. Credenciales: ${result.credentials.username} / ${result.credentials.password}`
                : 'Asignación creada correctamente.';
            this.assignments = await firstValueFrom(
                this.operationsApi.listAssignments(this.championshipId)
            );
            await this.refreshJudges();
        } catch {
            this.message = 'No fue posible crear la asignación. Revisa el juez, día y rol.';
        }
    }

    async reassign(assignment: JudgeAssignment): Promise<void> {
        const choices = this.judges.map((judge) =>
            `${judge.id} — ${judge.first_name} ${judge.last_name}`
        ).join('\n');
        const judgeId = window.prompt(
            `Pega el identificador del nuevo juez. La reasignación comienza en la siguiente categoría.\n\n${choices}`
        )?.trim();
        if (!judgeId) return;
        try {
            await firstValueFrom(this.operationsApi.reassign(
                this.championshipId, assignment.id, { judge_id: judgeId }
            ));
            this.assignments = await firstValueFrom(
                this.operationsApi.listAssignments(this.championshipId)
            );
            this.message = 'Juez reasignado desde la siguiente categoría aplicable.';
        } catch {
            this.message = 'No fue posible reasignar al juez.';
        }
    }
}
