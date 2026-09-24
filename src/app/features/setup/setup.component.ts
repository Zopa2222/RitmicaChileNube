import { InitialImportQueueService } from '../../core/services/initial-import-queue.service';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
    ChangeDetectorRef,
    Component,
    DestroyRef,
    ElementRef,
    OnInit,
    QueryList,
    ViewChildren
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
    FormBuilder,
    FormsModule,
    ReactiveFormsModule,
    Validators
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
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

import { ApiErrorBody } from '../../core/models/api-error.model';
import {
    CloudChampionshipDetail,
    ImportMarker,
    ImportPreview,
    ImportPreviewSheet
} from '../../core/models/cloud.model';
import {
    CloudChampionshipApiService
} from '../../core/services/cloud-championship-api.service';

type CutoffOption = number | 'MANUAL' | null;

@Component({
    selector: 'app-setup',
    standalone: true,
    imports: [
        CommonModule,
        JudgeLinkDeliveryComponent,
        FormsModule,
        MatButtonModule,
        MatCardModule,
        MatFormFieldModule,
        MatIconModule,
        MatInputModule,
        MatProgressSpinnerModule,
        MatSelectModule,
        MatSnackBarModule,
        ReactiveFormsModule,
        RouterLink
    ],
    templateUrl: './setup.component.html',
    styleUrls: ['./setup.component.scss']
})
export class SetupComponent implements OnInit {
    @ViewChildren('initialDayFileInput')
    private initialDayFileInputs!: QueryList<ElementRef<HTMLInputElement>>;

    readonly championshipForm = this.formBuilder.nonNullable.group({
        name: ['', [Validators.required, Validators.maxLength(180)]],
        kind: ['CLASIFICATORIO', Validators.required],
        zone: ['', Validators.required],
        qualifier_number: [1 as 1 | 2, Validators.required],
        start_date: ['', Validators.required]
    });

    championship: CloudChampionshipDetail | null = null;
    preview: ImportPreview | null = null;
    selectedFile: File | null = null;
    competitionDate = '';
    initialDayFiles: Array<{ date: string; file: File | null; validating?: boolean; validated?: boolean; error?: string }> = [
        { date: '', file: null }
    ];
    get creationQueue(): Array<{ date: string; file: File }> {
        return this.initialImportQueue.days;
    }
    loading = false;
    pageLoading = false;
    errorMessage = '';
    savingCutoffSequence: number | null = null;
    cutoffOptions: Record<number, CutoffOption> = {};
    manualRows: Record<number, number | null> = {};
    invalidCutoffSequences = new Set<number>();
    private readonly dirtyCutoffSequences = new Set<number>();

    private readonly routeChampionshipId =
        this.route.snapshot.paramMap.get('championshipId');
    private readonly routePreviewId =
        this.route.snapshot.queryParamMap.get('previewId');
    private readonly addingDay =
        this.route.snapshot.queryParamMap.get('dayUpload') === '1';
    private readonly initialSetup =
        this.route.snapshot.queryParamMap.get('initialSetup') === '1';
    private readonly returnToChampionshipDetail =
        this.route.snapshot.queryParamMap.get('returnToDetail') === '1';

    constructor(
        private readonly initialImportQueue: InitialImportQueueService,
        private readonly credentialDelivery: CredentialDeliveryService,
        private readonly changeDetector: ChangeDetectorRef,
        private readonly formBuilder: FormBuilder,
        private readonly route: ActivatedRoute,
        private readonly router: Router,
        private readonly championshipsApi: CloudChampionshipApiService,
        private readonly snackBar: MatSnackBar,
        destroyRef: DestroyRef
    ) {
        this.championshipForm.controls.start_date.valueChanges
            .pipe(takeUntilDestroyed(destroyRef))
            .subscribe(() => this.updateInitialDayDates());
    }

    ngOnInit(): void {
        if (this.routeChampionshipId) {
            this.loadDraft(this.routeChampionshipId);
        }
    }

    get allCutoffsConfirmed(): boolean {
        return Boolean(
            this.preview?.preview.sheets.length
            && this.preview.preview.sheets.every(
                (sheet) => sheet.cutoff_confirmed
            )
        );
    }

    get canConfirmImport(): boolean {
        return this.allCutoffsConfirmed && !this.cutoffsDirty;
    }

    get savingCutoffs(): boolean {
        return this.savingCutoffSequence !== null;
    }

