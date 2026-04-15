import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatListModule } from '@angular/material/list';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { CdkDragDrop, DragDropModule, moveItemInArray } from '@angular/cdk/drag-drop';
import Swal from 'sweetalert2';

import { ChampionshipService } from '../../core/services/championship.service';
import { ScoringService } from '../../core/services/scoring.service';
import { ApiService } from '../../core/services/api.service';
import { Championship } from '../../core/models/championship.model';
import { Category } from '../../core/models/category.model';
import { Gymnast, createEmptyGymnast } from '../../core/models/gymnast.model';
import { Judge } from '../../core/models/judge.model';

@Component({
    selector: 'app-scoring',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        MatSidenavModule,
        MatListModule,
        MatButtonModule,
        MatIconModule,
        MatTooltipModule,
        MatSnackBarModule,
        DragDropModule
    ],
    templateUrl: './scoring.component.html',
    styleUrls: ['./scoring.component.scss']
})
export class ScoringComponent implements OnInit, OnDestroy {
    championship: Championship | null = null;
    currentCategory: Category | null = null;
    judges: Judge[] = [];
    scoreColumns: string[] = [];

    // Auto-save state
    private autoSaveTimer: any = null;
    private readonly AUTO_SAVE_DELAY = 30_000; // 30 seconds
    hasUnsavedChanges = false;
    saving = false;

    constructor(
        private championshipService: ChampionshipService,
        private scoringService: ScoringService,
        private apiService: ApiService,
        private router: Router,
        private snackBar: MatSnackBar
    ) { }

    ngOnInit(): void {
        this.championship = this.championshipService.getChampionship();

        if (!this.championship || !this.championship.id) {
            this.router.navigate(['/setup']);
            return;
        }

        this.judges = this.championship.judges;
        this.scoreColumns = this.scoringService.getScoreColumns(this.judges);

        // Load categories from backend
        this.apiService.getCategories(this.championship.id).subscribe({
            next: (response) => {
                console.log('Categories loaded from backend:', response.categorias);

                // Update championship with categories from backend
                this.championship!.categories = response.categorias.map((catName: string) => ({
                    name: catName,
                    gymnasts: []
                }));

                // Check if a category was pre-selected (e.g. from export view)
                const preSelected = this.championshipService.getCurrentCategory();
                const targetCategory = this.championship!.categories.find(
                    c => c.name === preSelected?.name
                ) || this.championship!.categories[0];

                if (targetCategory) {
                    this.selectCategory(targetCategory);
                }
            },
            error: (err) => {
                console.error('Error loading categories:', err);
                this.snackBar.open('Error al cargar categorías', 'Cerrar', { duration: 3000 });
            }
        });
    }

    ngOnDestroy(): void {
        // Save pending changes before leaving
        if (this.hasUnsavedChanges) {
            this.performSave(true);
        }
        this.clearAutoSaveTimer();
    }

    selectCategory(category: Category): void {
        if (!this.championship) return;

        // Auto-save current category before switching
        if (this.hasUnsavedChanges && this.currentCategory) {
            this.performSave(true);
        }

        this.currentCategory = { ...category };

        // Fetch gymnasts from API
        this.apiService.getCategory(this.championship.id!, category.name).subscribe({
            next: (data) => {
                if (data.gimnastas) {
                    // Map backend data to frontend model
                    this.currentCategory!.gymnasts = data.gimnastas.map((g: any) => this.mapBackendGymnastToFrontend(g));

                    // Update state
                    this.championshipService.setCurrentCategory(this.currentCategory!);
                }
            },
            error: (err) => {
                console.error('Error fetching category:', err);
                this.snackBar.open('Error al cargar la categoría', 'Cerrar', { duration: 3000 });
            }
        });
    }

    private mapBackendGymnastToFrontend(bg: any): Gymnast {
        const scores: { [key: string]: number } = {};

        if (bg.DA) scores['DA'] = bg.DA;
        if (bg.DB) scores['DB'] = bg.DB;

        // Map E scores array to E1, E2...
        if (Array.isArray(bg.E)) {
            bg.E.forEach((val: number, idx: number) => {
                scores[`E${idx + 1}`] = val;
            });
        }

        // Map A scores array to A1, A2...
        if (Array.isArray(bg.A)) {
            bg.A.forEach((val: number, idx: number) => {
                scores[`A${idx + 1}`] = val;
            });
        }

        return {
            name: bg.nombre || '',
            club: bg.club || '',
            scores: scores,
            desc: bg.Desc || 0,
            totalScore: bg.puntajeTotal || 0,
            order: bg.order || 0
        };
    }

    onScoreChange(gymnast: Gymnast, column: string, value: string): void {
        const numValue = parseFloat(value) || 0;
        gymnast.scores[column] = numValue;
        this.updateGymnastScore(gymnast);
        this.markDirty();
    }

    onDescChange(gymnast: Gymnast, value: string): void {
        gymnast.desc = parseFloat(value) || 0;
        this.updateGymnastScore(gymnast);
        this.markDirty();
    }

    updateGymnastScore(gymnast: Gymnast): void {
        gymnast.totalScore = this.scoringService.calculateTotalScore(gymnast, this.judges);
    }

    hasScoreError(gymnast: Gymnast, column: string): boolean {
        const validation = this.scoringService.validateScores(gymnast, this.judges);
        return validation.errorColumns.includes(column);
    }

