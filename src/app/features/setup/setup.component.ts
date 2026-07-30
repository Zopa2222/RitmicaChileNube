import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
    Component,
    OnInit
} from '@angular/core';
import {
    FormBuilder,
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
    readonly championshipForm = this.formBuilder.nonNullable.group({
        name: ['', [Validators.required, Validators.maxLength(180)]],
        kind: ['CLASIFICATORIO', Validators.required],
        zone: ['', [Validators.required, Validators.maxLength(120)]],
        start_date: ['', Validators.required]
    });

    championship: CloudChampionshipDetail | null = null;
    preview: ImportPreview | null = null;
    selectedFile: File | null = null;
    loading = false;
    pageLoading = false;
    errorMessage = '';
    savingSheet: number | null = null;
    cutoffOptions: Record<number, CutoffOption> = {};
    manualRows: Record<number, number | null> = {};

    private readonly routeChampionshipId =
        this.route.snapshot.paramMap.get('championshipId');
    private readonly routePreviewId =
        this.route.snapshot.queryParamMap.get('previewId');

    constructor(
        private readonly formBuilder: FormBuilder,
        private readonly route: ActivatedRoute,
        private readonly router: Router,
        private readonly championshipsApi: CloudChampionshipApiService,
        private readonly snackBar: MatSnackBar
    ) { }

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

    createChampionship(): void {
        if (this.championshipForm.invalid || this.loading) {
            this.championshipForm.markAllAsTouched();
            return;
        }

        this.loading = true;
        this.errorMessage = '';
        const value = this.championshipForm.getRawValue();
        this.championshipsApi.create({
            name: value.name.trim(),
            kind: value.kind,
            zone: value.zone.trim(),
            start_date: value.start_date
        }).subscribe({
            next: (championship) => {
                this.loading = false;
                this.snackBar.open(
                    'Borrador creado. Ahora carga el orden de paso.',
                    'Cerrar',
                    { duration: 4000 }
                );
                void this.router.navigate(
                    ['/championships', championship.id, 'import'],
                    { replaceUrl: true }
                );
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

        this.loading = true;
        this.errorMessage = '';
        this.championshipsApi.createImportPreview(
            this.championship.id,
            this.selectedFile
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
    }

    saveSheetCutoff(sheet: ImportPreviewSheet): void {
        if (!this.preview || !this.championship || this.savingSheet !== null) {
            return;
        }
        const option = this.cutoffOptions[sheet.sequence];
        const rawRow = option === 'MANUAL'
            ? this.manualRows[sheet.sequence]
            : option;
        const row = Number(rawRow);
        if (
            !Number.isInteger(row)
            || row < 1
            || row > sheet.max_content_row + 1
        ) {
            this.snackBar.open(
                `Indica una fila entre 1 y ${sheet.max_content_row + 1}.`,
                'Cerrar',
                { duration: 4500 }
            );
            return;
        }

        this.savingSheet = sheet.sequence;
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
                this.initializeCutoffs(preview, true);
                this.savingSheet = null;
            },
            error: (error) => {
                this.snackBar.open(
                    this.apiMessage(error, 'No fue posible guardar el corte.'),
                    'Cerrar',
                    { duration: 5500 }
                );
                this.savingSheet = null;
            }
        });
    }

    acceptDetectedCutoffs(): void {
        if (!this.preview || !this.championship || this.loading) {
            return;
        }
        if (!this.preview.preview.sheets.some(
            (sheet) => sheet.detected_cutoff_row !== null
        )) {
            this.snackBar.open(
                'Ninguna hoja tiene un corte automático válido.',
                'Cerrar',
                { duration: 4500 }
            );
            return;
        }

        this.loading = true;
        this.championshipsApi.updateImportPreview(
            this.championship.id,
            this.preview.id,
            { accept_detected: true }
        ).subscribe({
            next: (preview) => {
                this.preview = preview;
                this.initializeCutoffs(preview, true);
                this.loading = false;
                if (!this.allCutoffsConfirmed) {
                    this.snackBar.open(
                        'Se aceptaron los cortes detectados. Revisa las hojas pendientes.',
                        'Cerrar',
                        { duration: 5000 }
                    );
                }
            },
            error: (error) => {
                this.errorMessage = this.apiMessage(
                    error,
                    'No fue posible aceptar los cortes detectados.'
                );
                this.loading = false;
            }
        });
    }

    async confirmImport(): Promise<void> {
        if (
            !this.preview
            || !this.championship
            || !this.allCutoffsConfirmed
            || this.loading
        ) {
            return;
        }

        const confirmation = await Swal.fire({
            title: 'Confirmar orden de paso',
            html:
                `Se crearán <strong>${this.preview.preview.total_days} días</strong>, `
                + `<strong>${this.preview.preview.total_categories} categorías</strong> `
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
                `Orden confirmado: ${result.imported.categories} categorías`,
                'Cerrar',
                { duration: 4500 }
            );
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
        this.pageLoading = true;
        this.championshipsApi.get(championshipId).subscribe({
            next: (championship) => {
                if (
                    championship.status !== 'DRAFT'
                    || championship.counts.days > 0
                ) {
                    void this.router.navigate([
                        '/championships',
                        championship.id
                    ]);
                    return;
                }
                this.championship = championship;
                if (this.routePreviewId) {
                    this.loadPreview(championship.id, this.routePreviewId);
                } else {
                    this.pageLoading = false;
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
        preserveManual = false
    ): void {
        for (const sheet of preview.preview.sheets) {
            if (
                preserveManual
                && this.cutoffOptions[sheet.sequence] === 'MANUAL'
                && !sheet.cutoff_confirmed
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
