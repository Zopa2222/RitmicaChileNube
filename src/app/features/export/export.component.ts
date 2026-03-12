import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';

import { ChampionshipService } from '../../core/services/championship.service';
import { ExcelService } from '../../core/services/excel.service';
import { ApiService } from '../../core/services/api.service';
import { Championship } from '../../core/models/championship.model';
import { Category } from '../../core/models/category.model';
import Swal from 'sweetalert2';

@Component({
    selector: 'app-export',
    standalone: true,
    imports: [
        CommonModule,
        MatCardModule,
        MatButtonModule,
        MatIconModule,
        MatTableModule
    ],
    templateUrl: './export.component.html',
    styleUrls: ['./export.component.scss']
})
export class ExportComponent implements OnInit {
    championship: Championship | null = null;
    displayedColumns: string[] = ['category', 'gymnasts', 'actions'];

    constructor(
        private championshipService: ChampionshipService,
        private excelService: ExcelService,
        private apiService: ApiService,
        private router: Router
    ) { }

    ngOnInit(): void {
        this.championship = this.championshipService.getChampionship();

        if (!this.championship || !this.championship.id) {
            this.router.navigate(['/setup']);
            return;
        }

        // Load category counts from backend
        this.loadCategoryCounts();
    }

    loadCategoryCounts(): void {
        if (!this.championship?.id) return;

        // Load each category's gymnast count from backend
        this.championship.categories.forEach((category) => {
            this.apiService.getCategory(this.championship!.id!, category.name).subscribe({
                next: (data) => {
                    // Update gymnasts array with data from backend
                    category.gymnasts = data.gimnastas.map((g: any) => ({
                        name: g.nombre,
                        club: g.club,
                        scores: {},
                        desc: 0,
                        totalScore: g.puntajeTotal || 0,
                        order: g.order || 0
                    }));
                },
                error: (err) => {
                    console.error(`Error loading category ${category.name}:`, err);
                }
            });
        });
    }

    getTotalGymnasts(): number {
        if (!this.championship) return 0;
        return this.championship.categories.reduce(
            (total, cat) => total + cat.gymnasts.length,
            0
        );
    }

    exportToExcel(): void {
        if (!this.championship) return;

        this.apiService.exportChampionship(this.championship.id!).subscribe({
            next: (blob) => {
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `${this.championship!.name}_resultados.xlsx`;
                link.click();
                window.URL.revokeObjectURL(url);
            },
            error: (err) => {
                console.error('Error exporting Excel:', err);
            }
        });
    }

    exportToPdf(): void {
        if (!this.championship) return;

        this.apiService.exportChampionshipPdf(this.championship.id!).subscribe({
            next: (blob) => {
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `${this.championship!.name}_resultados.pdf`;
                link.click();
                window.URL.revokeObjectURL(url);
            },
            error: (err) => {
                console.error('Error exporting PDF:', err);
            }
        });
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

    viewCategory(category: Category): void {
        this.championshipService.setCurrentCategory(category);
        this.router.navigate(['/scoring']);
    }
}
