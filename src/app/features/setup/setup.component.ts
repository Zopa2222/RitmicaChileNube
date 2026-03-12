import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, FormArray, Validators, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import Swal from 'sweetalert2';

import { ExcelService } from '../../core/services/excel.service';
import { ChampionshipService } from '../../core/services/championship.service';
import { ApiService } from '../../core/services/api.service';
import { Judge, JudgeRole } from '../../core/models/judge.model';
import { Championship } from '../../core/models/championship.model';

@Component({
    selector: 'app-setup',
    standalone: true,
    imports: [
        CommonModule,
        ReactiveFormsModule,
        MatCardModule,
        MatFormFieldModule,
        MatInputModule,
        MatSelectModule,
        MatButtonModule,
        MatIconModule,
        MatChipsModule
    ],
    templateUrl: './setup.component.html',
    styleUrls: ['./setup.component.scss']
})
export class SetupComponent {
    setupForm: FormGroup;
    selectedFile: File | null = null;
    fileName: string = '';
    loading: boolean = false;
    error: string = '';

    judgeRoles: JudgeRole[] = ['DA', 'DB', 'E', 'A', 'L'];

    readonly currentYear = new Date().getFullYear();

    etapasCampeonato: string[] = [
        `1er Control Zona Norte ${this.currentYear}`,
        `2do Control Zona Norte ${this.currentYear}`,
        `1er Control Zona Centro ${this.currentYear}`,
        `2do Control Zona Centro ${this.currentYear}`,
        `1er Control Zona Sur ${this.currentYear}`,
        `2do Control Zona Sur ${this.currentYear}`,
        `Final Nacional ${this.currentYear}`
    ];

    constructor(
        private fb: FormBuilder,
        private excelService: ExcelService,
        private championshipService: ChampionshipService,
        private apiService: ApiService,
        private router: Router
    ) {
        this.setupForm = this.fb.group({
            championshipName: ['', Validators.required],
            judges: this.fb.array([])
        });

        // Add initial judge
        this.addJudge();
    }

    get judges(): FormArray {
        return this.setupForm.get('judges') as FormArray;
    }

    addJudge(): void {
        const judgeGroup = this.fb.group({
            name: ['', Validators.required],
            role: ['', Validators.required]
        });
        this.judges.push(judgeGroup);
    }

    removeJudge(index: number): void {
        if (this.judges.length > 1) {
            this.judges.removeAt(index);
        }
    }

    onFileSelected(event: any): void {
        const file = event.target.files[0];
        if (file) {
            this.selectedFile = file;
            this.fileName = file.name;
            this.error = '';
        }
    }

    validateJudges(): string | null {
        const judges = this.judges.value as { name: string; role: JudgeRole }[];

        const daCount = judges.filter(j => j.role === 'DA').length;
        const dbCount = judges.filter(j => j.role === 'DB').length;
        const eCount = judges.filter(j => j.role === 'E').length;
        const aCount = judges.filter(j => j.role === 'A').length;
        const lCount = judges.filter(j => j.role === 'L').length;

        if (daCount < 1 || daCount > 2) return 'Debe haber entre 1 y 2 jueces DA';
        if (dbCount < 1 || dbCount > 2) return 'Debe haber entre 1 y 2 jueces DB';
        if (eCount < 1 || eCount > 4) return 'Debe haber entre 1 y 4 jueces E';
        if (aCount < 1 || aCount > 4) return 'Debe haber entre 1 y 4 jueces A';
        if (lCount > 1) return 'Puede haber máximo 1 juez L';

        return null;
    }

    goHome(): void {
        Swal.fire({
            title: '¿Volver al Menú Principal?',
            text: 'Se perderán los datos que no hayan sido guardados.',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#ef4444',
            cancelButtonColor: '#64748b',
            confirmButtonText: 'Sí, volver',
            cancelButtonText: 'Cancelar'
        }).then((result) => {
            if (result.isConfirmed) {
                this.router.navigate(['/']);
            }
        });
    }

    async onSubmit(): Promise<void> {
        if (!this.setupForm.valid) {
            this.error = 'Por favor complete todos los campos';
            return;
        }

        if (!this.selectedFile) {
            this.error = 'Por favor seleccione un archivo Excel';
            return;
        }

        const validationError = this.validateJudges();
        if (validationError) {
            this.error = validationError;
            return;
        }

        this.loading = true;
        this.error = '';

        try {
            const championshipName = this.setupForm.value.championshipName;

            // 1. Create championship
            console.log('Creating championship:', championshipName);
            const createResponse = await this.apiService.createChampionship(championshipName).toPromise();
            const championshipId = createResponse.id;
            console.log('Championship created:', championshipId);

            // 2. Add judges
            const judgesData = this.judges.value as { name: string; role: JudgeRole }[];
            const roleCounters: { [key: string]: number } = { E: 1, A: 1, DA: 1, DB: 1 };

            for (const judge of judgesData) {
                // Convert role with index for DA/DB second judge and E/A
                let rolBackend: string = judge.role;
                if (judge.role === 'DA') {
                    rolBackend = roleCounters['DA'] === 1 ? 'DA' : 'DA2';
                    roleCounters['DA']++;
                } else if (judge.role === 'DB') {
                    rolBackend = roleCounters['DB'] === 1 ? 'DB' : 'DB2';
                    roleCounters['DB']++;
                } else if (judge.role === 'E' || judge.role === 'A') {
                    rolBackend = `${judge.role}${roleCounters[judge.role]++}`;
                }

                console.log('Adding judge:', judge.name, 'with role:', rolBackend);
                await this.apiService.addJudge(championshipId, {
                    nombre: judge.name,
                    rol: rolBackend
                }).toPromise();
            }

            // 3. Upload Excel file
            console.log('Uploading Excel file...');
            const uploadResponse = await this.apiService.uploadExcel(
                championshipId,
                this.selectedFile
            ).toPromise();
            console.log('Excel uploaded, categories:', uploadResponse.categorias);

            // 4. Save championship info to local service
            const processedJudges: Judge[] = [];
            const roleCounters2: { [key: string]: number } = { E: 1, A: 1, DA: 1, DB: 1 };

            judgesData.forEach(j => {
                const judge: Judge = {
                    name: j.name,
                    role: j.role
                };

                if (j.role === 'E' || j.role === 'A') {
                    judge.index = roleCounters2[j.role]++;
                } else if (j.role === 'DA') {
                    if (roleCounters2['DA'] > 1) judge.role = 'DA2';
                    roleCounters2['DA']++;
                } else if (j.role === 'DB') {
                    if (roleCounters2['DB'] > 1) judge.role = 'DB2';
                    roleCounters2['DB']++;
                }

                processedJudges.push(judge);
            });

            const championship: Championship = {
                id: championshipId,
                name: championshipName,
                judges: processedJudges,
                categories: uploadResponse.categorias.map((catName: string) => ({
                    name: catName,
                    gymnasts: []
                }))
            };

            this.championshipService.setChampionship(championship);

            // 5. Navigate to scoring view
            this.router.navigate(['/scoring']);

        } catch (err: any) {
            console.error('Error in setup:', err);
            this.error = 'Error: ' + (err.error?.error || err.message || 'Error desconocido');
        } finally {
            this.loading = false;
        }
    }
}
