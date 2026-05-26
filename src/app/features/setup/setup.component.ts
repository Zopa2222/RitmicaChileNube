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
import { MatTooltipModule } from '@angular/material/tooltip';
import Swal from 'sweetalert2';

import { ChampionshipService } from '../../core/services/championship.service';
import { ApiService } from '../../core/services/api.service';
import { JudgeRole, BancaJudge } from '../../core/models/judge.model';
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
        MatChipsModule,
        MatTooltipModule
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

    judgeRoles: (JudgeRole | '')[] = ['', 'DB', 'DA', 'A', 'E', 'L', 'P'];
    roleLabels: { [key: string]: string } = {
        '': '— Sin rol',
        'DA': 'DA (Dificultad A)',
        'DB': 'DB (Dificultad B)',
        'E': 'E (Ejecución)',
        'A': 'A (Artístico)',
        'L': 'L (Línea)',
        'P': 'P (Planilla)'
    };

    constructor(
        private fb: FormBuilder,
        private championshipService: ChampionshipService,
        private apiService: ApiService,
        private router: Router
    ) {
        this.setupForm = this.fb.group({
            championshipName: ['', Validators.required],
            bancaA: this.fb.array([]),
            bancaB: this.fb.array([])
        });

        // Add initial judges for each banca
        this.addJudge('A');
        this.addJudge('B');
    }

    get bancaA(): FormArray {
        return this.setupForm.get('bancaA') as FormArray;
    }

    get bancaB(): FormArray {
        return this.setupForm.get('bancaB') as FormArray;
    }

    addJudge(banca: 'A' | 'B'): void {
        const judgeGroup = this.fb.group({
            name: ['', Validators.required],
            roleAM: ['', Validators.required],
            rolePM: ['']
        });

        // Auto-copy roleAM to rolePM when roleAM changes
        judgeGroup.get('roleAM')!.valueChanges.subscribe(val => {
            const pmCtrl = judgeGroup.get('rolePM')!;
            // Only auto-fill if PM is currently empty
            if (!pmCtrl.value) {
                pmCtrl.setValue(val);
            }
        });

        if (banca === 'A') {
            this.bancaA.push(judgeGroup);
        } else {
            this.bancaB.push(judgeGroup);
        }
    }

    removeJudge(banca: 'A' | 'B', index: number): void {
        const array = banca === 'A' ? this.bancaA : this.bancaB;
        if (array.length > 0) {
            array.removeAt(index);
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
        // Validate each banca+jornada independently
        for (const banca of ['A', 'B'] as const) {
            const judges = (banca === 'A' ? this.bancaA.value : this.bancaB.value) as
                { name: string; roleAM: string; rolePM: string }[];

            if (judges.length === 0) continue; // Banca can be empty

            for (const jornada of ['AM', 'PM'] as const) {
                const roles = judges
                    .map(j => jornada === 'AM' ? j.roleAM : j.rolePM)
                    .filter(r => r && r !== '');

                if (roles.length === 0) continue; // No judges for this jornada

                const daCount = roles.filter(r => r === 'DA').length;
                const dbCount = roles.filter(r => r === 'DB').length;
                const eCount = roles.filter(r => r === 'E').length;
                const aCount = roles.filter(r => r === 'A').length;
                const pCount = roles.filter(r => r === 'P').length;
                // L has no limit

                if (daCount > 2) return `Banca ${banca} ${jornada}: máximo 2 jueces DA (tiene ${daCount})`;
                if (dbCount > 2) return `Banca ${banca} ${jornada}: máximo 2 jueces DB (tiene ${dbCount})`;
                if (eCount > 4) return `Banca ${banca} ${jornada}: máximo 4 jueces E (tiene ${eCount})`;
                if (aCount > 4) return `Banca ${banca} ${jornada}: máximo 4 jueces A (tiene ${aCount})`;
                if (pCount > 2) return `Banca ${banca} ${jornada}: máximo 2 jueces Planilla (tiene ${pCount})`;
            }

            // Each judge must have at least one role
            for (const j of judges) {
                if ((!j.roleAM || j.roleAM === '') && (!j.rolePM || j.rolePM === '')) {
                    return `Banca ${banca}: el juez "${j.name || '(sin nombre)'}" debe tener al menos un rol (AM o PM)`;
                }
            }
        }

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
            this.error = 'Por favor complete todos los campos requeridos';
            return;
        }

        if (!this.selectedFile) {
            this.error = 'Por favor seleccione un archivo Excel';
            return;
        }

        // At least one banca must have judges
        if (this.bancaA.length === 0 && this.bancaB.length === 0) {
            this.error = 'Debe agregar jueces en al menos una banca';
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

            // 2. Add judges from both bancas
            const allBancaJudges: { banca: 'A' | 'B'; data: any }[] = [];

            for (const banca of ['A', 'B'] as const) {
                const judges = (banca === 'A' ? this.bancaA.value : this.bancaB.value) as
                    { name: string; roleAM: string; rolePM: string }[];

                for (const judge of judges) {
                    const rolAM = judge.roleAM && judge.roleAM !== '' ? judge.roleAM : null;
                    const rolPM = judge.rolePM && judge.rolePM !== '' ? judge.rolePM : null;

                    console.log('Adding judge:', judge.name, 'Banca:', banca, 'AM:', rolAM, 'PM:', rolPM);
                    await this.apiService.addJudge(championshipId, {
                        nombre: judge.name,
                        banca: banca,
                        rol_am: rolAM,
                        rol_pm: rolPM
                    }).toPromise();

                    allBancaJudges.push({
                        banca,
                        data: { name: judge.name, roleAM: rolAM, rolePM: rolPM }
                    });
                }
            }

            // 3. Upload Excel file
            console.log('Uploading Excel file...');
            const uploadResponse = await this.apiService.uploadExcel(
                championshipId,
                this.selectedFile
            ).toPromise();
            console.log('Excel uploaded, categories:', uploadResponse.categorias);

            // 4. Build championship object
            const bancaAJudges: BancaJudge[] = allBancaJudges
                .filter(j => j.banca === 'A')
                .map(j => j.data as BancaJudge);

            const bancaBJudges: BancaJudge[] = allBancaJudges
                .filter(j => j.banca === 'B')
                .map(j => j.data as BancaJudge);

            const categoriasBanca = uploadResponse.categorias_banca || {};

            const championship: Championship = {
                id: championshipId,
                name: championshipName,
                bancaA: bancaAJudges,
                bancaB: bancaBJudges,
                categoriasBanca: categoriasBanca,
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
