import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
    Component,
    OnInit
} from '@angular/core';
import { FormsModule } from '@angular/forms';
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
import { JudgeLinkDeliveryComponent } from '../../shared/judge-link-delivery.component';
import { CredentialDeliveryService } from '../../core/services/credential-delivery.service';

import { CloudExportApiService } from '../../core/services/cloud-export-api.service';

import { ApiErrorBody } from '../../core/models/api-error.model';
import {
    ChampionshipStatus,
    CloudChampionship,
    CloudChampionshipDetail,
    CompetitionDay,
    CloudJudge,
    JudgeAssignment
} from '../../core/models/cloud.model';
import {
    CloudChampionshipApiService
} from '../../core/services/cloud-championship-api.service';
import { CloudAdministrationApiService } from '../../core/services/cloud-administration-api.service';
import { CloudJudgeApiService } from '../../core/services/cloud-judge-api.service';
import { CloudOperationsApiService } from '../../core/services/cloud-operations-api.service';
import {
    formatRutInput,
    normalizeRut,
    rutValidationCode
} from '../../core/utils/rut.utils';

@Component({
    selector: 'app-championship-detail',
    standalone: true,
    imports: [
        CommonModule,
        JudgeLinkDeliveryComponent,
        FormsModule,
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
    assignments: JudgeAssignment[] = [];
    judges: CloudJudge[] = [];
    selectedAssignmentDayId = '';
    replacementJudgeIds: Record<string, string> = {};
    judgeSearchText = '';
    judgeSearchResults: CloudJudge[] = [];
    searchingJudges = false;
    showNewJudgeForm = false;
    assignmentDraft: {
        bench: 'A' | 'B'; session: 'AM' | 'PM'; role: 'DA' | 'DB' | 'A' | 'E' | 'L' | 'P';
        judgeId: string; firstName: string; lastName: string; rut: string;
    } = {
        bench: 'A', session: 'AM', role: 'DA', judgeId: '',
        firstName: '', lastName: '', rut: ''
    };
    loading = true;
    processing = false;
    downloading = false;
    selectedDayFile: File | null = null;
    selectedDayDate = '';
    managingAssignments = false;
    errorMessage = '';

    private judgeSearchTimer: ReturnType<typeof setTimeout> | undefined;
    private judgeSearchRequest = 0;

    private readonly championshipId =
        this.route.snapshot.paramMap.get('championshipId') ?? '';

    constructor(
        private readonly credentialDelivery: CredentialDeliveryService,
        private readonly route: ActivatedRoute,
        private readonly router: Router,
        private readonly championshipsApi: CloudChampionshipApiService,
        private readonly administrationApi: CloudAdministrationApiService,
        private readonly operationsApi: CloudOperationsApiService,
        private readonly judgesApi: CloudJudgeApiService,
        private readonly exportApi: CloudExportApiService,
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
                    void this.loadJudgeManagement();
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

    async download(format: 'excel' | 'pdf'): Promise<void> {
        if (this.downloading) return;
        this.downloading = true;
        try {
            const blob = await firstValueFrom(this.exportApi.download(this.championshipId, format));
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `resultados-${this.championshipId}.${format === 'excel' ? 'xlsx' : 'pdf'}`;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch {
            this.snackBar.open('No fue posible generar la exportación.', 'Cerrar', { duration: 4500 });
        } finally { this.downloading = false; }
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
            title: 'Terminar campeonato',
            html:
                'Dejará de estar operativo y no podrá reactivarse.<br>'
                + '<strong>Usa “Pausar” si la interrupción es temporal.</strong>',
            icon: 'warning',
            input: 'checkbox',
            inputPlaceholder: 'Comprendo que la finalización es definitiva',
            inputValidator: (checked) =>
                checked ? undefined : 'Debes confirmar la finalización definitiva',
            showCancelButton: true,
            confirmButtonText: 'Terminar campeonato',
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
            CLOSED: 'Terminado',
            PENDING_DELETION: 'Pendiente de eliminación',
            DELETED: 'Eliminado'
        };
        return labels[status];
    }

    assignmentsForSelectedDay(): JudgeAssignment[] {
        return this.assignments
            .filter((assignment) =>
                assignment.competition_day.id === this.selectedAssignmentDayId
            )
            .sort((first, second) => {
                const roleDifference = this.assignmentRoleOrder(first.role)
                    - this.assignmentRoleOrder(second.role);
                if (roleDifference !== 0) return roleDifference;

                const categoryDifference = first.effective_from_category.passing_order
                    - second.effective_from_category.passing_order;
                if (categoryDifference !== 0) return categoryDifference;

                return `${first.judge.last_name} ${first.judge.first_name}`.localeCompare(
                    `${second.judge.last_name} ${second.judge.first_name}`,
                    'es'
                );
            });
    }

    assignmentRoleLabel(assignment: JudgeAssignment): string {
        const matchingAssignments = this.assignmentsForSelectedDay()
            .filter((item) => item.role === assignment.role
                && item.bench === assignment.bench && item.session === assignment.session);
        return `${assignment.role}${matchingAssignments.findIndex((item) =>
            item.id === assignment.id
        ) + 1}`;
    }

    get assignmentChangesAllowed(): boolean {
        return this.championship?.status !== 'CLOSED'
            && this.championship?.status !== 'PENDING_DELETION'
            && this.championship?.status !== 'DELETED';
    }

    get assignmentAreaFull(): boolean {
        return this.assignmentsForSelectedDay().filter((item) =>
            item.bench === this.assignmentDraft.bench
            && item.session === this.assignmentDraft.session
            && item.role === this.assignmentDraft.role).length >= 4;
    }

    get inlineJudgeInvalid(): boolean {
        const draft = this.assignmentDraft;
        return !draft.firstName.trim() || !draft.lastName.trim()
            || rutValidationCode(draft.rut) !== null;
    }

    formatInlineRut(value: string): void {
        this.assignmentDraft.rut = formatRutInput(value);
    }

    selectCompetitionDayFile(event: Event): void {
        const input = event.target as HTMLInputElement;
        this.selectedDayFile = input.files?.[0] ?? null;
    }

    async uploadCompetitionDay(): Promise<void> {
        if (!this.championship || !this.selectedDayFile || !this.selectedDayDate || this.processing) {
            this.snackBar.open('Selecciona una fecha y la planilla del día.', 'Cerrar', { duration: 4000 });
            return;
        }
        this.processing = true;
        try {
            const preview = await firstValueFrom(this.championshipsApi.addCompetitionDay(
                this.championship.id, this.selectedDayFile, this.selectedDayDate
            ));
            await this.router.navigate(['/championships', this.championship.id, 'import'], {
                queryParams: { previewId: preview.id, dayUpload: '1', returnToDetail: '1' }
            });
        } catch (error) {
            this.snackBar.open(this.apiMessage(error, 'No fue posible analizar la planilla.'), 'Cerrar', { duration: 5000 });
        } finally {
            this.processing = false;
        }
    }

    onJudgeSearchChanged(): void {
        this.assignmentDraft.judgeId = '';
        this.showNewJudgeForm = false;
        if (this.judgeSearchTimer) {
            clearTimeout(this.judgeSearchTimer);
        }
        const query = this.judgeSearchText.trim();
        const request = ++this.judgeSearchRequest;
        if (!query) {
            this.judgeSearchResults = [];
            this.searchingJudges = false;
            return;
        }
        this.searchingJudges = true;
        this.judgeSearchTimer = setTimeout(() => {
            void this.searchJudges(query, request);
        }, 250);
    }

    selectJudge(judge: CloudJudge): void {
        this.assignmentDraft.judgeId = judge.id;
        this.judgeSearchText = `${judge.first_name} ${judge.last_name} · ${judge.rut}`;
        this.judgeSearchResults = [];
        this.showNewJudgeForm = false;
    }

    openNewJudgeForm(): void {
        this.assignmentDraft.judgeId = '';
        this.judgeSearchText = '';
        this.judgeSearchResults = [];
        this.showNewJudgeForm = true;
    }

    async createAssignment(): Promise<void> {
        if (!this.selectedAssignmentDayId || this.managingAssignments) {
            return;
        }
        const draft = this.assignmentDraft;
        if (this.assignmentAreaFull) {
            this.snackBar.open('Máximo 4 jueces por área, banca y jornada.', 'Cerrar', { duration: 4500 });
            return;
        }
        if (!draft.judgeId && !this.showNewJudgeForm) {
            this.snackBar.open(
                'Busca y selecciona un juez, o crea uno nuevo para continuar.',
                'Cerrar', { duration: 4500 }
            );
            return;
        }
        if (!draft.judgeId && this.inlineJudgeInvalid) {
            this.snackBar.open(
                'Ingresa nombre, apellido y un RUT válido para crear el juez.',
                'Cerrar', { duration: 4500 }
            );
            return;
        }
        this.managingAssignments = true;
        try {
            const result = await firstValueFrom(this.operationsApi.createAssignment(
                this.championshipId,
                {
                    competition_day_id: this.selectedAssignmentDayId,
                    bench: draft.bench,
                    session: draft.session,
                    role: draft.role,
                    ...(draft.judgeId ? { judge_id: draft.judgeId } : {
                        judge: {
                            first_name: draft.firstName.trim(),
                            last_name: draft.lastName.trim(),
                            rut: normalizeRut(draft.rut)
                        }
                    })
                }
            ));
            this.assignmentDraft = {
                ...this.assignmentDraft,
                judgeId: '', firstName: '', lastName: '', rut: ''
            };
            this.judgeSearchText = '';
            this.judgeSearchResults = [];
            this.showNewJudgeForm = false;
            await this.refreshAssignmentData();
            if (result.credentials) {
                this.credentialDelivery.addImported(`${draft.firstName} ${draft.lastName}`, result.credentials);
            }
            this.snackBar.open(
                result.credentials
                    ? 'Juez asignado. Copia su enlace de acceso en la bandeja.'
                    : this.championship?.status === 'DRAFT'
                        ? 'Juez asignado correctamente.'
                        : `Juez asignado desde ${result.assignment.effective_from_category.name}.`,
                'Cerrar', { duration: result.credentials ? 8000 : 3500 }
            );
        } catch (error) {
            this.snackBar.open(
                this.apiMessage(error, 'No fue posible asignar al juez. Revisa los datos y el rol.'),
                'Cerrar', { duration: 5000 }
            );
        } finally {
            this.managingAssignments = false;
        }
    }

    async reassign(assignment: JudgeAssignment): Promise<void> {
        const judgeId = this.replacementJudgeIds[assignment.id];
        if (!judgeId || this.managingAssignments) {
            return;
        }
        this.managingAssignments = true;
        try {
            const result = await firstValueFrom(this.operationsApi.reassign(
                this.championshipId, assignment.id, { judge_id: judgeId }
            ));
            delete this.replacementJudgeIds[assignment.id];
            await this.refreshAssignmentData();
            if (result.credentials) {
                this.credentialDelivery.addImported(result.credentials.username, result.credentials);
            }
            this.snackBar.open(
                result.credentials
                    ? 'Juez cambiado. Copia su enlace de acceso en la bandeja.'
                    : `Juez cambiado desde ${result.assignment.effective_from_category.name}.`,
                'Cerrar', { duration: result.credentials ? 8000 : 4500 }
            );
        } catch (error) {
            this.snackBar.open(
                this.apiMessage(error, 'No fue posible cambiar el juez.'),
                'Cerrar', { duration: 5000 }
            );
        } finally {
            this.managingAssignments = false;
        }
    }

    async removeAssignment(assignment: JudgeAssignment): Promise<void> {
        if (this.managingAssignments) {
            return;
        }
        const appliesFromNextCategory = this.championship?.status !== 'DRAFT';
        const confirmation = await Swal.fire({
            title: '¿Eliminar esta asignación?',
            html: appliesFromNextCategory
                ? 'El juez conservará su acceso sólo hasta la categoría actual. '
                    + '<strong>Se eliminará desde la siguiente categoría disponible.</strong>'
                : 'Se quitará este juez de la banca, jornada y rol seleccionados.',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Eliminar asignación',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#dc2626'
        });
        if (!confirmation.isConfirmed) {
            return;
        }
        this.managingAssignments = true;
        try {
            const result = await firstValueFrom(this.operationsApi.removeAssignment(
                this.championshipId, assignment.id
            ));
            delete this.replacementJudgeIds[assignment.id];
            await this.refreshAssignmentData();
            this.snackBar.open(
                result.effective_from_category
                    ? `Juez eliminado desde ${result.effective_from_category.name}.`
                    : 'Asignación eliminada correctamente.',
                'Cerrar', { duration: 4500 }
            );
        } catch (error) {
            this.snackBar.open(
                this.apiMessage(error, 'No fue posible eliminar la asignación.'),
                'Cerrar', { duration: 5000 }
            );
        } finally {
            this.managingAssignments = false;
        }
    }

    private loadCompetitionDays(): void {
        this.championshipsApi
            .listCompetitionDays(this.championshipId)
            .subscribe({
        next: (days) => {
                    this.competitionDays = days;
                    this.selectedAssignmentDayId = days[0]?.id ?? '';
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

    private async loadJudgeManagement(): Promise<void> {
        try {
            await this.refreshAssignmentData();
        } catch {
            this.snackBar.open(
                'No fue posible cargar las asignaciones de jueces.',
                'Cerrar', { duration: 4500 }
            );
        }
    }

    private assignmentRoleOrder(role: JudgeAssignment['role']): number {
        return ['DB', 'DA', 'A', 'E', 'L', 'P'].indexOf(role);
    }

    private async searchJudges(query: string, request: number): Promise<void> {
        try {
            const judges = await firstValueFrom(this.judgesApi.search(query));
            if (request !== this.judgeSearchRequest) {
                return;
            }
            this.judgeSearchResults = judges;
        } catch {
            if (request === this.judgeSearchRequest) {
                this.judgeSearchResults = [];
            }
        } finally {
            if (request === this.judgeSearchRequest) {
                this.searchingJudges = false;
            }
        }
    }

    private async refreshAssignmentData(): Promise<void> {
        const [assignments, judges] = await Promise.all([
            firstValueFrom(this.operationsApi.listAssignments(this.championshipId)),
            firstValueFrom(this.judgesApi.search(''))
        ]);
        this.assignments = assignments;
        this.judges = judges;
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
                        : 'Campeonato terminado',
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