    get cutoffsDirty(): boolean {
        return this.dirtyCutoffSequences.size > 0;
    }

    initialDayDateError(index: number): string {
        const date = this.initialDayFiles[index].date;
        const startDate = this.championshipForm.controls.start_date.value;
        if (!date) return 'Selecciona la fecha de este día.';
        if (startDate && date < startDate) {
            return 'La fecha no puede ser anterior a la fecha del primer día.';
        }
        if (this.initialDayFiles.some((day, otherIndex) => otherIndex !== index && day.date === date)) {
            return 'Esta fecha ya está asignada a otro día.';
        }
        if (this.initialDayFiles.slice(0, index).some((day) => day.date && day.date >= date)) {
            return 'La fecha debe ser posterior a la de los días anteriores.';
        }
        return '';
    }

    get initialDayDatesInvalid(): boolean {
        return !this.initialDayFiles.length
            || this.initialDayFiles.some((_, index) => Boolean(this.initialDayDateError(index)));
    }

    get initialFilesInvalid(): boolean {
        return this.initialDayFiles.some(day => !day.file || !day.validated || day.validating);
    }

    trackInitialDay(index: number): number {
        return index;
    }

    enforceInitialDayMinimum(index: number, event: Event): void {
        const input = event.target as HTMLInputElement;
        const startDate = this.championshipForm.controls.start_date.value;
        if (input.value && startDate && input.value < startDate) {
            input.value = startDate;
            this.initialDayFiles[index].date = startDate;
        }
    }

    private initialDateForDay(index: number): string {
        const startDate = this.championshipForm.controls.start_date.value;
        if (!startDate) return '';
        // Use calendar days in UTC so month/year boundaries and DST are handled.
        const date = new Date(`${startDate}T00:00:00Z`);
        if (Number.isNaN(date.getTime())) return '';
        date.setUTCDate(date.getUTCDate() + index);
        return date.toISOString().slice(0, 10);
    }

    private updateInitialDayDates(): void {
        this.initialDayFiles = this.initialDayFiles.map((day, index) => ({
            ...day,
            date: this.initialDateForDay(index)
        }));
    }

    createChampionship(): void {
        if (this.championshipForm.invalid || this.loading) {
            this.championshipForm.markAllAsTouched();
            return;
        }

        if (this.initialDayDatesInvalid) {
            this.errorMessage = 'Corrige las fechas de los días de competencia antes de continuar.';
            return;
        }

        if (this.initialFilesInvalid) {
            this.errorMessage = 'Espera el análisis y corrige las planillas indicadas antes de continuar.';
            return;
        }

        const providedDays = this.initialDayFiles.filter(
            (day) => day.date || day.file
        );
        if (!providedDays.length) {
            this.errorMessage = 'Agrega al menos un día con su fecha y planilla.';
            return;
        }
        if (providedDays.some((day) => !day.date || !day.file)) {
            this.errorMessage = 'Cada día inicial debe tener fecha y planilla.';
            return;
        }
        if (new Set(providedDays.map((day) => day.date)).size !== providedDays.length) {
            this.errorMessage = 'Las fechas de los días iniciales no pueden repetirse.';
            return;
        }

        if (providedDays.some((day) => day.date < this.championshipForm.controls.start_date.value)) {
            this.errorMessage = 'Ningún día puede ser anterior a la fecha del primer día.';
            return;
        }

        this.loading = true;
        this.errorMessage = '';
        const value = this.championshipForm.getRawValue();
        this.championshipsApi.create({
            name: value.name.trim(),
            kind: value.kind,
            zone: value.zone,
            qualifier_number: value.kind === 'CLASIFICATORIO' ? value.qualifier_number : null,
            start_date: value.start_date
        }).subscribe({
            next: (championship) => {
                this.championship = championship as CloudChampionshipDetail;
                this.loading = false;
                this.initialImportQueue.championshipId = championship.id;
                this.initialImportQueue.days = providedDays.map((day) => ({
                    date: day.date, file: day.file!
                }));
                if (this.creationQueue.length) {
                    void this.uploadNextInitialDay(championship.id);
                } else {
                    void this.router.navigate(['/championships', championship.id]);
                }
            },
            error: (error) => {
                this.errorMessage = this.apiMessage(
                    error,
                    'No fue posible crear el campeonato.'
                );
                this.loading = false;
            }
        });
    }