    addGymnast(): void {
        if (!this.currentCategory) return;

        const newGymnast = createEmptyGymnast(this.currentCategory.gymnasts.length);
        this.currentCategory.gymnasts.push(newGymnast);
        this.markDirty();
    }

    deleteGymnast(index: number): void {
        if (!this.currentCategory) return;

        Swal.fire({
            title: 'Eliminar Gimnasta',
            text: '¿Está seguro de eliminar esta gimnasta?',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#ef4444',
            cancelButtonColor: '#64748b',
            confirmButtonText: 'Sí, eliminar',
            cancelButtonText: 'Cancelar'
        }).then((result) => {
            if (result.isConfirmed) {
                this.currentCategory!.gymnasts.splice(index, 1);
                this.currentCategory!.gymnasts.forEach((g, i) => g.order = i);
                this.markDirty();
            }
        });
    }

    drop(event: CdkDragDrop<Gymnast[]>): void {
        if (!this.currentCategory) return;

        moveItemInArray(
            this.currentCategory.gymnasts,
            event.previousIndex,
            event.currentIndex
        );

        this.currentCategory.gymnasts.forEach((g, i) => g.order = i);
        this.markDirty();
    }

    sortByScore(): void {
        if (!this.currentCategory) return;

        this.currentCategory.gymnasts.sort((a, b) => b.totalScore - a.totalScore);
        this.currentCategory.gymnasts.forEach((g, i) => g.order = i);
        this.markDirty();

        this.snackBar.open('Gimnastas ordenadas por puntaje', 'OK', { duration: 2000 });
    }

    // --- Auto-save helpers ---

    markDirty(): void {
        this.hasUnsavedChanges = true;
        this.resetAutoSaveTimer();
    }

    private resetAutoSaveTimer(): void {
        this.clearAutoSaveTimer();
        this.autoSaveTimer = setTimeout(() => {
            if (this.hasUnsavedChanges) {
                this.performSave(true);
            }
        }, this.AUTO_SAVE_DELAY);
    }

    private clearAutoSaveTimer(): void {
        if (this.autoSaveTimer) {
            clearTimeout(this.autoSaveTimer);
            this.autoSaveTimer = null;
        }
    }

    /** Manual save triggered by button */
    saveCategory(): void {
        this.performSave(false);
    }

    /**
     * Perform the actual save.
     * @param silent  If true, show a subtle auto-save message instead of the full snackbar.
     */
    private performSave(silent: boolean): void {
        if (!this.currentCategory || !this.championship) return;
        if (this.saving) return; // prevent concurrent saves

        this.saving = true;
        this.clearAutoSaveTimer();

        // Map frontend data to backend format
        const gimnastasPayload = this.currentCategory.gymnasts.map(g => {
            const eScores: number[] = [];
            const aScores: number[] = [];

            Object.keys(g.scores).forEach(key => {
                if (key.startsWith('E')) {
                    const idx = parseInt(key.substring(1)) - 1;
                    eScores[idx] = g.scores[key];
                }
            });

            Object.keys(g.scores).forEach(key => {
                if (key.startsWith('A')) {
                    const idx = parseInt(key.substring(1)) - 1;
                    aScores[idx] = g.scores[key];
                }
            });

            for (let i = 0; i < eScores.length; i++) if (eScores[i] === undefined) eScores[i] = 0;
            for (let i = 0; i < aScores.length; i++) if (aScores[i] === undefined) aScores[i] = 0;

            return {
                nombre: g.name,
                club: g.club,
                DA: g.scores['DA'] || 0,
                DB: g.scores['DB'] || 0,
                E: eScores,
                A: aScores,
                Desc: g.desc || 0,
                puntajeFrontend: g.totalScore,
                order: g.order
            };
        });

        this.apiService.updateCategory(
            this.championship.id!,
            this.currentCategory.name,
            gimnastasPayload
        ).subscribe({
            next: (response) => {
                this.hasUnsavedChanges = false;
                this.saving = false;

                if (silent) {
                    this.snackBar.open('✓ Guardado automático', '', { duration: 1500 });
                } else {
                    this.snackBar.open('Categoría guardada exitosamente', 'OK', { duration: 3000 });
                }

                // Update local totals with server calculation if provided
                if (response.gimnastas) {
                    response.gimnastas.forEach((bg: any) => {
                        const localGymnast = this.currentCategory!.gymnasts.find(
                            g => g.name === bg.nombre
                        );
                        if (localGymnast && bg.puntajeTotal !== undefined) {
                            localGymnast.totalScore = bg.puntajeTotal;
                        }
                    });
                }
            },
            error: (err) => {
                console.error('Error saving category:', err);
                this.saving = false;
                this.snackBar.open('Error al guardar categoría', 'Cerrar', { duration: 3000 });
            }
        });
    }

    goToExport(): void {
        this.router.navigate(['/export']);
    }

    goHome(): void {
        Swal.fire({
            title: '¿Terminar campeonato?',
            text: '¿Está seguro que desea salir? Se perderán los datos que no hayan sido guardados.',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#ef4444',
            cancelButtonColor: '#64748b',
            confirmButtonText: 'Sí, terminar',
            cancelButtonText: 'Cancelar'
        }).then((result) => {
            if (result.isConfirmed) {
                this.router.navigate(['/']);
            }
        });
    }
}