    addInitialDay(): void {
        if (this.loading) return;
        this.initialDayFiles = [
            ...this.initialDayFiles,
            { date: this.initialDateForDay(this.initialDayFiles.length), file: null }
        ];
        // Render the input synchronously so the picker keeps the user's click activation.
        this.changeDetector.detectChanges();
        this.initialDayFileInputs.last.nativeElement.click();
    }

    selectInitialDayFile(index: number, event: Event): void {
        const input = event.target as HTMLInputElement;
        const file = input.files?.[0] ?? null;
        if (!file) return;
        if (!file.name.toLowerCase().endsWith('.xlsx')) {
            this.initialDayFiles[index] = { ...this.initialDayFiles[index], file: null, validated: false, validating: false, error: 'Selecciona una planilla Excel con extensión .xlsx.' };
            input.value = '';
            return;
        }
        if (file.size > 16 * 1024 * 1024) {
            this.initialDayFiles[index] = { ...this.initialDayFiles[index], file: null, validated: false, validating: false, error: 'La planilla no puede superar los 16 MB.' };
            input.value = '';
            return;
        }
        this.errorMessage = '';
        this.initialDayFiles[index] = { ...this.initialDayFiles[index], file, validating: true, validated: false, error: '' };
        input.value = '';
        this.championshipsApi.validateDayFile(file).subscribe({
            next: () => {
                if (this.initialDayFiles[index].file !== file) return;
                this.initialDayFiles[index] = { ...this.initialDayFiles[index], validating: false, validated: true };
            },
            error: (error) => {
                if (this.initialDayFiles[index].file !== file) return;
                this.initialDayFiles[index] = { ...this.initialDayFiles[index], validating: false, validated: false,
                    error: this.apiMessage(error, 'No se pudo analizar la planilla. Selecciónala nuevamente para reintentar.') };
            }
        });
    }

    private async uploadNextInitialDay(championshipId: string): Promise<void> {
        const next = this.creationQueue[0];
        if (!next) return;
        this.loading = true;
        this.errorMessage = '';
        this.preview = null;
        this.selectedFile = next.file;
        this.competitionDate = next.date;
        try {
            const preview = await firstValueFrom(
                this.championshipsApi.createImportPreview(championshipId, next.file, next.date)
            );
            this.competitionDate = next.date;
            this.preview = preview;
            this.initializeCutoffs(preview);
            await this.router.navigate(['/championships', championshipId, 'import'], {
                queryParams: {
                    previewId: preview.id,
                    dayUpload: '1',
                    initialSetup: '1',
                    returnToDetail: '1'
                },
                replaceUrl: true
            });
        } catch (error) {
            this.errorMessage = this.apiMessage(error, 'No fue posible analizar la planilla. Puedes volver a analizarla.');
        } finally {
            this.loading = false;
        }
    }

    retryInitialDay(): void {
        if (!this.championship || this.loading || !this.creationQueue.length) return;
        void this.uploadNextInitialDay(this.championship.id);
    }

    replaceQueuedDayFile(event: Event): void {
        if (this.loading || !this.creationQueue.length) return;
        const input = event.target as HTMLInputElement;
        if (!input.files?.length) return;
        this.selectFile(event);
        if (!this.selectedFile || this.errorMessage) return;
        this.creationQueue[0].file = this.selectedFile;
        input.value = '';
        this.retryInitialDay();
    }

    selectFile(event: Event): void {
        const input = event.target as HTMLInputElement;
        const file = input.files?.[0] ?? null;
        this.errorMessage = '';

        if (!file) {
            this.selectedFile = null;
            return;
        }
        if (!file.name.toLocaleLowerCase().endsWith('.xlsx')) {
            this.selectedFile = null;
            input.value = '';
            this.errorMessage = 'Selecciona un archivo con extensión .xlsx.';
            return;
        }
        if (file.size > 16 * 1024 * 1024) {
            this.selectedFile = null;
            input.value = '';
            this.errorMessage = 'El archivo supera el máximo de 16 MB.';
            return;
        }
        this.selectedFile = file;
    }

    uploadExcel(): void {
        if (!this.championship || !this.selectedFile || this.loading) {
            if (!this.selectedFile) {
                this.errorMessage = 'Selecciona el orden de paso en formato .xlsx.';
            }
            return;
        }

        if (!this.competitionDate) {
            this.errorMessage = 'Selecciona la fecha del día de competencia.';
            return;
        }
        if (this.competitionDate < this.championship.start_date) {
            this.errorMessage = 'La fecha no puede ser anterior al primer día del campeonato.';
            return;
        }
        this.loading = true;
        this.errorMessage = '';
        this.championshipsApi.createImportPreview(
            this.championship.id,
            this.selectedFile,
            this.competitionDate
        ).subscribe({
            next: (preview) => {
                this.preview = preview;
                this.initializeCutoffs(preview);
                this.loading = false;
                void this.router.navigate([], {
                    relativeTo: this.route,
                    queryParams: { previewId: preview.id },
                    queryParamsHandling: 'merge',
                    replaceUrl: true
                });
                window.scrollTo({ top: 0, behavior: 'smooth' });
            },
            error: (error) => {
                this.errorMessage = this.apiMessage(
                    error,
                    'No fue posible analizar el Excel.'
                );
                this.loading = false;
            }
        });
    }

    previewJudgeRoleLabel(judge: ImportPreview['preview']['judges'][number]): string {
        const group = this.preview!.preview.judges.filter((item) =>
            item.bench === judge.bench && item.session === judge.session && item.role === judge.role);
        return `${judge.role}${group.indexOf(judge) + 1}`;
    }

    eligibleMarkers(sheet: ImportPreviewSheet): ImportMarker[] {
        return sheet.markers.filter((marker) => marker.eligible_cutoff);
    }

    detectedMarker(sheet: ImportPreviewSheet): ImportMarker | null {
        return sheet.markers.find(
            (marker) => marker.row === sheet.detected_cutoff_row
        ) ?? null;
    }

    optionChanged(sheet: ImportPreviewSheet, option: CutoffOption): void {
        this.cutoffOptions[sheet.sequence] = option;
        if (option !== 'MANUAL') {
            this.manualRows[sheet.sequence] = null;
        }
        this.dirtyCutoffSequences.add(sheet.sequence);
        this.invalidCutoffSequences.delete(sheet.sequence);
        this.invalidCutoffSequences = new Set(this.invalidCutoffSequences);
    }

    manualRowChanged(sheet: ImportPreviewSheet, value: number): void {
        this.manualRows[sheet.sequence] = value;
        this.dirtyCutoffSequences.add(sheet.sequence);
        this.invalidCutoffSequences.delete(sheet.sequence);
        this.invalidCutoffSequences = new Set(this.invalidCutoffSequences);
    }

    isCutoffDirty(sheet: ImportPreviewSheet): boolean {
        return this.dirtyCutoffSequences.has(sheet.sequence);
    }

    confirmCutoffs(sheet: ImportPreviewSheet): void {
        if (!this.preview || !this.championship || this.savingCutoffs) return;

        const option = this.cutoffOptions[sheet.sequence];
        const rawRow = option === 'MANUAL'
            ? this.manualRows[sheet.sequence]
            : option;
        const row = Number(rawRow);
        if (!Number.isInteger(row) || row < 1 || row > sheet.max_content_row + 1) {
            this.invalidCutoffSequences.add(sheet.sequence);
            this.invalidCutoffSequences = new Set(this.invalidCutoffSequences);
            this.errorMessage = `Indica una fila de corte válida para el día ${sheet.sequence}.`;
            return;
        }

        this.savingCutoffSequence = sheet.sequence;
        this.errorMessage = '';
        this.championshipsApi.updateImportPreview(
            this.championship.id,
            this.preview.id,
            {
                sheets: [{
                    sequence: sheet.sequence,
                    cutoff_row: row,
                    confirmed: true
                }]
            }
        ).subscribe({
            next: (preview) => {
                this.preview = preview;
                this.dirtyCutoffSequences.delete(sheet.sequence);
                this.initializeCutoffs(preview, true);
                this.savingCutoffSequence = null;
                this.snackBar.open(
                    `Cortes AM/PM del día ${sheet.sequence} confirmados.`,
                    'Cerrar',
                    { duration: 3500 }
                );
            },
            error: (error) => {
                this.errorMessage = this.apiMessage(error, 'No fue posible confirmar los cortes.');
                this.savingCutoffSequence = null;
            }
        });
    }

    async confirmImport(): Promise<void> {
        if (
            !this.preview
            || !this.championship
            || !this.canConfirmImport
            || this.loading
        ) {
            return;
        }

        const confirmation = await Swal.fire({
            title: 'Confirmar día de competencia',
            html:
                `Se agregará <strong>${this.preview.preview.sheets[0].name}</strong> `
                + `el <strong>${this.competitionDate || this.preview.decisions.competition_date}</strong>, `
                + `con <strong>${this.preview.preview.total_categories} categorías</strong> `
                + `y <strong>${this.preview.preview.total_gymnasts} participantes</strong>.`,
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: 'Confirmar importación',
            cancelButtonText: 'Volver a revisar',
            confirmButtonColor: '#4f46e5'
        });
        if (!confirmation.isConfirmed) {
            return;
        }

        this.loading = true;
        this.errorMessage = '';
        try {
            const result = await firstValueFrom(
                this.championshipsApi.confirmImport(
                    this.championship.id,
                    this.preview.id
                )
            );
            this.snackBar.open(
                `Día agregado: ${result.imported.categories} categorías`,
                'Cerrar',
                { duration: 4500 }
            );
            if (result.imported.new_judge_credentials?.length) {
                result.imported.new_judge_credentials.forEach((item) =>
                    this.credentialDelivery.addImported(item.judge, item));
            }
            if (this.creationQueue.length) {
                this.creationQueue.shift();
                if (this.creationQueue.length) {
                    await this.uploadNextInitialDay(this.championship.id);
                    return;
                }
            }
            if (this.returnToChampionshipDetail) {
                await this.router.navigate(['/championships', this.championship.id]);
                return;
            }
            await this.router.navigate([
                '/championships',
                this.championship.id
            ]);
        } catch (error) {
            this.errorMessage = this.apiMessage(
                error,
                'No fue posible confirmar la importación.'
            );
        } finally {
            this.loading = false;
        }
    }

    private loadDraft(championshipId: string): void {
        if (this.initialImportQueue.championshipId !== championshipId) {
            this.initialImportQueue.days = [];
        }
        this.pageLoading = true;
        this.championshipsApi.get(championshipId).subscribe({
            next: (championship) => {
                if (
                    championship.status !== 'DRAFT'
                    || (championship.counts.days > 0 && !this.addingDay && !this.initialSetup)
                ) {
                    void this.router.navigate([
                        '/championships',
                        championship.id
                    ]);
                    return;
                }
                this.championship = championship;
                if (this.routePreviewId && (this.addingDay || this.initialSetup)) {
                    this.loadPreview(championship.id, this.routePreviewId);
                    return;
                }
                if (this.routePreviewId) {
                    this.loadPreview(championship.id, this.routePreviewId);
                } else {
                    this.pageLoading = false;
                    this.retryInitialDay();
                }
            },
            error: (error) => {
                this.errorMessage = this.apiMessage(
                    error,
                    'No fue posible abrir el borrador.'
                );
                this.pageLoading = false;
            }
        });
    }

    private loadPreview(championshipId: string, previewId: string): void {
        this.championshipsApi
            .getImportPreview(championshipId, previewId)
            .subscribe({
                next: (preview) => {
                    this.preview = preview;
                    this.initializeCutoffs(preview);
                    this.pageLoading = false;
                },
                error: (error) => {
                    this.errorMessage = this.apiMessage(
                        error,
                        'No fue posible recuperar la previsualización.'
                    );
                    this.pageLoading = false;
                }
            });
    }

    private initializeCutoffs(
        preview: ImportPreview,
        preserveDirty = false
    ): void {
        if (!preserveDirty) {
            this.dirtyCutoffSequences.clear();
            this.cutoffOptions = {};
            this.manualRows = {};
        }
        this.competitionDate = preview.decisions.competition_date || this.competitionDate;
        this.invalidCutoffSequences.clear();
        for (const sheet of preview.preview.sheets) {
            if (
                preserveDirty
                && this.dirtyCutoffSequences.has(sheet.sequence)
            ) {
                continue;
            }
            const selectedRow = sheet.selected_cutoff_row;
            const selectedIsMarker = selectedRow !== null
                && this.eligibleMarkers(sheet).some(
                    (marker) => marker.row === selectedRow
                );
            if (selectedIsMarker) {
                this.cutoffOptions[sheet.sequence] = selectedRow;
                this.manualRows[sheet.sequence] = null;
            } else {
                this.cutoffOptions[sheet.sequence] = 'MANUAL';
                this.manualRows[sheet.sequence] = selectedRow;
            }
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
